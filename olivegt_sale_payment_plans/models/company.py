from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payment_plan_receipt_bg_url = fields.Char(
        string='Payment Plan Receipt Background URL',
        help='Background image URL used in the payment plan allocation receipt PDF.',
    )