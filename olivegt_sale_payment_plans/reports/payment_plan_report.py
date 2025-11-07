import re

from odoo import models, api, fields
from odoo.tools import format_date


def _pluralize_currency_label(label):
    label = (label or '').strip().upper()
    if not label:
        return label
    if label.endswith('L'):
        return f"{label[:-1]}LES"
    if label.endswith('Z'):
        return f"{label[:-1]}CES"
    if label.endswith(('A', 'E', 'I', 'O', 'U', 'Á', 'É', 'Í', 'Ó', 'Ú')):
        return f"{label}S"
    return f"{label}ES"


def amount_to_text_plural(currency, amount):
    text = currency.amount_to_text(amount)
    if not text:
        return ''
    result = text.upper()
    unit_label = currency.currency_unit_label or currency.name or ''
    plural_label = _pluralize_currency_label(unit_label)
    unit_upper = (unit_label or '').strip().upper()
    if unit_upper and plural_label and unit_upper != plural_label:
        pattern = r"\b%s\b" % re.escape(unit_upper)
        result = re.sub(pattern, plural_label, result)
    return result


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
            'amount_to_text_plural': amount_to_text_plural,
        }


class PaymentPlanReceiptReport(models.AbstractModel):
    _name = 'report.olivegt_sale_payment_plans.report_payment_plan_reconciliation_receipt'
    _description = 'Payment Plan Reconciliation Receipt'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['payment.plan.reconciliation'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'payment.plan.reconciliation',
            'docs': docs,
            'amount_to_text_plural': amount_to_text_plural,
        }