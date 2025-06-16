odoo.define('olivegt_sale_payment_plans.payment_plan_reconciliation_dashboard', function (require) {
"use strict";

var KanbanRecord = require('web.KanbanRecord');
var KanbanView = require('web.KanbanView');
var viewRegistry = require('web.view_registry');
var KanbanController = require('web.KanbanController');
var KanbanRenderer = require('web.KanbanRenderer');
var KanbanModel = require('web.KanbanModel');

var PaymentPlanDashboardController = KanbanController.extend({
    custom_events: _.extend({}, KanbanController.prototype.custom_events, {
        kanban_click_custom_reconcile: '_onKanbanClickCustomReconcile',
    }),

    /**
     * Handler when clicking on a card in the kanban view.
     *
     * @private
     * @param {OdooEvent} ev
     */
    _onKanbanClickCustomReconcile: function (ev) {
        var record = this.model.get(ev.target.recordData.id, {raw: true});
        this._rpc({
            model: 'payment.plan.line',
            method: 'action_reconcile',
            args: [[record.res_id]],
        }).then((result) => {
            this.do_action(result);
        });
    },
});

var PaymentPlanDashboardView = KanbanView.extend({
    config: _.extend({}, KanbanView.prototype.config, {
        Controller: PaymentPlanDashboardController,
    }),
});

viewRegistry.add('payment_plan_dashboard_kanban', PaymentPlanDashboardView);

return PaymentPlanDashboardView;

});
