﻿from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date
import logging
import math


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
    overdue_days = fields.Integer('Overdue Days', compute='_compute_overdue_days', store=True, readonly=False)
    interest_amount = fields.Monetary('Interest', compute='_compute_interest_amount', store=True, readonly=False)
    total_with_interest = fields.Monetary('Total with Interest', compute='_compute_total_with_interest', store=True)
    
    # Allocation fields
    allocation_ids = fields.One2many('payment.plan.line.allocation', 'payment_plan_line_id', 
                                   string='Account Move Allocations')
    allocated_amount = fields.Monetary('Allocated Amount', compute='_compute_allocated_amount', store=True,
                                    help="Total amount allocated to this line from accounting entries")
    unallocated_amount = fields.Monetary('Unallocated Amount', compute='_compute_allocated_amount', store=True,
                                     help="Remaining amount that needs allocation")
    allocation_count = fields.Integer('Allocation Count', compute='_compute_allocated_amount', store=True)
    account_move_ids = fields.Many2many('account.move', string='Related Account Moves',
                                    compute='_compute_account_moves', store=False)
    is_fully_allocated = fields.Boolean('Fully Allocated', compute='_compute_allocated_amount', store=True)
    allocation_percentage = fields.Float('Allocation %', compute='_compute_allocated_amount', store=True,
                                     help="Percentage of this line that has been allocated")
    is_partially_allocated = fields.Boolean('Partially Allocated', compute='_compute_allocation_states', store=True)
    is_overdue_and_unallocated = fields.Boolean('Overdue and Unallocated', compute='_compute_allocation_states', store=True)

    @api.depends('payment_plan_id.line_ids.amount', 'payment_plan_id.line_ids.paid', 'payment_plan_id.line_ids.allocated_amount')
    def _compute_running_balance(self):
        for line in self:
            # Skip computation for new records with no date
            if not line.date:
                line.running_balance = 0
                continue
                
            # Use sorted lines to ensure consistent order regardless of ID
            sorted_lines = line.payment_plan_id.line_ids.sorted(key=lambda l: (l.date or fields.Date.today(), l.id or 0))
            
            # Calculate running balance up to current line's position
            total_amount = 0
            paid_amount = 0
            allocated_amount = 0
            
            for payment_line in sorted_lines:
                if payment_line == line:
                    break
                if payment_line.date:  # Only include lines with dates
                    total_amount += payment_line.amount
                    if payment_line.paid:
                        paid_amount += payment_line.amount
                    else:
                        # Consider partial allocations for unpaid lines
                        allocated_amount += payment_line.allocated_amount
            
            # Add current line's amount to the total
            total_amount += line.amount
            
            # Set the running balance - consider both paid lines and partial allocations
            line.running_balance = total_amount - paid_amount - allocated_amount

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
            
            # Handle different cases for paid and unpaid lines
            if not line.date or line.date >= reference_date or line.overdue_days <= 0:
                # No interest for future due dates or no overdue days
                line.interest_amount = 0
            elif line.paid and line.payment_date and line.date < line.payment_date:
                # For paid lines with payment date, use the payment date for interest calculation
                # Only if the stored interest_amount is zero, calculate it
                if not line.interest_amount:
                    delta_days = (line.payment_date - line.date).days
                    if delta_days > 0:
                        # Use calculate_interest_for_days helper method
                        line.interest_amount = line._calculate_interest_for_days(delta_days)
                # If interest amount is already set, keep it (from mark_as_paid)
            else:
                # For unpaid lines or special cases, calculate interest normally
                line.interest_amount = line._calculate_interest_for_days(line.overdue_days)
    
    @api.depends('amount', 'interest_amount')
    def _compute_total_with_interest(self):
        """Compute total with interest separately to allow manually editing interest"""
        for line in self:
            line.total_with_interest = line.amount + line.interest_amount

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_('Amount must be positive!'))

    def mark_as_paid(self, respect_manual_edits=True):
        """
        Mark a payment line as paid
        
        Args:
            respect_manual_edits: If True, will preserve manually edited overdue days and interest
        """
        today = fields.Date.context_today(self)
        for line in self:
            # Store original interest data
            original_interest = line.interest_amount
            original_total = line.total_with_interest
            original_overdue_days = line.overdue_days
            
            # Set payment date first if not already set
            if not line.payment_date:
                line.payment_date = today
            
            # Calculate interest using payment date before marking as paid
            if not line.paid:
                # Use the payment date for calculation
                line.calculate_and_store_interest(line.payment_date, respect_manual_edits)
                
                # If previous calculation resulted in zero interest but there was overdue,
                # restore the original values which may have been computed before
                if respect_manual_edits and line.interest_amount == 0 and original_overdue_days > 0 and original_interest > 0:
                    line.interest_amount = original_interest
                    line.total_with_interest = original_total
                    line.overdue_days = original_overdue_days
            
            # Now mark as paid, preserving the interest calculation
            line.paid = True
            
            # If this was called directly (not from allocation update), update payment reference
            if not line.payment_reference and line.is_fully_allocated:
                # Get the references from the allocations
                move_refs = line.allocation_ids.mapped('account_move_id.name')
                if move_refs:
                    line.payment_reference = ', '.join(move_refs)
            
            # Force direct database update to ensure interest values are preserved
            self.env.cr.execute("""
                UPDATE payment_plan_line 
                SET paid = TRUE,
                    payment_date = %s,
                    interest_amount = %s,
                    total_with_interest = %s,
                    overdue_days = %s
                WHERE id = %s
            """, (line.payment_date, line.interest_amount, line.total_with_interest, line.overdue_days, line.id))
            
            # Flush to ensure changes are committed
            self.env.cr.commit()

    def mark_as_unpaid(self, respect_manual_edits=True):
        """
        Mark a payment line as unpaid
        
        Args:
            respect_manual_edits: If True, will preserve manually edited overdue days and interest
        """
        for line in self:
            # Store original values before changing status
            original_interest = line.interest_amount
            original_total = line.total_with_interest
            original_overdue_days = line.overdue_days
            original_payment_date = line.payment_date
            
            # Update payment status
            line.paid = False
            line.payment_reference = False
            
            # Keep payment_date temporarily for interest calculations
            if original_payment_date:
                # Calculate interest based on the stored payment date
                line.calculate_and_store_interest(original_payment_date, respect_manual_edits)
                
                # Now clear payment date after calculation
                line.payment_date = False
                
                # Force database update to preserve the calculated values
                self.env.cr.execute("""
                    UPDATE payment_plan_line 
                    SET paid = FALSE,
                        payment_date = NULL,
                        payment_reference = NULL,
                        interest_amount = %s,
                        total_with_interest = %s,
                        overdue_days = %s
                    WHERE id = %s
                """, (line.interest_amount, line.total_with_interest, line.overdue_days, line.id))
                
                # Flush to ensure changes are committed
                self.env.cr.commit()
            else:
                # If no payment date was recorded, use original values if they exist and we're respecting manual edits
                if respect_manual_edits and original_overdue_days > 0 and original_interest > 0:
                    # Force database update
                    self.env.cr.execute("""
                        UPDATE payment_plan_line 
                        SET paid = FALSE,
                            payment_date = NULL,
                            payment_reference = NULL,
                            interest_amount = %s,
                            total_with_interest = %s,
                            overdue_days = %s
                        WHERE id = %s
                    """, (original_interest, original_total, original_overdue_days, line.id))
                    
                    # Flush to ensure changes are committed
                    self.env.cr.commit()
                else:
                    # Recalculate based on today's date
                    today = fields.Date.context_today(self)
                    line.calculate_and_store_interest(today, respect_manual_edits)
                    
                    # Force update of payment fields
                    line.payment_date = False
                    line.payment_reference = False
                    self.env.cr.commit()
            
    def calculate_and_store_interest(self, reference_date=None, respect_manual_edits=True):
        """Calculate and store interest for a payment line
        
        Args:
            reference_date: Date to use for calculations, defaults to payment_date or today
            respect_manual_edits: If True, will not overwrite manually edited values
        """
        if not reference_date:
            reference_date = self.payment_date if self.payment_date else fields.Date.context_today(self)
            
        # Calculate overdue days based on dates (regardless of manual edits)
        if self.date and self.date < reference_date:
            delta = reference_date - self.date
            calculated_overdue_days = delta.days if delta.days > 0 else 0
        else:
            calculated_overdue_days = 0
                
        # Calculate interest based on calculated overdue days
        calculated_interest_amount = 0
        if calculated_overdue_days > 0:
            calculated_interest_amount = self._calculate_interest_for_days(calculated_overdue_days)
            
        # Determine which values to use based on respect_manual_edits flag
        # If respect_manual_edits is True and we have existing values, keep them
        # Otherwise, use the newly calculated values
        if respect_manual_edits:
            # Keep existing values for edited fields
            final_overdue_days = self.overdue_days
            final_interest_amount = self.interest_amount
        else:
            # Use calculated values
            final_overdue_days = calculated_overdue_days
            final_interest_amount = calculated_interest_amount
            
        # Calculate total with interest
        final_total_with_interest = self.amount + final_interest_amount
        
        # Store the final values
        self.overdue_days = final_overdue_days
        self.interest_amount = final_interest_amount
        self.total_with_interest = final_total_with_interest
        
        # Return the calculated values
        return {
            'overdue_days': final_overdue_days,
            'interest_amount': final_interest_amount,
            'total_with_interest': final_total_with_interest
        }

    def update_overdue_status(self, respect_manual_edits=True):
        """
        Manually update overdue days and interest calculation
        
        Args:
            respect_manual_edits: If True, will not overwrite manually edited values
        """
        today = fields.Date.context_today(self)
        logger = logging.getLogger(__name__)
        logger.info(f"Manually updating {len(self)} payment plan lines, respect_manual_edits={respect_manual_edits}")
        
        for line in self:
            # For paid lines, use payment_date as reference date
            if line.paid and line.payment_date:
                # Preserve interest for paid lines that were overdue
                if line.overdue_days <= 0:
                    # Calculate using payment date
                    line.calculate_and_store_interest(line.payment_date, respect_manual_edits)
            else:
                # For unpaid lines, calculate normally using payment date or today
                reference_date = line.payment_date if line.payment_date else today
                line.calculate_and_store_interest(reference_date, respect_manual_edits)
                
        # Ensure UI gets refreshed
        self.flush_recordset(['overdue_days', 'interest_amount', 'total_with_interest'])
        
        return {"type": "ir.actions.client", "tag": "reload"}
        
    def reset_and_recalculate(self):
        """
        Reset any manually edited values and force recalculation
        This deliberately ignores manual edits and recalculates based on payment date or today
        """
        today = fields.Date.context_today(self)
        logger = logging.getLogger(__name__)
        logger.info(f"Resetting and recalculating {len(self)} payment plan lines")
        
        for line in self:
            # Determine reference date - payment_date for paid lines, today for unpaid
            reference_date = line.payment_date if (line.paid and line.payment_date) else today
            
            # Force recalculation ignoring manual edits
            line.calculate_and_store_interest(reference_date, respect_manual_edits=False)
            
        # Ensure UI gets refreshed
        self.flush_recordset(['overdue_days', 'interest_amount', 'total_with_interest'])
        
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _update_overdue_lines(self, respect_manual_edits=True):
        """
        This method is meant to be called from a scheduled action (cron job)
        to update overdue days and interest on all payment plan lines
        
        Args:
            respect_manual_edits: If True, will not overwrite manually edited values
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
        _logger.info(f"Updating {len(lines_to_update)} payment plan lines, respect_manual_edits={respect_manual_edits}")
        
        # Process lines in batches for better performance
        if lines_to_update:
            _logger.info("Processing payment plan lines for interest calculation")
            
            # Update each line with appropriate reference date
            for line in lines_to_update:
                # For paid lines, use payment_date
                if line.paid and line.payment_date:
                    # Skip if interest is already calculated correctly
                    if line.overdue_days > 0 and line.interest_amount > 0 and respect_manual_edits:
                        continue
                        
                    # Calculate using payment date
                    result = line.calculate_and_store_interest(line.payment_date, respect_manual_edits)
                    
                    # Only update the database if we're not respecting manual edits or if values changed
                    if not respect_manual_edits:
                        # Store calculated values directly in database for better performance
                        self.env.cr.execute("""
                            UPDATE payment_plan_line 
                            SET overdue_days = %s, interest_amount = %s, total_with_interest = %s 
                            WHERE id = %s
                        """, (result['overdue_days'], result['interest_amount'], 
                            result['total_with_interest'], line.id))
                    
                else:
                    # For unpaid lines, calculate based on today's date
                    result = line.calculate_and_store_interest(today, respect_manual_edits)
                    
                    # Only update the database if we're not respecting manual edits or if values changed
                    if not respect_manual_edits:
                        # Store calculated values directly in database for better performance
                        self.env.cr.execute("""
                            UPDATE payment_plan_line 
                            SET overdue_days = %s, interest_amount = %s, total_with_interest = %s 
                            WHERE id = %s
                        """, (result['overdue_days'], result['interest_amount'], 
                            result['total_with_interest'], line.id))
            
            # Flush all pending operations to database
            self.env.cr.commit()
            
            # Force recomputation of the total_with_interest field that depends on these values
            self.env.add_to_compute(self._fields['total_with_interest'], lines_to_update)
        
        _logger.info("Payment plan overdue line update completed")
        return True

    def _calculate_interest_for_days(self, days):
        """Helper method to calculate interest consistently
        
        Args:
            days: Number of days to calculate interest for
            
        Returns:
            interest_amount: Calculated interest amount
        """
        interest_amount = 0
        
        if days <= 0 or not self.payment_plan_id:
            return 0
            
        # Different calculation methods based on payment plan configuration
        if self.payment_plan_id.interest_calculation_method == 'percentage':
            # Monthly percentage method - calculated daily
            if self.payment_plan_id.interest_rate:
                monthly_rate = self.payment_plan_id.interest_rate / 100.0  # Convert percentage to decimal
                daily_rate = monthly_rate / 30.0  # Approximate days in a month
                interest_amount = self.amount * days * daily_rate
            else:
                # Default 1% monthly if not set
                daily_rate = (1.0 / 100.0) / 30.0
                interest_amount = self.amount * days * daily_rate
        
        elif self.payment_plan_id.interest_calculation_method == 'fixed':
            # Fixed monthly amount method
            if self.payment_plan_id.fixed_interest_amount:
                # Calculate how many months have passed (including partial months)
                months_passed = days / 30.0  # Approximate months
                if months_passed < 1:
                    # Less than a month - prorate the fixed amount
                    interest_amount = self.payment_plan_id.fixed_interest_amount * months_passed
                else:
                    # Round up for complete months
                    complete_months = math.ceil(months_passed)
                    interest_amount = self.payment_plan_id.fixed_interest_amount * complete_months
        
        return interest_amount

    @api.depends('allocation_ids', 'allocation_ids.amount', 'amount')
    def _compute_allocated_amount(self):
        """Compute the total allocated amount and related statistics"""
        for line in self:
            line.allocated_amount = sum(line.allocation_ids.mapped('amount'))
            line.unallocated_amount = line.amount - line.allocated_amount
            line.allocation_count = len(line.allocation_ids)
            line.is_fully_allocated = line.unallocated_amount <= 0
            
            # Calculate allocation percentage
            if line.amount > 0:
                line.allocation_percentage = line.allocated_amount / line.amount
            else:
                line.allocation_percentage = 0.0
            # The following line is redundant and can be removed or kept if it serves a specific purpose not immediately obvious.
            # For now, I'll keep it as it was in the original code.
            line.allocation_percentage = (line.allocated_amount / line.amount) * 100 if line.amount > 0 else 0
    
    @api.depends('amount', 'allocated_amount', 'unallocated_amount', 'date')
    def _compute_allocation_states(self):
        """Compute boolean fields for view decoration based on allocation and date"""
        today = fields.Date.context_today(self)
        for line in self:
            line.is_partially_allocated = line.allocated_amount > 0 and line.allocated_amount < line.amount
            line.is_overdue_and_unallocated = line.date < today and line.unallocated_amount > 0

    @api.depends('allocation_ids', 'allocation_ids.account_move_id')
    def _compute_account_moves(self):
        """Compute the related account moves"""
        for line in self:
            line.account_move_ids = line.allocation_ids.mapped('account_move_id')
            
    def _update_payment_status_from_allocations(self):
        """Update the payment status based on allocated amount"""
        for line in self:
            if line.is_fully_allocated and not line.paid:
                # Line is now fully allocated, mark as paid
                line.mark_as_paid(respect_manual_edits=True)
            elif not line.is_fully_allocated and line.paid and line.allocated_amount <= 0:
                # Line is no longer fully allocated and has no allocations, mark as unpaid
                line.mark_as_unpaid(respect_manual_edits=True)
                
    def action_view_allocations(self):
        """Open the allocations related to this payment plan line"""
        self.ensure_one()
        action = {
            'name': _('Payment Allocations for %s') % self.name or _('Line'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.line.allocation',
            'view_mode': 'list,form',
            'domain': [('payment_plan_line_id', '=', self.id)],
            'context': {
                'default_payment_plan_line_id': self.id,
                'default_payment_plan_id': self.payment_plan_id.id,
                'search_default_groupby_account_move': 1,
            },
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    No allocations for this payment plan line
                </p>
                <p>
                    <strong>Line Information:</strong><br/>
                    Total Amount: %s %s<br/>
                    Allocated Amount: %s %s (%s%%)<br/>
                    Unallocated Amount: %s %s
                </p>
            """ % (
                self.amount,
                self.currency_id.symbol,
                self.allocated_amount,
                self.currency_id.symbol,
                round(self.allocation_percentage * 100, 2),
                self.unallocated_amount,
                self.currency_id.symbol
            )
        }
        if len(self.allocation_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.allocation_ids.id,
            })
        return action
