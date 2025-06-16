from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero
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
    
    # New fields for reconciliation
    reconciliation_ids = fields.One2many('payment.plan.reconciliation', 'payment_plan_line_id', string='Reconciliations')
    allocation_count = fields.Integer(compute='_compute_allocation_count', string='Allocations')
    allocated_amount = fields.Monetary(compute='_compute_allocated_amount', string='Allocated Amount', store=True)
    allocation_state = fields.Selection([
        ('none', 'No Asignado'),
        ('partial', 'Parcialmente Asignado'),
        ('full', 'Totalmente Asignado')
    ], compute='_compute_allocation_state', string='Allocation Status', store=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partially Allocated'),
        ('allocated', 'Allocated'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue')
    ], compute='_compute_state', string='Status', store=True)    # Vamos a usar un campo Char para mayor compatibilidad
    allocation_summary = fields.Char(compute='_compute_allocation_summary', string='Allocations')
    
    # New field to show move lines details in the dashboard
    move_lines_summary = fields.Html(compute='_compute_move_lines_summary', string='Payment Details')
    
    @api.depends('reconciliation_ids.state')
    def _compute_allocation_count(self):
        for line in self:
            # Solo contar reconciliaciones confirmadas
            confirmed_reconciliations = line.reconciliation_ids.filtered(lambda r: r.state == 'confirmed')
            line.allocation_count = len(confirmed_reconciliations)
    
    @api.depends('reconciliation_ids.amount', 'reconciliation_ids.state', 'amount')
    def _compute_allocated_amount(self):
        for line in self:
            line.allocated_amount = sum(line.reconciliation_ids.filtered(
                lambda r: r.state == 'confirmed').mapped('amount')
            )
    
    @api.depends('allocated_amount', 'amount')
    def _compute_allocation_state(self):
        for line in self:
            if float_is_zero(line.allocated_amount, precision_rounding=line.currency_id.rounding):
                line.allocation_state = 'none'
            elif float_compare(line.allocated_amount, line.amount, precision_rounding=line.currency_id.rounding) >= 0:
                line.allocation_state = 'full'
            else:
                line.allocation_state = 'partial'
    
    @api.depends('payment_plan_id.line_ids.amount', 'payment_plan_id.line_ids.paid')
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
            
            for payment_line in sorted_lines:
                if payment_line == line:
                    break
                if payment_line.date:  # Only include lines with dates
                    total_amount += payment_line.amount
                    if payment_line.paid:
                        paid_amount += payment_line.amount
            
            # Add current line's amount to the total
            total_amount += line.amount
            
            # Set the running balance
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
        
        elif self.payment_plan_id.interest_calculation_method == 'fixed':            # Fixed monthly amount method
            if self.payment_plan_id.fixed_interest_amount:
                # Calculate how many months have passed (including partial months)
                months_passed = days / 30.0  # Approximate months
                if months_passed < 1:
                    # Less than a month - prorate the fixed amount
                    interest_amount = self.payment_plan_id.fixed_interest_amount
                else:
                    # Round up for complete months
                    complete_months = math.ceil(months_passed)
                    interest_amount = self.payment_plan_id.fixed_interest_amount * complete_months
        return interest_amount

    def action_view_reconciliations(self):
        """View reconciliations for this line"""
        self.ensure_one()
        return {
            'name': _('Reconciliations'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.reconciliation',
            'view_mode': 'list,form',
            'domain': [('payment_plan_line_id', '=', self.id)],
            'context': {
                'default_payment_plan_id': self.payment_plan_id.id,
                'default_payment_plan_line_id': self.id,
            },
        }
    
    def action_reconcile(self):
        """Open reconciliation wizard"""
        self.ensure_one()
        
        # Check if we have a wizard model first
        model = 'payment.plan.reconciliation.wizard'
        if model in self.env:
            return {
                'name': _('Reconcile Payment'),
                'type': 'ir.actions.act_window',
                'res_model': model,
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payment_plan_id': self.payment_plan_id.id,
                    'default_payment_plan_line_id': self.id,
                    'default_partner_id': self.payment_plan_id.partner_id.id,
                    'default_amount': self.amount - self.allocated_amount,
                }
            }
        else:
            # If wizard doesn't exist yet, create a simple form
            return {
                'name': _('Create Reconciliation'),
                'type': 'ir.actions.act_window',
                'res_model': 'payment.plan.reconciliation',
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_payment_plan_id': self.payment_plan_id.id,
                    'default_payment_plan_line_id': self.id,
                    'default_amount': self.amount - self.allocated_amount,
                }
            }
    
    @api.depends('paid', 'allocation_state', 'overdue_days')
    def _compute_state(self):
        for line in self:
            if line.paid:
                line.state = 'paid'
            elif line.allocation_state == 'full':
                line.state = 'allocated'
            elif line.allocation_state == 'partial':
                line.state = 'partial'
            elif line.overdue_days > 0:
                line.state = 'overdue'
            else:
                line.state = 'pending'
                
    def action_toggle_allocations(self):
        """Toggle display of allocations in list view.
        This is a client-side action, no server side effect."""
        # This is primarily a client-side action to toggle visibility
        # It doesn't need to do anything on the server side
        # The JS will handle showing/hiding the allocations section
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_show_allocations(self):
        """
        Open a popup window to show allocation details
        """
        self.ensure_one()
        
        # Get confirmed reconciliations for this line
        reconciliations = self.reconciliation_ids.filtered(lambda r: r.state == 'confirmed')
        
        if not reconciliations:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin Asignaciones'),
                    'message': _('No hay asignaciones confirmadas para esta línea del plan de pago.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
          # Return action to show reconciliations in a popup
        return {
            'name': _('Detalles de Asignaciones'),
            'view_mode': 'list,form',  # Usamos list para compatibilidad con Odoo 17
            'res_model': 'payment.plan.reconciliation',
            'domain': [('id', 'in', reconciliations.ids)],
            'view_id': self.env.ref('olivegt_sale_payment_plans.view_payment_plan_reconciliation_detailed_tree').id,
            'type': 'ir.actions.act_window',
            'target': 'new',  # This opens in a dialog/popup
            'context': {
                'create': False, 
                'edit': False,
                'delete': False            }
        }
        
    @api.depends('reconciliation_ids.state', 'reconciliation_ids.move_id', 'reconciliation_ids.amount', 
               'reconciliation_ids.date', 'reconciliation_ids.journal_id')
    def _compute_allocation_summary(self):
        for line in self:
            confirmed_reconciliations = line.reconciliation_ids.filtered(lambda r: r.state == 'confirmed')
            if not confirmed_reconciliations:
                line.allocation_summary = ""
                continue
            
            # Mostrar de forma clara la cantidad de asignaciones y el total
            total_amount = sum(confirmed_reconciliations.mapped('amount'))
            formatted_amount = "{:,.2f}".format(total_amount)
            count = len(confirmed_reconciliations)
            
            # Obtener una lista de los journals involucrados
            journals = confirmed_reconciliations.mapped('journal_id.name')
            unique_journals = list(set([j for j in journals if j]))
            
            # Formatear mejor para mayor visibilidad en la vista de lista
            if unique_journals:
                journal_text = ", ".join(unique_journals[:2])
                if len(unique_journals) > 2:
                    journal_text += f" y {len(unique_journals) - 2} más"
                line.allocation_summary = f"{count} asign: Q{formatted_amount} ({journal_text})"
            else:
                line.allocation_summary = f"{count} asignaciones: Q{formatted_amount}"    @api.depends('reconciliation_ids.state', 'reconciliation_ids.move_id', 'reconciliation_ids.amount', 
                'reconciliation_ids.date', 'reconciliation_ids.journal_id', 'reconciliation_ids.move_payment_reference')
    def _compute_move_lines_summary(self):
        """Generate a formatted HTML table with the move lines details for this payment plan line"""
        for line in self:
            # Only include confirmed reconciliations
            confirmed_reconciliations = line.reconciliation_ids.filtered(lambda r: r.state == 'confirmed')
            if not confirmed_reconciliations:
                line.move_lines_summary = ""
                continue
            
            currency_symbol = line.currency_id.symbol or 'Q'
                
            # Create a mini HTML table for the move lines
            html = '<div class="o_payment_details" style="font-size: 0.85em;">'
            
            # Use table format for better alignment
            html += '<table style="width: 100%; border-collapse: separate; border-spacing: 0 2px;">'
            
            for rec in confirmed_reconciliations:
                amount_str = "{:,.2f}".format(rec.amount)
                date_str = rec.date.strftime('%d/%m/%Y') if rec.date else ''
                journal_name = rec.journal_id.name or ''
                move_ref = rec.move_id.name or ''
                reference = rec.move_payment_reference or ''
                
                # Truncate long text
                if len(journal_name) > 15:
                    journal_name = journal_name[:12] + '...'
                if len(reference) > 15:
                    reference = reference[:12] + '...'
                
                # Set background color based on journal type
                bg_color = '#f0f8ff'  # Default light blue
                if rec.journal_id.type == 'bank':
                    bg_color = '#e6f7e6'  # Light green for bank
                elif rec.journal_id.type == 'cash':
                    bg_color = '#fff7e6'  # Light yellow for cash
                
                html += f'<tr style="background-color: {bg_color}; border-radius: 4px;">'
                
                # Amount column with currency
                html += f'<td style="padding: 3px; font-weight: bold; white-space: nowrap;">'
                html += f'{currency_symbol} {amount_str}'
                html += '</td>'
                
                # Date column
                html += f'<td style="padding: 3px; white-space: nowrap;">{date_str}</td>'
                
                # Journal column
                html += f'<td style="padding: 3px;" title="{rec.journal_id.name}">{journal_name}</td>'
                
                # Reference column (if available)
                if reference:
                    html += f'<td style="padding: 3px;" title="{rec.move_payment_reference}">'
                    html += f'{reference}</td>'
                else:
                    html += f'<td style="padding: 3px;" title="{move_ref}">{move_ref}</td>'
                
                html += '</tr>'
            
            html += '</table></div>'
            line.move_lines_summary = html
