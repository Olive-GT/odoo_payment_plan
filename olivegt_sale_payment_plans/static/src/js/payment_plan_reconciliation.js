odoo.define('olivegt_sale_payment_plans.payment_plan_reconciliation', function (require) {
    'use strict';

    var core = require('web.core');
    var Widget = require('web.Widget');
    var AbstractAction = require('web.AbstractAction');
    var Dialog = require('web.Dialog');
    var _t = core._t;

    // Hook into the reconciliation widget when it's loaded
    var ReconcilePaymentOverride = Widget.extend({
        init: function (parent, options) {
            this._super.apply(this, arguments);
            this.parent = parent;
            this.options = options || {};

            // Hook into events to enhance the reconciliation dialog
            core.bus.on('payment_plan_reconciliation_dialog', this, this._onReconciliationDialog);
        },

        _onReconciliationDialog: function (dialog) {
            if (!dialog || !dialog.$el) {
                return;
            }

            // Get the payment plan line ID from the context
            var paymentPlanLineId = this.options.paymentPlanLineId;
            if (!paymentPlanLineId) {
                return;
            }

            // Get payment plan line data with overdue information
            this._rpc({
                model: 'payment.plan.line',
                method: 'read',
                args: [[paymentPlanLineId], ['overdue_days', 'interest_amount', 'total_with_interest']],
            }).then(function (result) {
                if (!result || !result.length) {
                    return;
                }

                var line = result[0];
                
                // Only add overdue information if it exists
                if (line.overdue_days > 0) {
                    // Find the place to insert the overdue information
                    var $infoGroup = dialog.$el.find('.oe_title, .o_form_view').first();
                    
                    if ($infoGroup.length) {
                        var $overdueInfo = $('<div class="payment_plan_overdue_info" style="margin-top: 15px; color: #d9534f;">' +
                            '<div><strong>' + _t('Overdue Days') + ':</strong> ' + line.overdue_days + '</div>' +
                            '<div><strong>' + _t('Interest Amount') + ':</strong> ' + line.interest_amount + '</div>' +
                            '<div><strong>' + _t('Total with Interest') + ':</strong> ' + line.total_with_interest + '</div>' +
                            '</div>');
                        
                        $infoGroup.append($overdueInfo);
                    }
                }
            });
        }
    });

    // Register the enhancement to run when web client is ready
    core.action_registry.add('payment_plan_reconciliation_override', ReconcilePaymentOverride);

    return ReconcilePaymentOverride;
});
