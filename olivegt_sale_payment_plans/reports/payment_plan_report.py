from odoo import models, api


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
        }