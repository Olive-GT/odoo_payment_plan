odoo.define('olivegt_sale_payment_plans.payment_plan_reconciliation', function (require) {
    'use strict';

    var core = require('web.core');
    var session = require('web.session');
    var Widget = require('web.Widget');
    var Dialog = require('web.Dialog');
    var QWeb = core.qweb;
    var _t = core._t;

    // Make sure our templates are loaded
    var reconcile_templates = require('web.core').qweb;

    /**
     * Widget that overrides the standard reconciliation widget to add overdue information
     * This will intercept the reconcile dialog rendering and inject our additional info
     */
    var ReconcilePaymentOverride = Widget.extend({
        events: {
            'click .o_reconcile_payment_container': '_onReconcilePaymentClick',
        },
        
        /**
         * @override
         */
        init: function (parent, options) {
            this._super.apply(this, arguments);
            this.parent = parent;
            this.options = options || {};
            
            // Hook into DOM mutations to detect when reconcile popup appears
            this._setupMutationObserver();
        },

        /**
         * @override
         */
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                // Check if there's already a reconcile popup when the widget starts
                self._checkExistingReconcilePopup();
            });
        },

        /**
         * Setup a mutation observer to watch for reconcile popup appearing in the DOM
         * This is needed because Odoo creates dialogs dynamically
         */
        _setupMutationObserver: function () {
            var self = this;
            if (!window.MutationObserver) {
                return;  // Not supported in this browser
            }

            // Create an observer instance
            this.observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.addedNodes && mutation.addedNodes.length > 0) {
                        for (var i = 0; i < mutation.addedNodes.length; i++) {
                            var node = mutation.addedNodes[i];
                            if (node.nodeType === 1 && node.classList && 
                                (node.classList.contains('modal') || node.querySelector('.modal'))) {
                                // Check if this is our reconcile payment popup
                                var $modal = $(node).find('.modal-title:contains("Reconcile Payment")').closest('.modal');
                                if ($modal.length) {
                                    self._enhanceReconcilePopup($modal);
                                }
                            }
                        }
                    }
                });
            });

            // Start observing
            this.observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        },

        /**
         * Check if there's already a reconcile popup when the widget starts
         */
        _checkExistingReconcilePopup: function () {
            var $modal = $('.modal-title:contains("Reconcile Payment")').closest('.modal');
            if ($modal.length) {
                this._enhanceReconcilePopup($modal);
            }
        },

        /**
         * Enhance the reconcile popup with overdue information
         */
        _enhanceReconcilePopup: function ($modal) {
            var self = this;
            var activeId = session.active_id;
            
            // If we don't have an active_id, try to get it from the URL
            if (!activeId) {
                var urlParams = new URLSearchParams(window.location.search);
                activeId = parseInt(urlParams.get('id'), 10);
            }
            
            // If we still don't have an ID, try to extract it from the popup
            if (!activeId) {
                var headerText = $modal.find('h1').text() || '';
                var match = headerText.match(/PPL\/\d+\/(\d+)/);
                if (match && match[1]) {
                    activeId = parseInt(match[1], 10);
                }
            }
            
            if (!activeId) {
                console.error('Could not determine payment plan line ID');
                return;
            }
            
            // Get payment plan line data
            this._rpc({
                model: 'payment.plan.line',
                method: 'read',
                args: [[activeId], ['overdue_days', 'interest_amount', 'total_with_interest', 'currency_id']],
            }).then(function (result) {
                if (!result || !result.length) {
                    return;
                }
                
                var line = result[0];
                if (line.overdue_days > 0) {
                    // Create overdue info panel using QWeb template
                    var $lineAmount = $modal.find('.o_field_name:contains("Line Amount"), .o_field_name:contains("Already Allocated")').first().closest('.row');
                    
                    if ($lineAmount.length) {
                        var $infoPanel = $(QWeb.render('olivegt_sale_payment_plans.ReconcilePaymentInfoPanel', {
                            overdue_days: line.overdue_days,
                            interest_amount: line.interest_amount,
                            total_with_interest: line.total_with_interest,
                            currency_id: line.currency_id
                        }));
                        
                        $lineAmount.after($infoPanel);
                    }
                    
                    // Also add a notice at the top of the allocations section
                    var $allocationsSection = $modal.find('.o_notebook_headers:contains("Allocations")').first();
                    if ($allocationsSection.length) {
                        var $warningMessage = $('<div class="alert alert-warning">' +
                            '<strong>Note:</strong> This payment line has an overdue interest amount of ' + 
                            line.interest_amount + '. The total amount required to fully reconcile this payment is ' + 
                            line.total_with_interest + '.' +
                            '</div>');
                        
                        $allocationsSection.before($warningMessage);
                    }
                }
            });
        },
    });

    // Register the widget to run on page load
    core.action_registry.add('payment_plan_reconciliation_override', ReconcilePaymentOverride);

    // Auto-instantiate our widget when the web client is ready
    $(document).ready(function() {
        new ReconcilePaymentOverride().appendTo(document.body);
    });

    return ReconcilePaymentOverride;
});
