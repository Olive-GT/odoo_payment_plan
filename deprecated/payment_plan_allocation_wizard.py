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
    allocation_remaining = fields.Monetary('Remaining to Allocate', compute='_compute_allocation_remaining')
    allocation_used = fields.Monetary('Amount Used', compute='_compute_allocation_remaining')
    allocation_percentage = fields.Float('Allocated %', compute='_compute_allocation_remaining')
    
    # Preselected line from context
    preselect_line_id = fields.Many2one('payment.plan.line', string='Preselected Line')
    
    # Allocation options
    allocation_strategy = fields.Selection([
        ('manual', 'Manual Allocation'),
        ('oldest_first', 'Oldest Due First'),
        ('newest_first', 'Newest Due First'),
        ('proportional', 'Proportional Distribution')
    ], string='Allocation Strategy', default='manual', required=True,
       help="How to distribute the amount among payment lines")
      # Allocation lines
    allocation_date = fields.Date('Allocation Date', default=fields.Date.context_today, required=True)
    allocation_line_ids = fields.One2many('payment.plan.line.allocation.wizard.line', 'wizard_id', 
                                        string='Allocation Lines')
    notes = fields.Text('Notes')
    
    @api.depends('account_move_amount', 'allocation_line_ids.amount_to_allocate')
    def _compute_allocation_remaining(self):
        """Compute remaining amount to allocate and usage statistics"""
        for wizard in self:
            allocated = sum(line.amount_to_allocate for line in wizard.allocation_line_ids)
            wizard.allocation_used = allocated
            wizard.allocation_remaining = wizard.account_move_amount - allocated
            
            # Calculate percentage of amount used
            if wizard.account_move_amount > 0:
                wizard.allocation_percentage = (allocated / wizard.account_move_amount) * 100
            else:
                wizard.allocation_percentage = 0
    
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
            'view_mode': 'list,form',
            'domain': [('id', 'in', allocations.ids)],
        }
        
        return action
        
    def apply_allocation_strategy(self):
        """Apply the selected allocation strategy"""
        self.ensure_one()
        
        # Clear existing allocations
        for line in self.allocation_line_ids:
            line.amount_to_allocate = 0.0
            
        # Get amount to allocate
        amount_remaining = self.account_move_amount
        if amount_remaining <= 0:
            return {'warning': {'title': _('Warning'), 'message': _('No amount available to allocate!')}}
            
        # Apply strategy
        if self.allocation_strategy == 'oldest_first':
            self._apply_oldest_first_strategy(amount_remaining)
        elif self.allocation_strategy == 'newest_first':
            self._apply_newest_first_strategy(amount_remaining)
        elif self.allocation_strategy == 'proportional':
            self._apply_proportional_strategy(amount_remaining)
            
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def _apply_oldest_first_strategy(self, amount_remaining):
        """Apply oldest first allocation strategy"""
        # Sort lines by date (oldest first)
        lines = self.allocation_line_ids.sorted(lambda l: l.date)
        
        for line in lines:
            if amount_remaining <= 0:
                break
                
            if line.unallocated_amount > 0:
                amount_to_allocate = min(line.unallocated_amount, amount_remaining)
                line.amount_to_allocate = amount_to_allocate
                amount_remaining -= amount_to_allocate
    
    def _apply_newest_first_strategy(self, amount_remaining):
        """Apply newest first allocation strategy"""
        # Sort lines by date (newest first)
        lines = self.allocation_line_ids.sorted(lambda l: l.date, reverse=True)
        
        for line in lines:
            if amount_remaining <= 0:
                break
                
            if line.unallocated_amount > 0:
                amount_to_allocate = min(line.unallocated_amount, amount_remaining)
                line.amount_to_allocate = amount_to_allocate
                amount_remaining -= amount_to_allocate
    
    def _apply_proportional_strategy(self, amount_remaining):
        """Apply proportional distribution strategy"""
        # Calculate total unallocated amount
        total_unallocated = sum(line.unallocated_amount for line in self.allocation_line_ids)
        
        if total_unallocated <= 0:
            return
            
        # Distribute proportionally
        for line in self.allocation_line_ids:
            if line.unallocated_amount > 0:
                ratio = line.unallocated_amount / total_unallocated
                amount_to_allocate = min(line.unallocated_amount, amount_remaining * ratio)
                line.amount_to_allocate = round(amount_to_allocate, 2)
                
        # Adjust for rounding errors - allocate remaining to first line with space
        recalculated_allocated = sum(line.amount_to_allocate for line in self.allocation_line_ids)
        if recalculated_allocated < amount_remaining:
            remaining_diff = amount_remaining - recalculated_allocated
            for line in self.allocation_line_ids:
                if line.amount_to_allocate + remaining_diff <= line.unallocated_amount:
                    line.amount_to_allocate += remaining_diff
                    break
                    
    def action_distribute_evenly(self):
        """Distribute the amount evenly across all lines"""
        self.ensure_one()
        
        # Count lines with unallocated amounts
        eligible_lines = self.allocation_line_ids.filtered(lambda l: l.unallocated_amount > 0)
        if not eligible_lines:
            return {'warning': {'title': _('Warning'), 'message': _('No eligible lines for allocation!')}}
            
        # Calculate even distribution
        amount_per_line = self.account_move_amount / len(eligible_lines)
        
        # Clear existing allocations
        for line in self.allocation_line_ids:
            line.amount_to_allocate = 0.0
            
        # Allocate evenly
        amount_remaining = self.account_move_amount
        for line in eligible_lines:
            if amount_remaining <= 0:
                break
                
            amount_to_allocate = min(line.unallocated_amount, amount_per_line)
            line.amount_to_allocate = amount_to_allocate
            amount_remaining -= amount_to_allocate
            
        # Allocate any remainder to the first eligible line
        if amount_remaining > 0:
            for line in eligible_lines:
                if line.amount_to_allocate + amount_remaining <= line.unallocated_amount:
                    line.amount_to_allocate += amount_remaining
                    break
                    
        return {'type': 'ir.actions.client', 'tag': 'reload'}
        
    def action_clear_all(self):
        """Clear all allocations"""
        self.ensure_one()
        
        for line in self.allocation_line_ids:
            line.amount_to_allocate = 0.0
            
        return {'type': 'ir.actions.client', 'tag': 'reload'}


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
    allocation_percentage = fields.Float('Allocation %', compute='_compute_allocation_percentage', store=True)
    allocation_visual = fields.Float('Allocation Visual', compute='_compute_allocation_percentage', store=True)
    
    @api.depends('amount_to_allocate', 'amount_total')
    def _compute_allocation_percentage(self):
        """Calculate what percentage of the line is being allocated"""
        for line in self:
            if line.amount_total > 0:
                total_allocated = line.allocated_amount + line.amount_to_allocate
                line.allocation_percentage = total_allocated / line.amount_total
            else:
                line.allocation_percentage = 0
                
    def set_max_allocation(self):
        """Set the maximum allocation amount"""
        for line in self:
            line.amount_to_allocate = line.unallocated_amount
        return {'type': 'ir.actions.client', 'tag': 'reload'}
        
    def clear_allocation(self):
        """Clear the allocation amount"""
        for line in self:
            line.amount_to_allocate = 0
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
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
