from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from ..utils.payment_helpers import calculate_installment_dates, split_equal_installments


class PaymentPlanCalculatorWizard(models.TransientModel):
    _name = 'payment.plan.calculator.wizard'
    _description = 'Payment Plan Calculator'

    payment_plan_id = fields.Many2one('payment.plan', string='Payment Plan', required=True)
    total_amount = fields.Monetary(string='Total Amount', required=True)
    currency_id = fields.Many2one('res.currency', related='payment_plan_id.currency_id')

    # Reserva
    initial_payment = fields.Boolean('Reserva', default=True)
    initial_mode = fields.Selection([
        ('percent', 'Percentage'),
        ('custom', 'Custom Amount'),
    ], string='Initial Mode', default='percent')
    initial_percent = fields.Float(string='Initial %', default=10.0, help="Default down payment percent (e.g. 10 = 10%)")
    initial_amount = fields.Monetary(string='Initial Amount')
    initial_date = fields.Date('Fecha de Reserva', default=fields.Date.context_today)

    # Regular Installments
    installment_count = fields.Integer(string='Number of Installments', default=1)
    installment_frequency = fields.Selection([
        ('month', 'Monthly'),
        ('week', 'Weekly'),
        ('day', 'Daily'),
    ], string='Frequency', default='month')
    installment_start_date = fields.Date('First Payment Date', default=fields.Date.context_today)
    equal_installments = fields.Boolean('Equal Installments', default=True)

    # Pago Intermedio
    intermediate_payment = fields.Boolean('Pago Intermedio')
    intermediate_mode = fields.Selection([
        ('percent', 'Percentage'),
        ('custom', 'Custom Amount'),
    ], string='Intermediate Mode', default='custom')
    intermediate_percent = fields.Float(string='Intermediate %', default=0.0)
    intermediate_amount = fields.Monetary(string='Intermediate Amount')
    intermediate_date = fields.Date('Fecha de Pago Intermedio')

    # Pago Final
    final_payment = fields.Boolean('Pago Final')
    final_mode = fields.Selection([
        ('percent', 'Percentage'),
        ('custom', 'Custom Amount'),
    ], string='Final Mode', default='custom')
    final_percent = fields.Float(string='Final %', default=0.0)
    final_amount = fields.Monetary(string='Final Amount')
    final_date = fields.Date('Fecha de Pago Final')

    # Helper readonly fields to show equivalent percentages for custom amounts
    initial_percent_equiv = fields.Float(string='Initial % (equiv.)', compute='_compute_equiv_percents')
    intermediate_percent_equiv = fields.Float(string='Intermediate % (equiv.)', compute='_compute_equiv_percents')
    final_percent_equiv = fields.Float(string='Final % (equiv.)', compute='_compute_equiv_percents')

    @api.onchange('initial_payment', 'initial_mode', 'initial_percent', 'total_amount')
    def _onchange_initial_amount_auto(self):
        for wizard in self:
            if wizard.initial_payment and wizard.initial_mode == 'percent':
                percent = max(0.0, wizard.initial_percent or 0.0)
                wizard.initial_amount = wizard.currency_id.round((wizard.total_amount or 0.0) * (percent / 100.0))

    @api.onchange('final_payment', 'final_mode', 'final_percent', 'total_amount')
    def _onchange_final_amount_auto(self):
        for wizard in self:
            if wizard.final_payment and wizard.final_mode == 'percent':
                percent = max(0.0, wizard.final_percent or 0.0)
                wizard.final_amount = wizard.currency_id.round((wizard.total_amount or 0.0) * (percent / 100.0))

    @api.onchange('intermediate_payment', 'intermediate_mode', 'intermediate_percent', 'total_amount')
    def _onchange_intermediate_amount_auto(self):
        for wizard in self:
            if wizard.intermediate_payment and wizard.intermediate_mode == 'percent':
                percent = max(0.0, wizard.intermediate_percent or 0.0)
                wizard.intermediate_amount = wizard.currency_id.round((wizard.total_amount or 0.0) * (percent / 100.0))

    @api.onchange('initial_payment', 'initial_amount', 'initial_mode', 'initial_percent',
                  'intermediate_payment', 'intermediate_amount', 'intermediate_mode', 'intermediate_percent',
                  'final_payment', 'final_amount', 'final_mode', 'final_percent', 'total_amount')
    def _onchange_payment_distribution(self):
        remaining = self.total_amount
        if self.initial_payment and self.initial_amount > 0:
            remaining -= self.initial_amount
        if self.intermediate_payment and self.intermediate_amount > 0:
            remaining -= self.intermediate_amount
        if self.final_payment and self.final_amount > 0:
            remaining -= self.final_amount

        if remaining < 0:
            return {'warning': {
                'title': _('Invalid Distribution'),
                'message': _('The sum of initial, intermediate and final payments exceeds the total amount!')
            }}

    @api.onchange('installment_count', 'installment_frequency', 'installment_start_date')
    def _onchange_final_date(self):
        if self.installment_count and self.installment_start_date and self.installment_frequency:
            if self.installment_frequency == 'month':
                last_installment_date = self.installment_start_date + relativedelta(months=self.installment_count)
                self.final_date = last_installment_date + relativedelta(months=1)
                # Pago intermedio se ubica al final de las cuotas
                self.intermediate_date = last_installment_date
            elif self.installment_frequency == 'week':
                last_installment_date = self.installment_start_date + relativedelta(weeks=self.installment_count)
                self.final_date = last_installment_date + relativedelta(weeks=1)
                self.intermediate_date = last_installment_date
            elif self.installment_frequency == 'day':
                last_installment_date = self.installment_start_date + relativedelta(days=self.installment_count)
                self.final_date = last_installment_date + relativedelta(days=1)
                self.intermediate_date = last_installment_date

    def calculate_payment_plan(self):
        self.ensure_one()
        currency = self.currency_id or self.payment_plan_id.currency_id

        # Always align to the sale order total to ensure plan matches quotation
        base_total = self.payment_plan_id.sale_id.amount_total or self.total_amount or 0.0
        self.total_amount = base_total

        # Determine initial, intermediate and final amounts according to mode
        init_amount = 0.0
        inter_amount = 0.0
        fin_amount = 0.0
        if self.initial_payment:
            if self.initial_mode == 'percent':
                init_amount = currency.round(base_total * ((self.initial_percent or 0.0) / 100.0))
            else:
                init_amount = currency.round(self.initial_amount or 0.0)
        if self.intermediate_payment:
            if self.intermediate_mode == 'percent':
                inter_amount = currency.round(base_total * ((self.intermediate_percent or 0.0) / 100.0))
            else:
                inter_amount = currency.round(self.intermediate_amount or 0.0)
        if self.final_payment:
            if self.final_mode == 'percent':
                fin_amount = currency.round(base_total * ((self.final_percent or 0.0) / 100.0))
            else:
                fin_amount = currency.round(self.final_amount or 0.0)

        # Validate distribution
        total_distributed = init_amount + inter_amount + fin_amount
        if total_distributed > base_total:
            raise ValidationError(_('The sum of initial, intermediate and final payments exceeds the total amount!'))

        # Build installment amounts ensuring exact match to total
        installment_amounts = split_equal_installments(
            base_total,
            self.installment_count or 0,
            currency,
            initial_amount=init_amount,
            intermediate_amount=inter_amount,
            final_amount=fin_amount,
        )

        # If no installments, adjust final or initial to absorb rounding residuals
        if not installment_amounts:
            residual = currency.round(base_total - (init_amount + inter_amount + fin_amount))
            if residual:
                if self.final_payment:
                    fin_amount = currency.round(fin_amount + residual)
                elif self.intermediate_payment:
                    inter_amount = currency.round(inter_amount + residual)
                elif self.initial_payment:
                    init_amount = currency.round(init_amount + residual)
                else:
                    raise ValidationError(_('Total cannot be matched: set an initial/intermediate/final payment or at least 1 installment.'))

        # Clear existing plan lines
        self.payment_plan_id.line_ids.unlink()

        # Create new plan lines
        lines_vals = []

        # Reserva
        if self.initial_payment and init_amount > 0:
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': self.initial_date,
                'amount': init_amount,
                'name': _('Reserva'),
            })

        # Regular installments
        installment_dates = calculate_installment_dates(
            self.installment_start_date,
            self.installment_count,
            self.installment_frequency,
        )
        for i, date in enumerate(installment_dates):
            amt = installment_amounts[i] if i < len(installment_amounts) else 0.0
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': date,
                'amount': amt,
                'name': (_('Cuota %s') % (i + 1)),
            })

        # Pago Intermedio - se ubica al final de las cuotas
        if self.intermediate_payment and inter_amount > 0:
            intermediate_date = self.intermediate_date or (installment_dates[-1] if installment_dates else self.installment_start_date)
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': intermediate_date,
                'amount': inter_amount,
                'name': _('Pago Intermedio'),
            })

        # Pago Final
        current_date = installment_dates[-1] if installment_dates else self.installment_start_date
        if self.final_payment and fin_amount > 0:
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': self.final_date or current_date,
                'amount': fin_amount,
                'name': _('Pago Final'),
            })

        # Create lines
        self.env['payment.plan.line'].create(lines_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan',
            'view_mode': 'form',
            'res_id': self.payment_plan_id.id,
        }

    @api.depends('total_amount', 'initial_amount', 'intermediate_amount', 'final_amount')
    def _compute_equiv_percents(self):
        for wizard in self:
            total = wizard.total_amount or 0.0
            if total:
                wizard.initial_percent_equiv = round(((wizard.initial_amount or 0.0) / total) * 100.0, 4)
                wizard.intermediate_percent_equiv = round(((wizard.intermediate_amount or 0.0) / total) * 100.0, 4)
                wizard.final_percent_equiv = round(((wizard.final_amount or 0.0) / total) * 100.0, 4)
            else:
                wizard.initial_percent_equiv = 0.0
                wizard.intermediate_percent_equiv = 0.0
                wizard.final_percent_equiv = 0.0
