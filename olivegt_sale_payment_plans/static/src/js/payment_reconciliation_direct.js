odoo.define('olivegt_sale_payment_plans.payment_reconciliation', function (require) {
    'use strict';

    var core = require('web.core');
    var _t = core._t;
    var QWeb = core.qweb;

    // Load the base widget to ensure our templates are available
    require('web.Widget');

    /**
     * Direct injection into the DOM for the reconciliation panel
     * This is the simplest approach that doesn't depend on specific hooks
     */
    $(document).ready(function() {
        // Set up a mutation observer to watch for the payment reconciliation dialog
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.addedNodes && mutation.addedNodes.length) {
                    for (let i = 0; i < mutation.addedNodes.length; i++) {
                        const node = mutation.addedNodes[i];
                        if (node.nodeType !== 1) continue; // Only process Element nodes
                        
                        // Check if this is a payment reconciliation dialog
                        const $dialog = $(node).find('.modal-title:contains("Reconcile Payment")').closest('.modal');
                        
                        if ($dialog.length > 0 && !$dialog.find('.payment_plan_overdue_info').length) {
                            // Get the payment plan line data from the dialog                            const lineCode = $dialog.find('h1').text().trim();
                            
                            // If we found a line code (format PPL/YYYY/NNNN)
                            if (lineCode && lineCode.match(/PPL\/\d+\/\d+/)) {
                                // Make an RPC call to get the overdue information
                                const rpc = require('web.rpc');
                                rpc.query({
                                    model: 'payment.plan.line',
                                    method: 'search_read',
                                    domain: [['payment_plan_id.name', '=', lineCode]], // Use the payment plan's name field
                                    fields: ['overdue_days', 'interest_amount', 'total_with_interest', 'currency_id'],
                                    limit: 1,
                                })                                .then(function(result) {
                                    if (result && result.length) {
                                        const line = result[0];
                                        
                                        // Only inject if there's overdue information
                                        if (line.overdue_days > 0) {
                                            // Create the info HTML from the template
                                            const $overdueInfo = $(QWeb.render('olivegt_sale_payment_plans.PaymentReconcileModal', {
                                                overdue_days: line.overdue_days,
                                                interest_amount: line.interest_amount,
                                                total_with_interest: line.total_with_interest,
                                                currency_id: line.currency_id
                                            }));
                                            
                                            // Find a place to inject the overdue info
                                            const $injectTarget = $dialog.find('.modal-body > div').first();
                                            if ($injectTarget.length) {
                                                $injectTarget.prepend($overdueInfo);
                                            }
                                        }
                                    } else {
                                        // If search by payment_plan_id.name fails, try a more direct approach
                                        // Try to find the payment plan line ID from the URL or context
                                        let paymentPlanLineId = null;
                                        
                                        // Try to get the active_id from the URL or dialog data
                                        const urlParams = new URLSearchParams(window.location.search);
                                        if (urlParams.has('active_id')) {
                                            paymentPlanLineId = parseInt(urlParams.get('active_id'), 10);
                                        }
                                        
                                        // If we found an ID, try to get the overdue information
                                        if (paymentPlanLineId) {
                                            rpc.query({
                                                model: 'payment.plan.line',
                                                method: 'read',
                                                args: [[paymentPlanLineId], ['overdue_days', 'interest_amount', 'total_with_interest', 'currency_id']],
                                            }).then(function(lineResult) {
                                                if (lineResult && lineResult.length && lineResult[0].overdue_days > 0) {
                                                    const line = lineResult[0];
                                                    const $overdueInfo = $(QWeb.render('olivegt_sale_payment_plans.PaymentReconcileModal', {
                                                        overdue_days: line.overdue_days,
                                                        interest_amount: line.interest_amount,
                                                        total_with_interest: line.total_with_interest,
                                                        currency_id: line.currency_id
                                                    }));
                                                    
                                                    const $injectTarget = $dialog.find('.modal-body > div').first();
                                                    if ($injectTarget.length) {
                                                        $injectTarget.prepend($overdueInfo);
                                                    }
                                                }
                                            });
                                        }
                                    }
                                });
                            }
                        }
                    }
                }
            });
        });
        
        // Start observing the entire document
        observer.observe(document.body, { childList: true, subtree: true });
    });
});
