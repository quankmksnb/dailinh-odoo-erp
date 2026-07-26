/** @odoo-module **/
// ============================================================
//  DL RFQ List — đồng bộ giao diện danh sách Yêu cầu báo giá (D1).
//  - dl_rfq_list: list Sales/chung — mở chi tiết tự do mọi trạng thái.
//  - dl_rfq_list_my: list "RFQ cần xử lý" (Kỹ thuật) — RFQ "Mới" phải bấm
//    "Nhận RFQ" (status → Đang xử lý) rồi mới mở được chi tiết. RFQ "Đã bổ
//    sung" (đã tiếp nhận trước đó, quay lại sau vòng trả-bổ-sung) mở tự do.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
import { serializeDate, today } from "@web/core/l10n/dates";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Chip lọc trạng thái RFQ (single-select, có số đếm) — thay dropdown ẩn cũ.
// "Cần xử lý" (to_process = Mới+Đang xử lý+Đã bổ sung) là chip mặc định khi
// mở màn: đúng ý "chỉ hiện RFQ còn phải làm", lại đặt tên trung thực cho
// composite mà dropdown single-select trước đây không thể hiển thị nổi (bật 3
// filter nhưng chỉ khoe được "Mới"). key CHÍNH LÀ name filter trong search view
// để bật/tắt đồng bộ với bộ lọc gốc Odoo.
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "to_process", label: "Cần xử lý" },
    { key: "new", label: "Mới" },
    { key: "processing", label: "Đang xử lý" },
    { key: "returned", label: "Trả lại bổ sung" },
    { key: "supplemented", label: "Đã bổ sung" },
    { key: "confirmed", label: "Đã xử lý xong" },
    { key: "quoted", label: "Đã tạo BG" },
    { key: "cancelled", label: "Đã hủy" },
    { key: "overdue", label: "Quá hạn" },
];
// Các chip ánh xạ 1-1 tới filter bật/tắt được ("all" là bỏ lọc, không có filter).
const FILTER_KEYS = CHIPS.filter((c) => c.key !== "all").map((c) => c.key);

export class DlRfqListController extends DlListBaseController {
    // "+ Tạo RFQ" → mở đúng màn Tạo RFQ của Sales (2 bảng thương mại/gia
    // công — action_dl_quotation_request_create) thay vì form mặc định.
    async createRecord() {
        return this.actionService.doAction(
            "dl_technical.action_dl_quotation_request_create"
        );
    }

    get dlCountNoun() {
        return "yêu cầu báo giá";
    }

    get dlChips() {
        return CHIPS;
    }

    async _loadCounts() {
        const model = "dl.quotation.request";
        const groups = await this.orm.readGroup(model, [], ["status"], ["status"]);
        const byStatus = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.status_count ?? 0;
            byStatus[g.status] = n;
            total += n;
        }
        const counts = {
            all: total,
            new: byStatus.new ?? 0,
            processing: byStatus.processing ?? 0,
            returned: byStatus.returned ?? 0,
            supplemented: byStatus.supplemented ?? 0,
            confirmed: byStatus.confirmed ?? 0,
            quoted: byStatus.quoted ?? 0,
            cancelled: byStatus.cancelled ?? 0,
        };
        // "Cần xử lý" = tổng các trạng thái còn phải làm (khớp domain filter
        // to_process). "Quá hạn" là điều kiện chéo (deadline + status) nên phải
        // đếm riêng, khớp đúng domain filter overdue trong search view.
        counts.to_process = counts.new + counts.processing + counts.supplemented;
        counts.overdue = await this.orm.searchCount(model, [
            ["deadline", "<", serializeDate(today())],
            ["status", "not in", ["quoted", "cancelled"]],
        ]);
        this.dlCounts = counts;
    }

    _statusFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && FILTER_KEYS.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._statusFilters().find((i) => i.isActive);
        return active ? active.name : "all";
    }

    // Single-select: tắt hết filter trạng thái rồi bật 1 (giống màn Phê duyệt).
    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._statusFilters();
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        if (key !== "all") {
            const it = items.find((i) => i.name === key);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }
}

// "RFQ cần xử lý" (Kỹ thuật): chỉ RFQ "Mới" phải bấm nút "Nhận RFQ" trên dòng
// trước (status → Đang xử lý) mới mở được chi tiết — đánh dấu KTV đã tiếp nhận
// lần đầu. RFQ "Đã bổ sung" đã được tiếp nhận ở vòng trước (processing →
// returned → supplemented) nên mở thẳng, không bắt nhận lại; badge trạng thái +
// dòng chatter "Sales đã bổ sung" vẫn báo hiệu có thông tin mới.
export class DlRfqListMyController extends DlRfqListController {
    setup() {
        super.setup();
        this.dlNotification = useService("notification");
    }

    async openRecord(record) {
        if (record.data.status === "new") {
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
