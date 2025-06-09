from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from ..utils.payment_helpers import calculate_installment_dates, calculate_equal_installments


class PaymentPlanCalculatorWizard(models.TransientModel):
    _name = 'payment.plan.calculator.wizard'
    _description = 'Payment Plan Calculator'

    payment_plan_id = fields.Many2one('payment.plan', string='Payment Plan', required=True)
    total_amount = fields.Monetary(string='Total Amount', required=True)
    currency_id = fields.Many2one('res.currency', related='payment_plan_id.currency_id')
    
    # Initial Payment
    initial_payment = fields.Boolean('Initial Payment')
    initial_amount = fields.Monetary(string='Initial Amount')
    initial_date = fields.Date('Initial Payment Date', default=fields.Date.context_today)
    
    # Regular Installments
    installment_count = fields.Integer(string='Number of Installments', default=1)
    installment_frequency = fields.Selection([
        ('month', 'Monthly'),
        ('week', 'Weekly'),
        ('day', 'Daily'),
    ], string='Frequency', default='month')
    installment_start_date = fields.Date('First Payment Date', default=fields.Date.context_today)
    equal_installments = fields.Boolean('Equal Installments', default=True)
    
    # Final Payment
    final_payment = fields.Boolean('Final Payment')
    final_amount = fields.Monetary(string='Final Amount')
    final_date = fields.Date('Final Payment Date')

    @api.onchange('initial_payment', 'initial_amount', 'final_payment', 'final_amount', 'total_amount')
    def _onchange_payment_distribution(self):
        remaining = self.total_amount
        if self.initial_payment and self.initial_amount > 0:
            remaining -= self.initial_amount
        if self.final_payment and self.final_amount > 0:
            remaining -= self.final_amount
        
        # Ensure the distribution makes sense
        if remaining < 0:
            return {'warning': {
                'title': _('Invalid Distribution'),
                'message': _('The sum of initial and final payments exceeds the total amount!')
            }}
    
    @api.onchange('installment_count', 'installment_frequency', 'installment_start_date')
    def _onchange_final_date(self):
        if self.installment_count and self.installment_start_date and self.installment_frequency:
            if self.installment_frequency == 'month':
                self.final_date = self.installment_start_date + relativedelta(months=self.installment_count)
            elif self.installment_frequency == 'week':
                self.final_date = self.installment_start_date + relativedelta(weeks=self.installment_count)
            elif self.installment_frequency == 'day':
                self.final_date = self.installment_start_date + relativedelta(days=self.installment_count)
    
    def calculate_payment_plan(self):
        self.ensure_one()
        
        # Validate amounts
        total_distributed = 0
        if self.initial_payment:
            total_distributed += self.initial_amount
        if self.final_payment:
            total_distributed += self.final_amount
            
        if total_distributed > self.total_amount:
            raise ValidationError(_('The sum of initial and final payments exceeds the total amount!'))
          # Calculate regular installment amount using helper function
        regular_amount = calculate_equal_installments(
            self.total_amount, 
            self.installment_count, 
            self.initial_amount if self.initial_payment else 0,
            self.final_amount if self.final_payment else 0
        )
        
        # Clear existing plan lines
        self.payment_plan_id.line_ids.unlink()
        
        # Create new plan lines
        lines_vals = []
        
        # Initial payment
        if self.initial_payment and self.initial_amount > 0:
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': self.initial_date,
                'amount': self.initial_amount,
                'name': _('Initial Payment'),
            })
          # Regular installments - using helper function to calculate installment dates
        installment_dates = calculate_installment_dates(
            self.installment_start_date,
            self.installment_count,
            self.installment_frequency
        )
        
        for i, date in enumerate(installment_dates):
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': date,
                'amount': regular_amount,
                'name': _('Installment %s', i+1),
            })
            
        # Set current_date to the last installment date for final payment calculation
        current_date = installment_dates[-1] if installment_dates else self.installment_start_date
        
        # Final payment
        if self.final_payment and self.final_amount > 0:
            lines_vals.append({
                'payment_plan_id': self.payment_plan_id.id,
                'date': self.final_date or current_date,
                'amount': self.final_amount,
                'name': _('Final Payment'),
            })
        
        # Create lines
        self.env['payment.plan.line'].create(lines_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'payment.plan',
            'view_mode': 'form',
            'res_id': self.payment_plan_id.id,
        }
