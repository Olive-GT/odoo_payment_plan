from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


class PaymentPlan(models.Model):
    _name = 'payment.plan'
    _description = 'Payment Plan'
    _order = 'id desc'
    
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
    interest_rate = fields.Float(string='Annual Interest Rate (%)', default=10.0, 
                               help="Annual interest rate for overdue payments")
    notes = fields.Text('Notes')

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

    def action_post(self):
        for plan in self:
            if plan.state == 'draft':
                plan.state = 'posted'
                
    def action_cancel(self):
        for plan in self:
            if plan.state != 'canceled':
                plan.state = 'canceled'
                
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
            self.line_ids._compute_overdue_days()
            self.line_ids._compute_interest_amount()
        return True
