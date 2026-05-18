from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payment_plan_receipt_bg_url = fields.Char(
        string='Payment Plan Receipt Background URL',
        compute='_compute_payment_plan_receipt_bg_url',
        inverse='_inverse_payment_plan_receipt_bg_url',
        help='Background image URL used in the payment plan allocation receipt PDF.',
    )

    def _get_payment_plan_receipt_bg_url_key(self):
        self.ensure_one()
        return f'olivegt_sale_payment_plans.payment_plan_receipt_bg_url.{self.id}'

    def _compute_payment_plan_receipt_bg_url(self):
        config = self.env['ir.config_parameter'].sudo()
        for company in self:
            company.payment_plan_receipt_bg_url = config.get_param(
                company._get_payment_plan_receipt_bg_url_key(),
                default='',
            )

    def _inverse_payment_plan_receipt_bg_url(self):
        config = self.env['ir.config_parameter'].sudo()
        for company in self:
            key = company._get_payment_plan_receipt_bg_url_key()
            if company.payment_plan_receipt_bg_url:
                config.set_param(key, company.payment_plan_receipt_bg_url)
            else:
                config.search([('key', '=', key)]).unlink()