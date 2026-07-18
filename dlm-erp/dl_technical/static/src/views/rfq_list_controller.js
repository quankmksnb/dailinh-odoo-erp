/** @odoo-module **/
// ============================================================
//  DL RFQ List — đồng bộ giao diện danh sách Yêu cầu báo giá (D1).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlRfqListController extends DlListBaseController {
    get dlCountNoun() {
        return "yêu cầu báo giá";
    }

    get dlFilterDropdowns() {
        return [
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "new", label: "Mới" },
                    { name: "processing", label: "Đang xử lý" },
                    { name: "confirmed", label: "Chờ báo giá" },
                    { name: "quoted", label: "Đã tạo BG" },
                    { name: "overdue", label: "Quá hạn" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_rfq_list", {
    ...listView,
    Controller: DlRfqListController,
});
