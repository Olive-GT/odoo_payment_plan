from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date


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

    @api.depends('date', 'paid')
    def _compute_overdue_days(self):
        # Get current date for overdue calculation
        today = fields.Date.context_today(self)
        
        for line in self:
            # Skip computation for records with no date
            if not line.date:
                line.overdue_days = 0
                continue
                
            if line.paid:
                # Paid lines have no overdue days
                line.overdue_days = 0
            elif line.date < today:
                # Calculate days between due date and today
                delta = today - line.date
                line.overdue_days = delta.days
            else:
                # Future dates have no overdue days
                line.overdue_days = 0

    @api.depends('overdue_days', 'amount', 'payment_plan_id.interest_rate', 'date', 'paid')
    def _compute_interest_amount(self):
        today = fields.Date.context_today(self)  # Add current date dependency
        
        for line in self:
            if line.paid or not line.date or line.date >= today or line.overdue_days <= 0:
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
            line.payment_date = fields.Date.context_today(self)

    def mark_as_unpaid(self):
        for line in self:
            line.paid = False
            line.payment_date = False
            line.payment_reference = False
            
    def update_overdue_status(self):
        """Manually update overdue days and interest calculation"""
        self._compute_overdue_days()
        self._compute_interest_amount()
        return True

    @api.model
    def _update_overdue_lines(self):
        """
        This method is meant to be called from a scheduled action (cron job)
        to update overdue days and interest on all payment plan lines
        """
        # Find all unpaid lines that are overdue
        today = fields.Date.context_today(self)
        overdue_lines = self.search([
            ('paid', '=', False),
            ('date', '<', today)
        ])
        
        # Force recalculation of overdue days and interest
        if overdue_lines:
            overdue_lines._compute_overdue_days()
            overdue_lines._compute_interest_amount()
        
        return True
