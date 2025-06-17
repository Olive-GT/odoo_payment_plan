from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare


class PaymentPlanReconciliation(models.Model):
    _name = 'payment.plan.reconciliation'
    _description = 'Payment Plan Reconciliation'
    _order = 'id desc'
    payment_plan_line_id = fields.Many2one(
        'payment.plan.line', 
        string='Payment Plan Line',
        required=True, 
        ondelete='cascade'
    )
    move_line_id = fields.Many2one(
        'account.move.line', 
        string='Journal Item',
        required=True, 
        ondelete='restrict',
        domain="[('id', 'in', available_move_line_ids)]",
    )
    
    available_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_available_move_lines',
        string='Available Journal Items'
    )
    payment_plan_id = fields.Many2one(
        related='payment_plan_line_id.payment_plan_id',
        store=True,
        string='Payment Plan'
    )
    partner_id = fields.Many2one(        related='payment_plan_id.partner_id',
        store=True,
        string='Partner'
    )
    amount = fields.Monetary(
        string='Allocated Amount',
        required=True,
        help='Amount allocated to this payment plan line'
    )
    currency_id = fields.Many2one(
        related='payment_plan_line_id.currency_id',
        string='Currency'
    )
    date = fields.Date(
        string='Date',
        default=lambda self: fields.Date.context_today(self),
        required=True,
        help="Date of reconciliation. Always matches the journal entry date."
    )
    company_id = fields.Many2one(
        related='payment_plan_id.company_id',
        string='Company',
        store=True
    )
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        string='Journal Entry',
        store=True
    )
    journal_id = fields.Many2one(
        related='move_id.journal_id',
        string='Journal',
        store=True
    )
    move_date = fields.Date(
        related='move_id.date',
        string='Entry Date',
        store=True
    )
    move_payment_reference = fields.Char(
        related='move_id.ref',
        string='Payment Reference',
        store=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled')
    ], default='draft', string='Status', required=True)
    
    # Campos relacionados para mostrar información de mora
    overdue_days = fields.Integer(
        related='payment_plan_line_id.overdue_days',
        string='Overdue Days',
        readonly=True
    )
    interest_amount = fields.Monetary(
        related='payment_plan_line_id.interest_amount',
        string='Interest Amount',
        readonly=True
    )
    total_with_interest = fields.Monetary(
        related='payment_plan_line_id.total_with_interest',
        string='Total with Interest',
        readonly=True
    )
    
    @api.constrains('amount')
    def _check_amount(self):
        """Ensure allocated amount is positive and not zero"""
        for rec in self:
            if float_is_zero(rec.amount, precision_rounding=rec.currency_id.rounding):
                raise ValidationError(_("Allocated amount cannot be zero."))
            if float_compare(rec.amount, 0.0, precision_rounding=rec.currency_id.rounding) <= 0:
                raise ValidationError(_("Allocated amount must be positive."))
    
    @api.constrains('move_line_id', 'amount')
    def _check_available_amount(self):
        """Ensure allocated amount doesn't exceed available amount in move line"""
        for rec in self:
            # Get all allocations for this move line
            allocations = self.search([
                ('move_line_id', '=', rec.move_line_id.id),
                ('state', '!=', 'cancelled'),
                ('id', '!=', rec.id)  # Exclude current record
            ])
            
            # Calculate already allocated amount
            allocated_amount = sum(allocations.mapped('amount'))
            
            # Calculate available amount from move line (debit or credit)
            available_amount = abs(rec.move_line_id.balance)
            
            # Check if allocation exceeds available amount
            if float_compare(allocated_amount + rec.amount, available_amount, 
                           precision_rounding=rec.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Cannot allocate more than the available amount.\n"
                    "Available: %(available).2f\n"
                    "Already allocated: %(allocated).2f\n"
                    "This allocation: %(amount).2f"
                ) % {
                    'available': available_amount,
                    'allocated': allocated_amount,
                    'amount': rec.amount
                })
    
    @api.constrains('payment_plan_line_id', 'amount')
    def _check_payment_plan_line_amount(self):
        """Ensure allocations don't exceed the payment plan line amount"""
        for rec in self:
            # Get all allocations for this payment plan line
            allocations = self.search([
                ('payment_plan_line_id', '=', rec.payment_plan_line_id.id),
                ('state', '!=', 'cancelled'),
                ('id', '!=', rec.id)  # Exclude current record
            ])
            
            # Calculate already allocated amount
            allocated_amount = sum(allocations.mapped('amount'))
            
            # Check if allocation exceeds line amount
            plan_line_amount = rec.payment_plan_line_id.amount
            if float_compare(allocated_amount + rec.amount, plan_line_amount, 
                           precision_rounding=rec.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Cannot allocate more than the payment plan line amount.\n"
                    "Line amount: %(line).2f\n"
                    "Already allocated: %(allocated).2f\n"
                    "This allocation: %(amount).2f"
                ) % {
                    'line': plan_line_amount,
                    'allocated': allocated_amount,
                    'amount': rec.amount
                })
    
    @api.constrains('date', 'move_date')
    def _check_date_match(self):
        """Ensure reconciliation date matches the journal entry date"""
        for rec in self:
            if rec.date != rec.move_date:
                raise ValidationError(_("The reconciliation date must match the journal entry date."))
                
    def action_confirm(self):
        """Confirm the reconciliation"""
        for rec in self:
            # Update state
            rec.state = 'confirmed'
            
            # Update payment plan line
            line = rec.payment_plan_line_id
            
            # Check if line is fully reconciled
            all_confirmed_allocations = self.search([
                ('payment_plan_line_id', '=', line.id),
                ('state', '=', 'confirmed')
            ])
            
            total_allocated = sum(all_confirmed_allocations.mapped('amount'))
            
            # Get payment date from the most recent allocation
            latest_allocation = all_confirmed_allocations.sorted(
                key=lambda r: r.date, reverse=True)[0]
            
            # Set payment reference from allocations
            references = list(filter(None, all_confirmed_allocations.mapped('move_payment_reference')))
            payment_reference = ', '.join(references[:3])
            if len(references) > 3:
                payment_reference += f' (+{len(references) - 3})'
            
            # First update the payment date - this should trigger recalculations in Odoo 18
            line.write({
                'payment_date': latest_allocation.date,
                'payment_reference': payment_reference
            })
            
            # Now that date is updated, fetch the fresh values with recalculated interest
            line.invalidate_cache()
            line = line.with_context(force_refresh=True).browse(line.id)
            
            # Check if there's overdue interest to consider
            required_amount = line.total_with_interest if line.overdue_days > 0 else line.amount
            
            # If allocations cover the full amount (including interest if applicable), mark as paid
            precision = self.env['decimal.precision'].precision_get('Payment')
            if float_compare(total_allocated, required_amount, precision_digits=precision) >= 0 and not line.paid:
                line.mark_as_paid()
    def action_cancel(self):
        """Cancel the reconciliation"""
        for rec in self:
            # Update state
            rec.state = 'cancelled'
            
            # Check if line is marked as paid and needs to be reversed
            line = rec.payment_plan_line_id
            if line.paid:
                # Check if there are any remaining confirmed allocations
                remaining_allocations = self.search([
                    ('payment_plan_line_id', '=', line.id),
                    ('state', '=', 'confirmed'),
                    ('id', '!=', rec.id)
                ])
                total_allocated = sum(remaining_allocations.mapped('amount'))
                  # If remaining allocations don't cover full amount, mark as unpaid
                precision = self.env['decimal.precision'].precision_get('Payment')
                if float_compare(total_allocated, line.amount, 
                              precision_digits=precision) < 0:
                    line.mark_as_unpaid()
    
    def action_draft(self):
        """Reset to draft state"""
        for rec in self:
            rec.state = 'draft'
    
    @api.model
    def create(self, vals):
        """Override create to set the date to match move date"""
        if vals.get('move_line_id'):
            move_line = self.env['account.move.line'].browse(vals.get('move_line_id'))
            if move_line and move_line.move_id.date:
                vals['date'] = move_line.move_id.date
        elif not vals.get('date'):
            vals['date'] = fields.Date.context_today(self)
        return super().create(vals)
    
    @api.depends('partner_id')
    def _compute_available_move_lines(self):
        """Compute available move lines for reconciliation based on filters"""
        for rec in self:
            domain = [
                ('account_id.reconcile', '=', True),
                ('reconciled', '=', False),
                ('account_id.account_type', 'in', ['asset_cash', 'asset_liquidity']),
                ('debit', '>', 0.0)
            ]
            
            # Add partner filter if we have one
            if rec.partner_id:
                domain.append(('partner_id', '=', rec.partner_id.id))
                
            # Get move lines that match the domain
            move_lines = self.env['account.move.line'].search(domain)
            rec.available_move_line_ids = move_lines
            
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """When partner changes, recompute available move lines"""
        self._compute_available_move_lines()

    @api.onchange('move_line_id')
    def _onchange_move_line_id(self):
        """When move line changes, set date to match move date"""
        for rec in self:
            if rec.move_line_id and rec.move_line_id.move_id.date:
                rec.date = rec.move_line_id.move_id.date
