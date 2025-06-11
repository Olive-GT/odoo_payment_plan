from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PaymentPlanLineAllocationWizard(models.TransientModel):
    _name = 'payment.plan.line.allocation.wizard'
    _description = 'Create Payment Plan Line Allocations'
    
    payment_plan_id = fields.Many2one('payment.plan', string='Payment Plan', required=True)
    partner_id = fields.Many2one('res.partner', related='payment_plan_id.partner_id', readonly=True)
    currency_id = fields.Many2one('res.currency', related='payment_plan_id.currency_id', readonly=True)
    
    # Account move to allocate from
    account_move_id = fields.Many2one('account.move', string='Accounting Entry', 
                                    domain="[('state', '=', 'posted'), ('partner_id', '=', partner_id)]",
                                    required=True)
    account_move_line_id = fields.Many2one('account.move.line', string='Account Move Line',
                                         domain="[('move_id', '=', account_move_id)]")
    account_move_amount = fields.Monetary('Entry Amount', related='account_move_id.amount_total', readonly=True)
    
    # Allocation lines
    allocation_date = fields.Date('Allocation Date', default=fields.Date.context_today, required=True)
    allocation_line_ids = fields.One2many('payment.plan.line.allocation.wizard.line', 'wizard_id', 
                                        string='Allocation Lines')
    notes = fields.Text('Notes')
    
    @api.onchange('payment_plan_id')
    def _onchange_payment_plan(self):
        """When payment plan changes, update lines"""
        self.allocation_line_ids = [(5, 0, 0)]  # Clear existing lines
        if self.payment_plan_id:
            # Create a line for each unpaid payment plan line
            unpaid_lines = self.env['payment.plan.line'].search([
                ('payment_plan_id', '=', self.payment_plan_id.id),
                ('paid', '=', False),
                ('unallocated_amount', '>', 0)
            ], order='date')
            
            vals_list = []
            for line in unpaid_lines:
                vals_list.append((0, 0, {
                    'payment_plan_line_id': line.id,
                    'date': line.date,
                    'name': line.name,
                    'amount_total': line.amount,
                    'allocated_amount': line.allocated_amount,
                    'unallocated_amount': line.unallocated_amount,
                    'amount_to_allocate': 0.0,
                }))
                
            self.allocation_line_ids = vals_list
    
    @api.onchange('account_move_id')
    def _onchange_account_move(self):
        """Clear the account move line when the account move changes"""
        self.account_move_line_id = False
    
    def action_allocate(self):
        """Create allocations based on wizard data"""
        self.ensure_one()
        
        # Total amount being allocated
        total_allocated = sum(line.amount_to_allocate for line in self.allocation_line_ids if line.amount_to_allocate > 0)
        
        if total_allocated <= 0:
            raise ValidationError(_("You must allocate some amount to at least one payment plan line!"))
            
        if total_allocated > self.account_move_amount:
            raise ValidationError(_("Total allocated amount (%s) exceeds the accounting entry amount (%s)!") 
                                % (total_allocated, self.account_move_amount))
        
        # Create allocation records
        allocation_vals = []
        for line in self.allocation_line_ids.filtered(lambda l: l.amount_to_allocate > 0):
            allocation_vals.append({
                'payment_plan_line_id': line.payment_plan_line_id.id,
                'account_move_id': self.account_move_id.id,
                'account_move_line_id': self.account_move_line_id.id if self.account_move_line_id else False,
                'amount': line.amount_to_allocate,
                'allocation_date': self.allocation_date,
                'notes': self.notes,
            })
        
        # Create the allocations
        allocations = self.env['payment.plan.line.allocation'].create(allocation_vals)
        
        # Show the created allocations
        action = {
            'name': _('Created Allocations'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.line.allocation',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', allocations.ids)],
        }
        
        return action


class PaymentPlanLineAllocationWizardLine(models.TransientModel):
    _name = 'payment.plan.line.allocation.wizard.line'
    _description = 'Payment Plan Line Allocation Wizard Line'
    _order = 'date'
    
    wizard_id = fields.Many2one('payment.plan.line.allocation.wizard', string='Wizard', required=True, 
                              ondelete='cascade')
    payment_plan_line_id = fields.Many2one('payment.plan.line', string='Payment Plan Line', required=True)
    date = fields.Date('Due Date', related='payment_plan_line_id.date', readonly=True)
    name = fields.Char('Description', related='payment_plan_line_id.name', readonly=True)
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)
    
    amount_total = fields.Monetary('Total Amount', readonly=True)
    allocated_amount = fields.Monetary('Already Allocated', readonly=True)
    unallocated_amount = fields.Monetary('Remaining Amount', readonly=True)
    amount_to_allocate = fields.Monetary('Allocate', required=True, default=0.0)
    
    @api.onchange('amount_to_allocate')
    def _onchange_amount_to_allocate(self):
        """Validate amount to allocate"""
        if self.amount_to_allocate < 0:
            self.amount_to_allocate = 0
            return {'warning': {'title': _('Warning'), 'message': _('Amount to allocate cannot be negative!')}}
            
        if self.amount_to_allocate > self.unallocated_amount:
            self.amount_to_allocate = self.unallocated_amount
            return {'warning': {'title': _('Warning'), 
                              'message': _('Amount to allocate cannot exceed the unallocated amount!')}}
