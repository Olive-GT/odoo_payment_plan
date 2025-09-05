from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


class PaymentPlan(models.Model):
    _name = 'payment.plan'
    _description = 'Payment Plan'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    sale_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='sale_id.partner_id', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', related='sale_id.currency_id', store=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many('payment.plan.line', 'payment_plan_id', string='Payment Plan Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('canceled', 'Canceled'),
    ], string='Status', default='draft', tracking=True)
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_amounts', store=True)
    amount_paid = fields.Monetary(string='Amount Paid', compute='_compute_amounts', store=True)
    amount_residual = fields.Monetary(string='Amount Due', compute='_compute_amounts', store=True)
    total_interest = fields.Monetary(string='Total Interest', compute='_compute_amounts', store=True)
    total_with_interest = fields.Monetary(string='Total with Interest', compute='_compute_amounts', store=True)
    interest_calculation_method = fields.Selection([
        ('percentage', 'Monthly Percentage'),
        ('fixed', 'Fixed Monthly Amount')
    ], string='Interest Calculation Method', default='percentage', required=True,
       help="Method used to calculate interest on overdue payments")
    interest_rate = fields.Float(string='Monthly Interest Rate (%)', default=1.0, 
                               help="Monthly interest rate for overdue payments (calculated daily)")
    fixed_interest_amount = fields.Monetary(string='Fixed Monthly Interest Amount', default=0.0,
                                         help="Fixed amount to charge per month for overdue payments")
    notes = fields.Text('Notes')

    # Allocation statistics
    line_count = fields.Integer(string='Total Lines', compute='_compute_allocation_statistics')
    fully_allocated_lines_count = fields.Integer(string='Fully Allocated Lines', compute='_compute_allocation_statistics')
    partially_allocated_lines_count = fields.Integer(string='Partially Allocated Lines', compute='_compute_allocation_statistics')
    unallocated_lines_count = fields.Integer(string='Unallocated Lines', compute='_compute_allocation_statistics')
    allocation_progress = fields.Float(string='Allocation Progress', compute='_compute_allocation_statistics')
    allocation_ids = fields.One2many('payment.plan.line.allocation', compute='_compute_all_allocations', string='All Allocations')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('payment.plan') or _('New')
        return super().create(vals_list)
    
    @api.depends('line_ids.amount', 'line_ids.paid', 'line_ids.interest_amount')
    def _compute_amounts(self):
        for plan in self:
            plan.total_amount = sum(plan.line_ids.mapped('amount'))
            plan.amount_paid = sum(plan.line_ids.filtered(lambda l: l.paid).mapped('amount'))
            plan.amount_residual = plan.total_amount - plan.amount_paid
            plan.total_interest = sum(plan.line_ids.mapped('interest_amount'))
            plan.total_with_interest = plan.total_amount + plan.total_interest

    @api.depends('line_ids.allocated_amount', 'line_ids.is_fully_allocated')
    def _compute_allocation_statistics(self):
        """Compute statistics for allocation dashboard"""
        for plan in self:
            plan.line_count = len(plan.line_ids)
            
            plan.fully_allocated_lines_count = len(plan.line_ids.filtered(lambda l: l.is_fully_allocated))
            
            # Lines with some allocation but not fully allocated
            partially_allocated_lines = plan.line_ids.filtered(
                lambda l: not l.is_fully_allocated and l.allocated_amount > 0
            )
            plan.partially_allocated_lines_count = len(partially_allocated_lines)
            
            # Lines with no allocations
            plan.unallocated_lines_count = len(plan.line_ids.filtered(lambda l: l.allocated_amount <= 0))
            
            # Calculate overall allocation progress as percentage
            if plan.total_amount > 0:
                total_allocated = sum(plan.line_ids.mapped('allocated_amount'))
                plan.allocation_progress = total_allocated / plan.total_amount
            else:
                plan.allocation_progress = 0.0

    def action_post(self):
        for plan in self:
            if plan.state == 'draft':
                plan.state = 'posted'
                
    def action_update_overdue(self):
        """Update overdue days and interest for all lines in this payment plan"""
        for plan in self:
            plan.line_ids.update_overdue_status()
        return True
                
    def action_cancel(self):
        for plan in self:
            if plan.state != 'canceled':
                plan.state = 'canceled'
                
    def action_refresh_allocation_stats(self):
        """Refresh allocation statistics manually"""
        self.ensure_one()
        self._compute_allocation_statistics()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
        
    def action_view_allocations(self):
        """View all allocations for this payment plan"""
        self.ensure_one()
        
        # Collect all allocation IDs
        allocation_ids = []
        for line in self.line_ids:
            allocation_ids.extend(line.allocation_ids.ids)
            
        return {
            'name': _('Payment Allocations'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.line.allocation',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', allocation_ids)],
            'context': {'default_payment_plan_id': self.id},
        }
                
    def print_payment_plan(self):
        self.ensure_one()
        return self.env.ref('olivegt_sale_payment_plans.action_report_payment_plan').report_action(self)
    
    def action_draft(self):
        for plan in self:
            if plan.state == 'canceled':
                plan.state = 'draft'
    
    def action_calculate_payment_plan(self):
        self.ensure_one()
        return {
            'name': _('Payment Plan Calculator'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan.calculator.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_plan_id': self.id,
                'default_total_amount': self.sale_id.amount_total,
            }
        }
    
    def update_overdue_status(self):
        """Update overdue days and interest for all lines in this payment plan"""
        self.ensure_one()
        if self.line_ids:
            # Use the update_overdue_status method on the lines instead of compute methods
            # This respects manually edited values
            self.line_ids.update_overdue_status(respect_manual_edits=True)
        return True
        
    @api.depends('line_ids.allocation_ids')
    def _compute_all_allocations(self):
        """Compute all allocations for this payment plan"""
        for plan in self:
            plan.allocation_ids = plan.line_ids.mapped('allocation_ids')
