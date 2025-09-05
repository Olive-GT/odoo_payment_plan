from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PaymentPlanLineAllocation(models.Model):
    _name = 'payment.plan.line.allocation'
    _description = 'Payment Plan Line Account Move Allocation'
    _order = 'id desc'

    payment_plan_line_id = fields.Many2one('payment.plan.line', string='Payment Plan Line', 
                                        required=True, ondelete='cascade')
    account_move_id = fields.Many2one('account.move', string='Accounting Entry', 
                                    required=True, ondelete='cascade')
    account_move_line_id = fields.Many2one('account.move.line', string='Account Move Line',
                                         domain="[('move_id', '=', account_move_id)]")
    currency_id = fields.Many2one('res.currency', related='payment_plan_line_id.currency_id', 
                               store=True)
    amount = fields.Monetary('Allocated Amount', required=True)
    payment_plan_id = fields.Many2one('payment.plan', related='payment_plan_line_id.payment_plan_id', 
                                   store=True, readonly=True)
    company_id = fields.Many2one('res.company', related='payment_plan_id.company_id', 
                              store=True, readonly=True)
    allocation_date = fields.Date('Allocation Date', default=fields.Date.context_today, required=True)
    notes = fields.Text('Notes')

    @api.constrains('amount')
    def _check_amount(self):
        """Check that the allocated amount is positive"""
        for alloc in self:
            if alloc.amount <= 0:
                raise ValidationError(_("Allocated amount must be positive!"))

    @api.constrains('amount', 'account_move_id', 'payment_plan_line_id')
    def _check_allocation_limits(self):
        """Check that we don't allocate more than the account move amount or payment plan line amount"""
        for alloc in self:
            # Get total allocations for this account move
            move_allocations = self.search([
                ('account_move_id', '=', alloc.account_move_id.id),
                ('id', '!=', alloc.id)
            ])
            
            total_allocated_to_move = sum(move_allocations.mapped('amount'))
            
            # Get total amount for this payment plan line
            line_allocations = self.search([
                ('payment_plan_line_id', '=', alloc.payment_plan_line_id.id),
                ('id', '!=', alloc.id)
            ])
            
            total_allocated_to_line = sum(line_allocations.mapped('amount'))
            
            # Check if we're over-allocating
            if alloc.amount + total_allocated_to_line > alloc.payment_plan_line_id.amount:
                raise ValidationError(_(
                    "The total allocated amount (%s) exceeds the payment plan line amount (%s)!",
                    alloc.amount + total_allocated_to_line,
                    alloc.payment_plan_line_id.amount
                ))
            
            # We don't need to check against account_move total, as partial allocations are allowed
            
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to update payment plan line status if necessary"""
        allocations = super().create(vals_list)
        
        # Update each payment line's status
        for alloc in allocations:
            alloc.payment_plan_line_id._update_payment_status_from_allocations()
            
        return allocations
    
    def write(self, vals):
        """Override write to update payment plan line status if necessary"""
        result = super().write(vals)
        
        # Update each payment line's status if relevant fields were changed
        if any(field in vals for field in ['amount', 'payment_plan_line_id', 'account_move_id']):
            for alloc in self:
                alloc.payment_plan_line_id._update_payment_status_from_allocations()
                
                # If payment line was changed, also update the old one
                if 'payment_plan_line_id' in vals:
                    old_line = self.env['payment.plan.line'].browse(vals['payment_plan_line_id'])
                    if old_line.exists():
                        old_line._update_payment_status_from_allocations()
                
        return result
    
    def unlink(self):
        """Override unlink to update payment plan line status"""
        payment_lines = self.mapped('payment_plan_line_id')
        
        result = super().unlink()
        
        # Update the payment status for all affected lines
        for line in payment_lines:
            if line.exists():  # Make sure the line still exists
                line._update_payment_status_from_allocations()
        
        return result
