from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    reconciliation_ids = fields.One2many(
        'payment.plan.reconciliation',
        'move_line_id',
        string='Payment Plan Reconciliations'
    )
    
    payment_plan_available_amount = fields.Monetary(
        string='Available for Payment Plans',
        compute='_compute_payment_plan_available_amount',
        store=True
    )
    
    is_fully_consumed = fields.Boolean(
        string='Fully Consumed',
        compute='_compute_payment_plan_available_amount',
        store=True,
        help='True when this line has been fully consumed by payment plan reconciliations'
    )
    
    @api.depends('balance', 'account_id.reconcile', 'reconciliation_ids.state')
    def _compute_payment_plan_available_amount(self):
        """
        Calculate the amount available for allocation to payment plans
        """
        for move_line in self:
            # Skip if this line isn't reconcilable
            if not move_line.account_id.reconcile:
                move_line.payment_plan_available_amount = 0.0
                move_line.is_fully_consumed = True
                continue
                
            # Original amount is the absolute value of balance
            original_amount = abs(move_line.balance)
            
            # Find existing reconciliations for this move line
            reconciliations = self.env['payment.plan.reconciliation'].search([
                ('move_line_id', '=', move_line.id),
                ('state', '=', 'confirmed')
            ])
            
            # Calculate allocated amount
            allocated_amount = sum(reconciliations.mapped('amount'))
            
            # Available amount is original minus allocated
            available = original_amount - allocated_amount
            move_line.payment_plan_available_amount = available
            
            # Set fully_consumed flag when there's no available amount left
            move_line.is_fully_consumed = (available <= 0.0)
