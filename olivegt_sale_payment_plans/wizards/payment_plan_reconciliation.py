from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero


class PaymentPlanReconciliationWizardLine(models.TransientModel):
    _name = 'payment.plan.reconciliation.wizard.line'
    _description = 'Payment Plan Reconciliation Wizard Line'
    
    wizard_id = fields.Many2one(
        'payment.plan.reconciliation.wizard',
        string='Wizard',        required=True,
        ondelete='cascade'
    )
    
    move_line_id = fields.Many2one(
        'account.move.line',
        string='Journal Item'
    )
    
    is_readonly = fields.Boolean(
        string='Is Readonly',
        default=False,
        help='True if this line represents an existing allocation'
    )
    
    existing_reconciliation_id = fields.Many2one(
        'payment.plan.reconciliation',
        string='Existing Reconciliation',
        help='Reference to the existing reconciliation record if this is a historical entry'
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
            
            # For existing reconciliations, show the allocated amount correctly
            if line.is_readonly and line.existing_reconciliation_id:
                line.original_amount = abs(line.move_line_id.balance)
                line.available_amount = 0.0  # No available amount for existing reconciliations
                continue
                
            # Calculate original amount from move line
            line.original_amount = abs(line.move_line_id.balance)
            
            # Find existing reconciliations for this move line
            reconciliations = self.env['payment.plan.reconciliation'].search([
                ('move_line_id', '=', line.move_line_id.id),
                ('state', '=', 'confirmed')
            ])
            allocated = sum(reconciliations.mapped('amount'))            # Available amount is original minus allocated
            line.available_amount = line.original_amount - allocated
            # If no amount is set and it's not a readonly line, default to available amount
            if not line.amount and not line.is_readonly:
                line.amount = min(line.available_amount, line.wizard_id.remaining_to_allocate)
    
    @api.onchange('move_line_id')
    def _onchange_move_line_id(self):
        """When move_line_id changes, automatically set the amount to the lesser of 
        available amount or remaining to allocate"""
        for line in self:
            if line.move_line_id and not line.is_readonly:
                # First ensure available amount is calculated
                line._compute_available()                # Then set the amount based on availability and remaining to allocate
                if line.wizard_id and line.available_amount > 0:
                    line.amount = min(line.available_amount, line.wizard_id.remaining_to_allocate)
    
    @api.model
    def create(self, values):
        """Override create to make move_line_id validation conditional"""
        # If we're creating an empty line (for UI purposes), don't validate move_line_id
        if 'move_line_id' not in values and not values.get('is_readonly', False):
            # This is an empty line being created, likely through the "Add Line" button
            return super(PaymentPlanReconciliationWizardLine, self).create(values)
        return super(PaymentPlanReconciliationWizardLine, self).create(values)

    @api.constrains('amount', 'is_readonly')
    def _check_amount(self):
        for line in self:
            # Skip validation for readonly lines or lines without move_line_id
            if line.is_readonly or not line.move_line_id:
                continue
                
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
        related='payment_plan_line_id.total_with_interest',
        store=False
    )
    
    # We're using a different approach to show existing reconciliations
    
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
    
    @api.depends('wizard_line_ids.amount', 'remaining_amount', 'wizard_line_ids.is_readonly')
    def _compute_total(self):
        for wizard in self:
            # Only sum new allocations (non-readonly lines) for the total
            non_readonly_lines = wizard.wizard_line_ids.filtered(lambda line: not line.is_readonly)
            wizard.total_allocation = sum(non_readonly_lines.mapped('amount'))
            wizard.remaining_to_allocate = wizard.remaining_amount - wizard.total_allocation
    
    # The action_add_allocation_line method has been removed as it's redundant with the editable list view
    def _get_existing_reconciliations(self):
        """Get existing reconciliations for the current payment plan line"""
        self.ensure_one()
        if self.payment_plan_line_id:
            return self.env['payment.plan.reconciliation'].search([
                ('payment_plan_line_id', '=', self.payment_plan_line_id.id),
                ('state', '=', 'confirmed')
            ])
        return self.env['payment.plan.reconciliation']
        
    def default_get(self, fields_list):
        """Override default_get to ensure existing reconciliations are loaded"""
        res = super(PaymentPlanReconciliationWizard, self).default_get(fields_list)
        # If payment_plan_line_id is already in the context, preload the existing reconciliations
        if 'payment_plan_line_id' in res:
            payment_plan_line = self.env['payment.plan.line'].browse(res['payment_plan_line_id'])
            if payment_plan_line:
                res['payment_plan_id'] = payment_plan_line.payment_plan_id.id
        return res
        
    @api.model
    def create(self, vals):
        """Override create to populate existing reconciliations as wizard lines"""
        res = super(PaymentPlanReconciliationWizard, self).create(vals)
        # After creating the wizard, load existing reconciliations as read-only lines
        if res.payment_plan_line_id:
            res._load_existing_reconciliations()
        return res
        
    @api.onchange('payment_plan_line_id')
    def _onchange_payment_plan_line_id(self):
        """When the payment plan line changes, load its existing reconciliations"""
        if self.payment_plan_line_id:
            # Using command pattern to update wizard lines
            self.ensure_one()
            commands = [(5, 0, 0)]  # Clear existing lines
            existing_reconciliations = self._get_existing_reconciliations()
            
            for rec in existing_reconciliations:
                # Add existing reconciliation as a wizard line with create command
                commands.append((0, 0, {
                    'move_line_id': rec.move_line_id.id,
                    'amount': rec.amount,
                    'is_readonly': True,
                    'existing_reconciliation_id': rec.id,
                }))
            
            # Update move lines cache to ensure our payment_plan_available_amount is calculated
            if self.partner_id:
                move_lines = self.env['account.move.line'].search([
                    ('account_id.reconcile', '=', True),
                    ('partner_id', '=', self.partner_id.id)
                ])
                move_lines._compute_payment_plan_available_amount()
            
            self.wizard_line_ids = commands
            
    def _load_existing_reconciliations(self):
        """Helper method to load existing reconciliations as wizard lines"""
        self.ensure_one()
        existing_reconciliations = self._get_existing_reconciliations()
        for rec in existing_reconciliations:
            vals = {
                'wizard_id': self.id,
                'move_line_id': rec.move_line_id.id,
                'amount': rec.amount,                'is_readonly': True,
                'existing_reconciliation_id': rec.id,
            }
            self.env['payment.plan.reconciliation.wizard.line'].create(vals)
      # Removed the action_view_existing_reconciliations method as existing
    # reconciliations are now displayed directly in the wizard table
    
    def action_add_line(self):
        """Add a new empty line to the wizard"""
        self.ensure_one()
        
        # Create a new wizard with the same data but with a fresh state
        new_wizard = self.env['payment.plan.reconciliation.wizard'].create({
            'payment_plan_id': self.payment_plan_id.id,
            'payment_plan_line_id': self.payment_plan_line_id.id,
            'date': self.date,
        })
        
        # Load existing reconciliations
        new_wizard._load_existing_reconciliations()
        
        # Return the new wizard view
        return {
            'name': _('Reconcile Payment Plan Line'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.reconciliation.wizard',
            'view_mode': 'form',
            'res_id': new_wizard.id,
            'target': 'new',            'context': {'default_payment_plan_id': self.payment_plan_id.id,
                        'default_payment_plan_line_id': self.payment_plan_line_id.id},
        }
    
    def action_confirm(self):
        """Confirm the reconciliations"""
        self.ensure_one()
        
        # Only process lines that have a move_line_id set
        valid_lines = self.wizard_line_ids.filtered(lambda l: l.move_line_id and not l.is_readonly)
        
        # Validation 
        if not valid_lines or float_compare(sum(valid_lines.mapped('amount')), 0.0, 
                      precision_rounding=self.currency_id.rounding) <= 0:
            raise ValidationError(_("Nothing to allocate. Please add allocation lines and select journal items."))
        
        # Create reconciliations
        reconciliations = []
        for line in valid_lines:
                
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
            reconciliation.action_confirm()            # Reload the wizard for further allocations if there's still an amount to allocate
            if float_compare(self.line_amount, self.allocated_amount + sum(r.amount for r in self.env['payment.plan.reconciliation'].browse(reconciliations)), 
                         precision_rounding=self.currency_id.rounding) > 0:
                # There's still an amount to allocate, create a fresh wizard with same data
                new_wizard = self.env['payment.plan.reconciliation.wizard'].create({
                    'payment_plan_id': self.payment_plan_id.id,
                    'payment_plan_line_id': self.payment_plan_line_id.id,
                    'date': self.date,
                })
                # Load existing reconciliations in the new wizard
                new_wizard._load_existing_reconciliations()
                
                # Return the new wizard view
                return {
                    'name': _('Reconcile Payment Plan Line'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'payment.plan.reconciliation.wizard',
                    'view_mode': 'form',
                    'res_id': new_wizard.id,
                    'target': 'new',
                    'context': self.env.context,
                }
            # Show result if fully allocated or no more allocations needed
            elif reconciliations:
                return {
                    'name': _('Reconciliations'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'payment.plan.reconciliation',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', reconciliations)],
                }
            else:
                return {'type': 'ir.actions.act_window_close'}
    
    @api.onchange('partner_id')
    def _onchange_partner_filter_move_lines(self):
        """Filter move lines based on criteria when partner changes"""
        return {
            'domain': {
                'move_line_id': [
                    ('account_id.reconcile', '=', True),
                    ('reconciled', '=', False),
                    ('account_id.account_type', 'in', ['asset_cash', 'asset_liquidity']),
                    ('debit', '>', 0.0),
                    ('partner_id', '=', self.partner_id.id if self.partner_id else False),
                ]
            }
        }
