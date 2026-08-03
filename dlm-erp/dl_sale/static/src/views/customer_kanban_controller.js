/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { DlKanbanBaseController } from "@dl_base/views/dl_kanban_controller";

export class DlCustomerKanbanController extends DlKanbanBaseController {
    get dlFilterDropdowns() {
        return [
            {
                key: "type",
                label: "Tất cả loại KH",
                filters: [
                    { name: "filter_individual", label: "Cá nhân" },
                    { name: "filter_company", label: "Doanh nghiệp" },
                    { name: "filter_dealer", label: "Đại lý" },
                ],
            },
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "active", label: "Đang hoạt động" },
                    { name: "inactive", label: "Không hoạt động" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_customer_kanban", {
    ...kanbanView,
    Controller: DlCustomerKanbanController,
});
