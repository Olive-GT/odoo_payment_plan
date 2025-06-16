from odoo import models, api, fields, _


class PaymentPlanLine(models.Model):
    _inherit = 'payment.plan.line'

    def prepare_payment_registration_vals(self):
        """
        Prepare values to pass to the payment registration modal
        This will be called when opening the reconciliation panel
        """
        self.ensure_one()
        vals = {
            'default_payment_plan_id': self.payment_plan_id.id,
            'default_payment_plan_line_id': self.id,
            'default_partner_id': self.payment_plan_id.partner_id.id,
            'default_amount': self.amount - self.allocated_amount,
            'default_overdue_days': self.overdue_days,
            'default_interest_amount': self.interest_amount,
            'default_total_with_interest': self.total_with_interest,
            'payment_plan_line_id': self.id,
            'show_overdue_info': self.overdue_days > 0,
            # Add standard (non-default) values too
            'overdue_days': self.overdue_days,
            'interest_amount': self.interest_amount,
            'total_with_interest': self.total_with_interest,
            'currency_id': self.currency_id.id,
            'currency_symbol': self.currency_id.symbol,
        }
        return vals
        
    def action_reconcile_payment(self):
        """Override the reconciliation action to include overdue info in the context"""
        self.ensure_one()
        
        # Get the original action from the parent method if it exists
        action = super(PaymentPlanLine, self).action_reconcile_payment() if hasattr(super(PaymentPlanLine, self), 'action_reconcile_payment') else {
            'type': 'ir.actions.act_window',
            'name': _('Reconcile Payment'),
            'res_model': 'account.move.line',
            'view_mode': 'tree,form',
            'context': {},
        }
        
        # Add our overdue info to the context
        registration_vals = self.prepare_payment_registration_vals()
        if action and isinstance(action, dict) and 'context' in action:
            if isinstance(action['context'], dict):
                action['context'].update(registration_vals)
            else:
                # If context is a string, append our values
                action['context'] = str(action['context']).strip('{}') + ', ' + str(registration_vals).strip('{}')
        else:
            action['context'] = registration_vals
            
        return action
