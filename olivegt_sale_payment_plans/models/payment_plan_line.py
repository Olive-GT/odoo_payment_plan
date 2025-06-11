from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date
import logging


class PaymentPlanLine(models.Model):
    _name = 'payment.plan.line'
    _description = 'Payment Plan Line'
    _order = 'date'

    payment_plan_id = fields.Many2one('payment.plan', string='Payment Plan', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='payment_plan_id.currency_id', store=True)
    date = fields.Date('Due Date', required=True)
    amount = fields.Monetary('Amount', required=True)
    name = fields.Char('Description')
    paid = fields.Boolean('Paid', default=False)
    payment_date = fields.Date('Payment Date')
    payment_reference = fields.Char('Payment Reference')
    running_balance = fields.Monetary('Running Balance', compute='_compute_running_balance', store=True)
    overdue_days = fields.Integer('Overdue Days', compute='_compute_overdue_days', store=True)
    interest_amount = fields.Monetary('Interest', compute='_compute_interest_amount', store=True)
    total_with_interest = fields.Monetary('Total with Interest', compute='_compute_interest_amount', store=True)

    @api.depends('payment_plan_id.line_ids.amount', 'payment_plan_id.line_ids.paid')
    def _compute_running_balance(self):
        for line in self:
            # Skip computation for new records with no date
            if not line.date:
                line.running_balance = 0
                continue
                
            # Handle both saved and new records
            try:
                # For saved records, use date and id for ordering
                previous_lines = line.payment_plan_id.line_ids.filtered(
                    lambda l: l.date and l.date <= line.date
                )
                paid_amount = sum(previous_lines.filtered(lambda l: l.paid).mapped('amount'))
                total_amount = sum(previous_lines.mapped('amount'))
                line.running_balance = total_amount - paid_amount
            except TypeError:
                # If comparing NewId objects fails, just include all lines
                previous_lines = line.payment_plan_id.line_ids
                paid_amount = sum(previous_lines.filtered(lambda l: l.paid).mapped('amount'))
                total_amount = sum(previous_lines.mapped('amount'))
                line.running_balance = total_amount - paid_amount

    @api.depends('date', 'payment_date', 'paid')
    def _compute_overdue_days(self):
        # Get current date as fallback for unpaid lines
        today = fields.Date.context_today(self)
        
        for line in self:
            # Skip computation for records with no date
            if not line.date:
                line.overdue_days = 0
                continue
                
            if line.paid and line.payment_date:
                # For paid lines, calculate days between due date and payment date
                delta = line.payment_date - line.date
                line.overdue_days = delta.days if delta.days > 0 else 0
            elif line.paid:
                # Paid lines with no payment date recorded have no overdue days
                line.overdue_days = 0
            elif line.payment_date:
                # For unpaid lines with payment_date set (unusual case, but handle it)
                delta = line.payment_date - line.date
                line.overdue_days = delta.days if delta.days > 0 else 0
            elif line.date < today:
                # Only if no payment_date is available, use today as reference
                delta = today - line.date
                line.overdue_days = delta.days
            else:
                # Future dates have no overdue days
                line.overdue_days = 0

    @api.depends('overdue_days', 'amount', 'payment_plan_id.interest_rate', 'date', 'paid', 'payment_date')
    def _compute_interest_amount(self):
        today = fields.Date.context_today(self)  # Fallback date
        
        for line in self:
            reference_date = line.payment_date if line.payment_date else today
            
            if line.paid or not line.date or line.date >= reference_date or line.overdue_days <= 0:
                line.interest_amount = 0
            else:
                # Use the interest rate from the payment plan
                if line.payment_plan_id and line.payment_plan_id.interest_rate:
                    annual_rate = line.payment_plan_id.interest_rate / 100.0  # Convert from percentage
                else:
                    # Default interest rate if not set on payment plan
                    annual_rate = 0.10  # 10% per year as default
                    
                daily_rate = annual_rate / 365.0
                line.interest_amount = line.amount * line.overdue_days * daily_rate
            
            line.total_with_interest = line.amount + line.interest_amount

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_('Amount must be positive!'))

    def mark_as_paid(self):
        for line in self:
            line.paid = True
            # Only set payment_date if it's not already set
            if not line.payment_date:
                line.payment_date = fields.Date.context_today(self)

    def mark_as_unpaid(self):
        for line in self:
            line.paid = False
            line.payment_date = False
            line.payment_reference = False
            
    def update_overdue_status(self):
        """Manually update overdue days and interest calculation"""
        today = fields.Date.context_today(self)
        logger = logging.getLogger(__name__)
        logger.info(f"Manually updating {len(self)} payment plan lines")
        
        for line in self:
            # Skip paid lines with payment_date already set
            if line.paid and line.payment_date:
                continue
                
            reference_date = line.payment_date if line.payment_date else today
                
            # Update overdue days
            if line.date and line.date < reference_date:
                delta = reference_date - line.date
                line.overdue_days = delta.days
                
                # Update interest
                if line.payment_plan_id and line.payment_plan_id.interest_rate:
                    annual_rate = line.payment_plan_id.interest_rate / 100.0
                else:
                    annual_rate = 0.10  # Default 10%
                
                daily_rate = annual_rate / 365.0
                line.interest_amount = line.amount * line.overdue_days * daily_rate
                line.total_with_interest = line.amount + line.interest_amount
            else:
                line.overdue_days = 0
                line.interest_amount = 0
                line.total_with_interest = line.amount
                
        # Ensure UI gets refreshed
        self.flush_recordset(['overdue_days', 'interest_amount', 'total_with_interest'])
        
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _update_overdue_lines(self):
        """
        This method is meant to be called from a scheduled action (cron job)
        to update overdue days and interest on all payment plan lines
        """
        today = fields.Date.context_today(self)
        
        # Get all lines to process - both unpaid lines and paid lines that might need recalculation
        lines_to_update = self.search([
            '|',
            ('paid', '=', False),
            '&',
            ('paid', '=', True),
            ('payment_date', '!=', False),
        ])
        
        _logger = logging.getLogger(__name__)
        _logger.info(f"Updating {len(lines_to_update)} payment plan lines")
        
        # For explicit field recomputation
        if lines_to_update:
            # Mark the records as needing recomputation
            self.env.add_to_compute(self._fields['overdue_days'], lines_to_update)
            self.env.add_to_compute(self._fields['interest_amount'], lines_to_update)
            self.env.add_to_compute(self._fields['total_with_interest'], lines_to_update)
            
            # Force recomputation using the compute methods that now respect payment_date
            lines_to_update._compute_overdue_days()
            lines_to_update._compute_interest_amount()
            
            # Handle lines needing direct database updates
            for line in lines_to_update:
                reference_date = line.payment_date if line.payment_date else today
                
                # Only process if due date is past reference date
                if line.date and line.date < reference_date:
                    delta = reference_date - line.date
                    overdue_days = delta.days if delta.days > 0 else 0
                    
                    # Interest calculation
                    interest_amount = 0
                    # Only calculate interest for unpaid lines or paid lines that were overdue
                    if not line.paid or (line.paid and overdue_days > 0):
                        if line.payment_plan_id and line.payment_plan_id.interest_rate:
                            annual_rate = line.payment_plan_id.interest_rate / 100.0
                        else:
                            annual_rate = 0.10  # Default 10%
                        
                        daily_rate = annual_rate / 365.0
                        interest_amount = line.amount * overdue_days * daily_rate
                        
                    total_with_interest = line.amount + interest_amount
                    
                    # Update database directly
                    self.env.cr.execute("""
                        UPDATE payment_plan_line 
                        SET overdue_days = %s, interest_amount = %s, total_with_interest = %s 
                        WHERE id = %s
                    """, (overdue_days, interest_amount, total_with_interest, line.id))
            
            # Flush all pending operations
            self.env.cr.commit()
        
        _logger.info("Payment plan overdue line update completed")
        return True
