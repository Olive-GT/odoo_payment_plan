from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero


class PaymentPlanReconciliationWizardLine(models.TransientModel):
    _name = 'payment.plan.reconciliation.wizard.line'
    _description = 'Payment Plan Reconciliation Wizard Line'
    
    wizard_id = fields.Many2one(
        'payment.plan.reconciliation.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    move_line_id = fields.Many2one(
        'account.move.line',
        string='Journal Item',
        required=True,
        # Domain is now handled in the view with filter_domain
    )
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        string='Journal Entry',
        store=False
    )
    date = fields.Date(
        related='move_id.date',
        string='Date',
        store=False
    )
    journal_id = fields.Many2one(
        related='move_id.journal_id',
        string='Journal',
        store=False
    )
    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
        string='Currency',
        store=False
    )
    payment_reference = fields.Char(
        related='move_id.payment_reference',
        string='Reference',
        store=False
    )
    partner_id = fields.Many2one(
        related='move_id.partner_id',
        string='Partner',
        store=False
    )
    amount = fields.Monetary(
        string='Amount',
        help='Amount to allocate from this journal item'
    )
    available_amount = fields.Monetary(
        string='Available',
        compute='_compute_available',
        help='Available amount that can be allocated'
    )
    original_amount = fields.Monetary(
        string='Original',
        compute='_compute_available',
        help='Original amount of the journal item'
    )
    
    @api.onchange('move_line_id')
    @api.depends('move_line_id')
    def _compute_available(self):
        for line in self:
            if not line.move_line_id:
                line.available_amount = 0.0
                line.original_amount = 0.0
                continue
                
            # Calculate original amount from move line
            line.original_amount = abs(line.move_line_id.balance)
            
            # Find existing reconciliations for this move line
            reconciliations = self.env['payment.plan.reconciliation'].search([
                ('move_line_id', '=', line.move_line_id.id),
                ('state', '=', 'confirmed')
            ])
            allocated = sum(reconciliations.mapped('amount'))
            
            # Available amount is original minus allocated
            line.available_amount = line.original_amount - allocated
            
            # If no amount is set, default to available amount
            if not line.amount:
                line.amount = min(line.available_amount, line.wizard_id.remaining_to_allocate)
    
    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if float_compare(line.amount, 0.0, precision_rounding=line.currency_id.rounding) < 0:
                raise ValidationError(_("Amount must be positive."))
                
            if float_compare(line.amount, line.available_amount, 
                          precision_rounding=line.currency_id.rounding) > 0:
                raise ValidationError(_("Cannot allocate more than the available amount."))


class PaymentPlanReconciliationWizard(models.TransientModel):
    _name = 'payment.plan.reconciliation.wizard'
    _description = 'Payment Plan Reconciliation Wizard'
    
    payment_plan_id = fields.Many2one(
        'payment.plan',
        string='Payment Plan',
        required=True,
        ondelete='cascade'
    )
    payment_plan_line_id = fields.Many2one(
        'payment.plan.line',
        string='Payment Plan Line',
        required=True,
        domain="[('payment_plan_id', '=', payment_plan_id)]",
        ondelete='cascade'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        related='payment_plan_id.partner_id',
        store=False
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='payment_plan_id.currency_id',
        store=False
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='payment_plan_id.company_id',
        store=False
    )
    date = fields.Date(
        string='Date',
        default=lambda self: fields.Date.context_today(self),
        required=True
    )
    line_amount = fields.Monetary(
        string='Line Amount',
        related='payment_plan_line_id.amount',
        store=False
    )    # We're using a different approach to show existing reconciliations
    allocated_amount = fields.Monetary(
        string='Already Allocated',
        related='payment_plan_line_id.allocated_amount',
        store=False
    )
    remaining_amount = fields.Monetary(
        string='Remaining to Allocate',
        compute='_compute_remaining',
        store=True
    )
    wizard_line_ids = fields.One2many(
        'payment.plan.reconciliation.wizard.line',
        'wizard_id',
        string='Allocations'
    )
    total_allocation = fields.Monetary(
        string='Total Allocation',
        compute='_compute_total',
        store=True
    )
    remaining_to_allocate = fields.Monetary(
        string='Remaining After This Allocation',
        compute='_compute_total',
        store=True
    )
    
    @api.depends('payment_plan_line_id', 'allocated_amount', 'line_amount')
    def _compute_remaining(self):
        for wizard in self:
            if wizard.payment_plan_line_id:
                wizard.remaining_amount = wizard.line_amount - wizard.allocated_amount
            else:
                wizard.remaining_amount = 0.0
    
    @api.depends('wizard_line_ids.amount', 'remaining_amount')
    def _compute_total(self):
        for wizard in self:
            wizard.total_allocation = sum(wizard.wizard_line_ids.mapped('amount'))
            wizard.remaining_to_allocate = wizard.remaining_amount - wizard.total_allocation    # The action_add_allocation_line method has been removed as it's redundant with the editable list view    def get_existing_reconciliations(self):
        """Get existing reconciliations for the current payment plan line"""
        self.ensure_one()
        if self.payment_plan_line_id:
            return self.env['payment.plan.reconciliation'].search([
                ('payment_plan_line_id', '=', self.payment_plan_line_id.id),
                ('state', '=', 'confirmed')
            ])
        return self.env['payment.plan.reconciliation']
        
    def action_view_existing_reconciliations(self):
        """Open a window with the existing reconciliations"""
        self.ensure_one()
        
        reconciliations = self.get_existing_reconciliations()
        if not reconciliations:
            raise ValidationError(_("No existing reconciliations found for this payment plan line."))
        
        action = self.env["ir.actions.actions"]._for_xml_id("olivegt_sale_payment_plans.action_payment_plan_reconciliation")
        action['domain'] = [('id', 'in', reconciliations.ids)]
        action['context'] = {'create': False}
        action['name'] = _('Previous Allocations for %s') % self.payment_plan_line_id.display_name
        
        if len(reconciliations) == 1:
            action['views'] = [(self.env.ref('olivegt_sale_payment_plans.payment_plan_reconciliation_view_form').id, 'form')]
            action['res_id'] = reconciliations.id
            
        return action
    def action_confirm(self):
        """Confirm the reconciliations"""
        self.ensure_one()
        
        # Validation
        if float_compare(self.total_allocation, 0.0, 
                      precision_rounding=self.currency_id.rounding) <= 0:
            raise ValidationError(_("Nothing to allocate. Please add allocation lines."))
        
        # Create reconciliations
        reconciliations = []
        for line in self.wizard_line_ids:
            if float_is_zero(line.amount, precision_rounding=self.currency_id.rounding):
                continue
                
            reconciliation = self.env['payment.plan.reconciliation'].create({
                'payment_plan_id': self.payment_plan_id.id,
                'payment_plan_line_id': self.payment_plan_line_id.id,
                'move_line_id': line.move_line_id.id,
                'amount': line.amount,
                'date': self.date,
                'state': 'draft',
            })
            reconciliations.append(reconciliation.id)
            
            # Confirm the reconciliation
            reconciliation.action_confirm()
          # Show result
        if reconciliations:
            return {
                'name': _('Reconciliations'),
                'type': 'ir.actions.act_window',
                'res_model': 'payment.plan.reconciliation',
                'view_mode': 'list,form',
                'domain': [('id', 'in', reconciliations)],
            }
        else:
            return {'type': 'ir.actions.act_window_close'}
