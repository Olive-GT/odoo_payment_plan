odoo.define('olivegt_sale_payment_plans.enhanced_payment_reconciliation', function (require) {
    'use strict';

    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var _t = core._t;
    var QWeb = core.qweb;
    var rpc = require('web.rpc');

    /**
     * Override the standard Odoo ReconcileButton widget
     * This intercepts when the reconciliation button is clicked and adds our overdue information
     */
    $(document).ready(function() {
        // Store the original showReconcilePaymentDialog function if it exists
        var originalDialog = Dialog.confirm;
        
        // Override the Dialog.confirm method to add our overdue information
        Dialog.confirm = function(parent, options) {
            // Check if this is a payment reconciliation dialog by title
            if (options && options.title && options.title.indexOf(_t("Reconcile Payment")) !== -1) {
                // Extract the payment_plan_line_id from the context
                var context = parent.context || {};
                var activePlanLineId = context.payment_plan_line_id || context.active_id;
                
                if (activePlanLineId) {
                    // Get the overdue info from the server
                    rpc.query({
                        model: 'payment.plan.line',
                        method: 'read',
                        args: [[activePlanLineId], ['overdue_days', 'interest_amount', 'total_with_interest', 'currency_id']],
                    }).then(function(result) {
                        if (result && result.length && result[0].overdue_days > 0) {
                            // We have overdue information, add it to the dialog
                            var $dialog = $('.modal[role="dialog"]:visible');
                            
                            if ($dialog.length && !$dialog.find('.payment_plan_overdue_info').length) {
                                var $infoPanel = $(QWeb.render('olivegt_sale_payment_plans.PaymentReconcileModal', {
                                    overdue_days: result[0].overdue_days,
                                    interest_amount: result[0].interest_amount,
                                    total_with_interest: result[0].total_with_interest,
                                    currency_id: result[0].currency_id
                                }));
                                
                                // Insert at the beginning of the dialog body
                                $dialog.find('.modal-body').prepend($infoPanel);
                            }
                        }
                    });
                }
            }
            
            // Call the original method
            return originalDialog.apply(this, arguments);
        };
        
        // Add a mutation observer to catch dynamically added reconciliation dialogs
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.addedNodes && mutation.addedNodes.length) {
                    for (let i = 0; i < mutation.addedNodes.length; i++) {
                        const node = mutation.addedNodes[i];
                        if (node.nodeType !== 1) continue; // Skip non-Element nodes
                        
                        // Check if this is a reconciliation dialog
                        const $dialog = $(node).find('.modal-title:contains("Reconcile Payment")').closest('.modal');
                        if ($dialog.length && !$dialog.find('.payment_plan_overdue_info').length) {
                            // Get the payment plan line ID from various possible sources
                            let paymentPlanLineId = null;
                            
                            // Try from the URL
                            const urlParams = new URLSearchParams(window.location.search);
                            if (urlParams.has('payment_plan_line_id')) {
                                paymentPlanLineId = parseInt(urlParams.get('payment_plan_line_id'), 10);
                            } else if (urlParams.has('active_id')) {
                                paymentPlanLineId = parseInt(urlParams.get('active_id'), 10);
                            }
                            
                            // Try from dialog data
                            if (!paymentPlanLineId) {
                                // Look for hidden input or data attributes
                                paymentPlanLineId = $dialog.find('[name="payment_plan_line_id"]').val() || 
                                                  $dialog.data('payment_plan_line_id');
                            }
                            
                            // Try to extract from the heading - format PPL/YYYY/NNNN
                            if (!paymentPlanLineId) {
                                const heading = $dialog.find('h1').text().trim();
                                if (heading && heading.match(/PPL\/\d+\/\d+/)) {
                                    // Use the heading as a reference to lookup the record
                                    rpc.query({
                                        model: 'payment.plan.line',
                                        method: 'search_read',
                                        domain: [['payment_plan_id.name', '=', heading]],
                                        fields: ['id', 'overdue_days', 'interest_amount', 'total_with_interest', 'currency_id'],
                                        limit: 1,
                                    }).then(function(result) {
                                        if (result && result.length && result[0].overdue_days > 0) {
                                            injectOverdueInfo($dialog, result[0]);
                                        }
                                    });
                                    return;
                                }
                            }
                            
                            // If we have the ID, get the data and inject it
                            if (paymentPlanLineId) {
                                rpc.query({
                                    model: 'payment.plan.line',
                                    method: 'read',
                                    args: [[paymentPlanLineId], ['overdue_days', 'interest_amount', 'total_with_interest', 'currency_id']],
                                }).then(function(result) {
                                    if (result && result.length && result[0].overdue_days > 0) {
                                        injectOverdueInfo($dialog, result[0]);
                                    }
                                });
                            }
                        }
                    }
                }
            });
        });
        
        // Helper function to inject the overdue info
        function injectOverdueInfo($dialog, data) {
            if (!$dialog.find('.payment_plan_overdue_info').length) {
                var $infoPanel = $(QWeb.render('olivegt_sale_payment_plans.PaymentReconcileModal', {
                    overdue_days: data.overdue_days,
                    interest_amount: data.interest_amount,
                    total_with_interest: data.total_with_interest,
                    currency_id: data.currency_id
                }));
                
                $dialog.find('.modal-body').prepend($infoPanel);
            }
        }
        
        // Start observing for changes
        observer.observe(document.body, { childList: true, subtree: true });
    });
});
