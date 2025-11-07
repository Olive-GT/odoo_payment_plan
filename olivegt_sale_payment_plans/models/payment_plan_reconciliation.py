import base64
import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare


class PaymentPlanReconciliation(models.Model):
    _name = 'payment.plan.reconciliation'
    _description = 'Payment Plan Reconciliation'
    _order = 'id desc'
    payment_plan_line_id = fields.Many2one(
        'payment.plan.line', 
        string='Payment Plan Line',
        required=True, 
        ondelete='cascade'
    )
    move_line_id = fields.Many2one(
        'account.move.line', 
        string='Journal Item',
        required=True, 
        ondelete='restrict',
        domain="[('id', 'in', available_move_line_ids)]",
    )
    
    available_move_line_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_available_move_lines',
        string='Available Journal Items'
    )
    payment_plan_id = fields.Many2one(
        related='payment_plan_line_id.payment_plan_id',
        store=True,
        string='Payment Plan'
    )
    partner_id = fields.Many2one(        related='payment_plan_id.partner_id',
        store=True,
        string='Partner'
    )
    amount = fields.Monetary(
        string='Allocated Amount',
        required=True,
        help='Amount allocated to this payment plan line'
    )
    currency_id = fields.Many2one(
        related='payment_plan_line_id.currency_id',
        string='Currency'
    )
    date = fields.Date(
        string='Date',
        default=lambda self: fields.Date.context_today(self),
        required=True,
        help="Date of reconciliation. Always matches the journal entry date."
    )
    company_id = fields.Many2one(
        related='payment_plan_id.company_id',
        string='Company',
        store=True
    )
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        string='Journal Entry',
        store=True
    )
    journal_id = fields.Many2one(
        related='move_id.journal_id',
        string='Journal',
        store=True
    )
    move_date = fields.Date(
        related='move_id.date',
        string='Entry Date',
        store=True
    )
    move_payment_reference = fields.Char(
        related='move_id.ref',
        string='Payment Reference',
        store=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled')
    ], default='draft', string='Status', required=True)
    
    # Campos relacionados para mostrar información de mora
    overdue_days = fields.Integer(
        related='payment_plan_line_id.overdue_days',
        string='Overdue Days',
        readonly=True
    )
    interest_amount = fields.Monetary(
        related='payment_plan_line_id.interest_amount',
        string='Interest Amount',
        readonly=True
    )
    total_with_interest = fields.Monetary(
        related='payment_plan_line_id.total_with_interest',
        string='Total with Interest',
        readonly=True
    )
    
    @api.constrains('amount')
    def _check_amount(self):
        """Ensure allocated amount is positive and not zero"""
        for rec in self:
            if float_is_zero(rec.amount, precision_rounding=rec.currency_id.rounding):
                raise ValidationError(_("Allocated amount cannot be zero."))
            if float_compare(rec.amount, 0.0, precision_rounding=rec.currency_id.rounding) <= 0:
                raise ValidationError(_("Allocated amount must be positive."))
    
    @api.constrains('move_line_id', 'amount')
    def _check_available_amount(self):
        """Ensure allocated amount doesn't exceed available amount in move line"""
        for rec in self:
            # Get all allocations for this move line
            allocations = self.search([
                ('move_line_id', '=', rec.move_line_id.id),
                ('state', '!=', 'cancelled'),
                ('id', '!=', rec.id)  # Exclude current record
            ])
            
            # Calculate already allocated amount
            allocated_amount = sum(allocations.mapped('amount'))
            
            # Calculate available amount from move line (debit or credit)
            available_amount = abs(rec.move_line_id.balance)
            
            # Check if allocation exceeds available amount
            if float_compare(allocated_amount + rec.amount, available_amount, 
                           precision_rounding=rec.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Cannot allocate more than the available amount.\n"
                    "Available: %(available).2f\n"
                    "Already allocated: %(allocated).2f\n"
                    "This allocation: %(amount).2f"
                ) % {
                    'available': available_amount,
                    'allocated': allocated_amount,
                    'amount': rec.amount
                })
    
    @api.constrains('payment_plan_line_id', 'amount')
    def _check_payment_plan_line_amount(self):
        """Ensure allocations don't exceed the payment plan line amount"""
        for rec in self:
            # Get all allocations for this payment plan line
            allocations = self.search([
                ('payment_plan_line_id', '=', rec.payment_plan_line_id.id),
                ('state', '!=', 'cancelled'),
                ('id', '!=', rec.id)  # Exclude current record
            ])
            
            # Calculate already allocated amount
            allocated_amount = sum(allocations.mapped('amount'))
            
            # Check if allocation exceeds line amount
            plan_line_amount = rec.payment_plan_line_id.total_with_interest if rec.payment_plan_line_id.overdue_days > 0 else rec.payment_plan_line_id.amount
            if float_compare(allocated_amount + rec.amount, plan_line_amount, 
                           precision_rounding=rec.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Cannot allocate more than the payment plan line amount.\n"
                    "Line amount: %(line).2f\n"
                    "Already allocated: %(allocated).2f\n"
                    "This allocation: %(amount).2f"
                ) % {
                    'line': plan_line_amount,
                    'allocated': allocated_amount,
                    'amount': rec.amount
                })
    
    @api.constrains('date', 'move_date')
    def _check_date_match(self):
        """Ensure reconciliation date matches the journal entry date"""
        for rec in self:
            if rec.date != rec.move_date:
                raise ValidationError(_("The reconciliation date must match the journal entry date."))
                
    def action_confirm(self):
        """Confirm the reconciliation"""
        for rec in self:
            # Update state
            rec.state = 'confirmed'
            
            # Update payment plan line
            line = rec.payment_plan_line_id
            
            # Check if line is fully reconciled
            all_confirmed_allocations = self.search([
                ('payment_plan_line_id', '=', line.id),
                ('state', '=', 'confirmed')
            ])
            
            total_allocated = sum(all_confirmed_allocations.mapped('amount'))
            
            # Get payment date from the most recent allocation
            latest_allocation = all_confirmed_allocations.sorted(
                key=lambda r: r.date, reverse=True)[0]
            
            # Set payment reference from allocations
            references = list(filter(None, all_confirmed_allocations.mapped('move_payment_reference')))
            payment_reference = ', '.join(references[:3])
            if len(references) > 3:
                payment_reference += f' (+{len(references) - 3})'
              # Utiliza la fecha del asiento contable más reciente para el payment_date
            # Esto asegura que se use la fecha correcta para los cálculos de overdue
            payment_date = latest_allocation.move_date  # Usar move_date en lugar de date
            
            # Actualiza en la base de datos
            self.env.cr.execute("""
                UPDATE payment_plan_line 
                SET payment_date = %s, payment_reference = %s
                WHERE id = %s
            """, (payment_date, payment_reference, line.id))
            self.env.cr.commit()
            
            # Recarga el registro para obtener los nuevos valores de la base de datos
            self.env.invalidate_all()
            line = self.env['payment.plan.line'].browse(line.id)
            
            # SOLUCIÓN: Asegúrate de que payment_date se preserve con la fecha del asiento
            if line.payment_date != payment_date:
                # Si se perdió, fuerza la actualización nuevamente usando write
                line.write({'payment_date': payment_date})
                self.env.cr.commit()
            
            # Ahora fuerza los recálculos después de asegurar que payment_date está correcto
            line._compute_overdue_days()
            line._compute_interest_amount()
            line._compute_total_with_interest()
            line._compute_state()
            
            # Check if there's overdue interest to consider
            required_amount = line.total_with_interest if line.overdue_days > 0 else line.amount
              # If allocations cover the full amount (including interest if applicable), mark as paid
            precision = self.env['decimal.precision'].precision_get('Payment')
            if float_compare(total_allocated, required_amount, precision_digits=precision) >= 0 and not line.paid:
                line.mark_as_paid()

    def action_cancel(self):
        """Cancel the reconciliation"""
        for rec in self:
            # Update state
            rec.state = 'cancelled'
            
            # Check if line is marked as paid and needs to be reversed
            line = rec.payment_plan_line_id
            if line.paid:
                # Check if there are any remaining confirmed allocations
                remaining_allocations = self.search([
                    ('payment_plan_line_id', '=', line.id),
                    ('state', '=', 'confirmed'),
                    ('id', '!=', rec.id)
                ])
                total_allocated = sum(remaining_allocations.mapped('amount'))
                # If remaining allocations don't cover full amount, mark as unpaid
                precision = self.env['decimal.precision'].precision_get('Payment')
                if float_compare(total_allocated, line.amount, 
                              precision_digits=precision) < 0:
                    line.mark_as_unpaid()
    
    def action_draft(self):
        """Reset to draft state"""
        for rec in self:
            rec.state = 'draft'

    def action_print_receipt(self):
        """Generate the PDF receipt for this reconciliation"""
        self.ensure_one()
        return self.env.ref('olivegt_sale_payment_plans.action_report_payment_plan_reconciliation_receipt').report_action(self)
    
    def action_send_receipt_email(self):
        """Launch the email composer with the receipt template"""
        self.ensure_one()
        template = self.env.ref(
            'olivegt_sale_payment_plans.mail_template_payment_plan_reconciliation_receipt',
            raise_if_not_found=False,
        )
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', raise_if_not_found=False)

        attachment_ids = []
        receipt_report = self.env.ref('olivegt_sale_payment_plans.action_report_payment_plan_reconciliation_receipt', raise_if_not_found=False)
        if receipt_report:
            # Render the receipt PDF and store it as an attachment for the composer
            pdf_content, _pdf_format = receipt_report._render_qweb_pdf(
                receipt_report.report_name,
                res_ids=[self.id],
            )
            safe_name = (self.payment_plan_id.name or self.display_name or 'recibo').replace('/', '_')
            attachment = self.env['ir.attachment'].create({
                'name': f'Recibo_{safe_name}.pdf',
                'type': 'binary',
                'mimetype': 'application/pdf',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'payment.plan.reconciliation',
                'res_id': self.id,
            })
            attachment_ids.append(attachment.id)

        if self.payment_plan_id:
            statement_report = self.env.ref('olivegt_sale_payment_plans.action_report_payment_plan', raise_if_not_found=False)
            if statement_report:
                statement_content, _pdf_format = statement_report._render_qweb_pdf(
                    statement_report.report_name,
                    res_ids=[self.payment_plan_id.id],
                )
                statement_name = (self.payment_plan_id.name or 'estado_cuenta').replace('/', '_')
                statement_attachment = self.env['ir.attachment'].create({
                    'name': f'EstadoCuenta_{statement_name}.pdf',
                    'type': 'binary',
                    'mimetype': 'application/pdf',
                    'datas': base64.b64encode(statement_content),
                    'res_model': 'payment.plan.reconciliation',
                    'res_id': self.id,
                })
                attachment_ids.append(statement_attachment.id)
        email_to = False
        if self.partner_id and self.partner_id.email:
            # Split multiple addresses entered in a single field
            email_list = [addr.strip() for addr in re.split(r'[,;/\s]+', self.partner_id.email) if addr.strip()]
            if email_list:
                email_to = ', '.join(email_list)

        ctx = {
            'default_model': 'payment.plan.reconciliation',
            'default_res_ids': [self.id],
            'default_use_template': bool(template),
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'active_model': 'payment.plan.reconciliation',
            'active_ids': [self.id],
            'active_id': self.id,
            'default_attachment_ids': [(6, 0, attachment_ids)] if attachment_ids else False,
            'default_partner_ids': [self.partner_id.id] if self.partner_id else False,
            'default_email_from': self.company_id.email_formatted or self.env.user.email_formatted,
            'default_email_to': email_to,
        }
        return {
            'name': _('Enviar recibo por correo'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'view_id': compose_form.id if compose_form else False,
            'target': 'new',
            'context': ctx,
        }

    @api.model
    def create(self, vals):
        """Override create to set the date to match move date"""
        if vals.get('move_line_id'):
            move_line = self.env['account.move.line'].browse(vals.get('move_line_id'))
            if move_line and move_line.move_id.date:
                # Siempre forzar la fecha del asiento contable, incluso si ya hay una fecha en vals
                vals['date'] = move_line.move_id.date
        elif not vals.get('date'):
            vals['date'] = fields.Date.context_today(self)
        return super().create(vals)
    
    @api.depends('partner_id')
    def _compute_available_move_lines(self):
        """Compute available move lines for reconciliation based on filters"""
        for rec in self:
            # Allow either incoming bank debits or customer advance credits
            domain = [
                ('account_id.reconcile', '=', True),
                ('reconciled', '=', False),
                '|',
                '&',
                ('account_id.account_type', 'in', ['asset_cash', 'asset_liquidity']),
                ('debit', '>', 0.0),
                '&',
                ('account_id.account_type', 'in', ['liability_current', 'liability_payable', 'liability_non_current']),
                ('credit', '>', 0.0)
            ]
            
            # Add partner filter if we have one
            if rec.partner_id:
                domain.append(('partner_id', '=', rec.partner_id.id))
                
            # Get move lines that match the domain
            move_lines = self.env['account.move.line'].search(domain)
            rec.available_move_line_ids = move_lines
            
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """When partner changes, recompute available move lines"""
        self._compute_available_move_lines()

    @api.onchange('move_line_id')
    def _onchange_move_line_id(self):
        """When move line changes, set date to match move date"""
        for rec in self:
            if rec.move_line_id and rec.move_line_id.move_id.date:
                rec.date = rec.move_line_id.move_id.date
