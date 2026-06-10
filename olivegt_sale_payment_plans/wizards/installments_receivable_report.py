from odoo import models, fields, api, _
from odoo.tools import float_is_zero

class InstallmentsReceivableReportWizard(models.TransientModel):
    _name = 'installments.receivable.report.wizard'
    _description = 'Reporte de cuotas por cobrar'

    line_ids = fields.One2many(
        'installments.receivable.report.wizard.line',
        'wizard_id',
        string='Lines',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    total_partners = fields.Integer(
        string='Clientes',
        compute='_compute_totals',
    )
    total_pending = fields.Monetary(
        string='Total de pendientes por cobrar',
        compute='_compute_totals',
        currency_field='currency_id',
    )
    xlsx_file = fields.Binary(string='Excel File', readonly=True)
    xlsx_filename = fields.Char(string='Filename', default='cuotas_por_cobrar.xlsx')

    @api.depends('line_ids.pending_amount', 'line_ids.partner_id')
    def _compute_totals(self):
        for wiz in self:
            partners = wiz.line_ids.mapped('partner_id')
            wiz.total_partners = len(partners)
            wiz.total_pending = sum(wiz.line_ids.mapped('pending_amount'))

    @api.model
    def default_get(self, fields_list):
        res = super(InstallmentsReceivableReportWizard, self).default_get(fields_list)
        
        today = fields.Date.context_today(self)
        domain = [
            ('state', 'in', ('pending', 'partial', 'overdue')),
            ('payment_plan_id.state', '=', 'posted'),
        ]
        lines = self.env['payment.plan.line'].search(domain)

        wizard_line_vals = []
        for line in lines:
            pending = line.currency_id.round(
                line.total_with_interest - line.allocated_amount
            )
            
            if float_is_zero(pending, precision_rounding=line.currency_id.rounding):
                continue

            overdue = max(0, (today - line.date).days) if line.date and today >= line.date else 0

            wizard_line_vals.append((0, 0, {
                'partner_id': line.payment_plan_id.partner_id.id,
                'payment_plan_id': line.payment_plan_id.id,
                'payment_plan_line_id': line.id,
                'due_date': line.date,
                'original_amount': line.amount,
                'allocated_amount': line.allocated_amount,
                'pending_amount': pending,
                'overdue_days': overdue,
                'state': line.state,
                'description': line.name or line.payment_plan_id.name,
            }))

        if wizard_line_vals:
            res.update({'line_ids': wizard_line_vals})
            
        return res


class InstallmentsReceivableReportWizardLine(models.TransientModel):
    _name = 'installments.receivable.report.wizard.line'
    _description = 'Reporte de cuotas por cobrar de lineas de pago'
    _order = 'partner_id, due_date'

    wizard_id = fields.Many2one(
        'installments.receivable.report.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='#')
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)
    payment_plan_id = fields.Many2one('payment.plan', string='Plan de pago')
    payment_plan_line_id = fields.Many2one('payment.plan.line', string='Cuota')
    due_date = fields.Date(string='Fecha de vencimiento')
    original_amount = fields.Monetary(string='Monto original')
    allocated_amount = fields.Monetary(string='Monto pagado')
    pending_amount = fields.Monetary(string='Monto pendiente')
    overdue_days = fields.Integer(string='Días vencidos')
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Parcialmente pagado'),
        ('overdue', 'Atrasado'),
    ], string='Estado')
    description = fields.Char(string='Descripción')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
