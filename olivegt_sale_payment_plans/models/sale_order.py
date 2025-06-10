from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_plan_ids = fields.One2many('payment.plan', 'sale_id', string='Payment Plans')
    payment_plan_count = fields.Integer(string='Payment Plans', compute='_compute_payment_plan_count')

    @api.depends('payment_plan_ids')
    def _compute_payment_plan_count(self):
        for order in self:
            order.payment_plan_count = len(order.payment_plan_ids)

    def action_create_payment_plan(self):
        self.ensure_one()
        return {
            'name': _('Create Payment Plan'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan',
            'view_mode': 'form',
            'context': {
                'default_sale_id': self.id,
            },
        }    def action_view_payment_plans(self):
        self.ensure_one()
        return {
            'name': _('Payment Plans'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan',
            'view_mode': 'list,form',
            'domain': [('sale_id', '=', self.id)],
            'context': {
                'default_sale_id': self.id,
            },
        }
