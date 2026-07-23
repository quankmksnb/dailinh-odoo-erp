/** @odoo-module **/
// ============================================================
//  DL RFQ List — đồng bộ giao diện danh sách Yêu cầu báo giá (D1).
//  - dl_rfq_list: list Sales/chung — mở chi tiết tự do mọi trạng thái.
//  - dl_rfq_list_my: list "RFQ cần xử lý" (Kỹ thuật) — phải bấm "Nhận RFQ"
//    (status → Đang xử lý) rồi mới mở được chi tiết.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
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
                    { name: "supplemented", label: "Đã bổ sung" },
                    { name: "confirmed", label: "Chờ báo giá" },
                    { name: "quoted", label: "Đã tạo BG" },
                    { name: "overdue", label: "Quá hạn" },
                ],
            },
        ];
    }
}

// "RFQ cần xử lý" (Kỹ thuật): RFQ Mới/Đã bổ sung phải bấm nút "Nhận RFQ"
// trên dòng trước — status đổi thành "Đang xử lý" thì mới mở được chi tiết.
export class DlRfqListMyController extends DlRfqListController {
    setup() {
        super.setup();
        this.dlNotification = useService("notification");
    }

    async openRecord(record) {
        if (["new", "supplemented"].includes(record.data.status)) {
            this.dlNotification.add(
                "Bấm nút 'Nhận RFQ' trên dòng để nhận xử lý trước khi mở chi tiết. " +
                    "Trạng thái RFQ sẽ chuyển sang 'Đang xử lý'.",
                { type: "warning", title: "Chưa nhận RFQ" }
            );
            return;
        }
        return super.openRecord(record);
    }
}

registry.category("views").add("dl_rfq_list", {
    ...listView,
    Controller: DlRfqListController,
});

registry.category("views").add("dl_rfq_list_my", {
    ...listView,
    Controller: DlRfqListMyController,
});
