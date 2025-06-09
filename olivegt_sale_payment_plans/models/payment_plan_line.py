from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


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

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_('Amount must be positive!'))

    def mark_as_paid(self):
        for line in self:
            line.paid = True
            line.payment_date = fields.Date.context_today(self)

    def mark_as_unpaid(self):
        for line in self:
            line.paid = False
            line.payment_date = False
            line.payment_reference = False