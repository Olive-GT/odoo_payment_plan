from odoo import models, api, fields
from odoo.tools import format_date
from odoo.tools.misc import formatLang


class PaymentPlanReport(models.AbstractModel):
    _name = 'report.olivegt_sale_payment_plans.report_payment_plan'
    _description = 'Payment Plan Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['payment.plan'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'payment.plan',
            'docs': docs,
            'today': fields.Date.context_today(self),
            'format_date': format_date,
            'formatLang': formatLang,
        }