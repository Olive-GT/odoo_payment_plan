/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KanbanArchParser } from "@web/views/kanban/kanban_arch_parser";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Custom Kanban Controller for Payment Plan Dashboard
 */
class PaymentPlanDashboardKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    /**
     * Handle clicking a card and open the reconciliation view directly
     * @param {Object} record - The record that was clicked
     */
    async onRecordClick(record) {
        // Override default click behavior
        if (record) {
            const result = await this.orm.call(
                "payment.plan.line",
                "action_reconcile",
                [[record.resId]]
            );
            this.action.doAction(result);
        }
    }
}

/**
 * Custom Kanban Record to override click behavior
 */
class PaymentPlanDashboardKanbanRecord extends KanbanRecord {
    onClick(ev) {
        // Prevent default kanban record click handling
        ev.preventDefault();
        ev.stopPropagation();
        this.props.onRecordClick(this.props.record);
    }
}

/**
 * Custom Renderer to use our custom KanbanRecord
 */
class PaymentPlanDashboardKanbanRenderer extends KanbanRenderer {
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: PaymentPlanDashboardKanbanRecord,
    };

    setup() {
        super.setup();
    }
}

/**
 * Register our custom kanban view
 */
export const paymentPlanDashboardKanbanView = {
    ...kanbanView,
    Controller: PaymentPlanDashboardKanbanController,
    Renderer: PaymentPlanDashboardKanbanRenderer,
};

registry.category("views").add("payment_plan_dashboard_kanban", paymentPlanDashboardKanbanView);

});
