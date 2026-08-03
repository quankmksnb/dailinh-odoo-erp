/** @odoo-module **/
// ============================================================
//  DL RFQ List — đồng bộ giao diện danh sách Yêu cầu báo giá (D1).
//  - dl_rfq_list (Sales/chung): đủ 7 mốc vòng đời để quản lý toàn bộ RFQ.
//  - dl_rfq_list_my ("RFQ cần xử lý" — Kỹ thuật): CHỈ các mốc KTV thao tác/
//    theo dõi (bộ chip rút gọn TECH_CHIPS). Cả hai đều mở chi tiết tự do mọi
//    trạng thái; cổng "nhận xử lý" nằm trong form (nút "Xử lý" + khóa field
//    kết quả). Xem quotation_request_views.xml.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { serializeDate, today } from "@web/core/l10n/dates";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Chip lọc màn Sales/chung (list "Yêu cầu báo giá") — single-select, có số đếm.
// Gom theo MỐC QUYẾT ĐỊNH cho thanh chip gọn (không 1 chip / status):
//  - "Cần xử lý" (to_process) GỘP Mới + Đang xử lý + Đã bổ sung — cùng bản chất
//    "RFQ đang ở phía Kỹ thuật để xử lý"; là chip mặc định.
//  - Các mốc còn lại tách riêng vì bóng ở người khác / trạng thái chốt.
// Vẫn lọc lẻ Mới/Đang xử lý/Đã bổ sung được qua ô Search nâng cao. key CHÍNH
// LÀ name filter trong search view.
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "to_process", label: "Cần xử lý" },
    { key: "returned", label: "Trả lại bổ sung" },
    { key: "confirmed", label: "Chờ tạo báo giá" },
    { key: "quoted", label: "Đã tạo BG" },
    { key: "cancelled", label: "Đã hủy" },
    { key: "overdue", label: "Quá hạn" },
];

// Chip lọc màn "RFQ cần xử lý" (Kỹ thuật) — CHỈ các mốc KTV thật sự thao tác
// hoặc cần theo dõi. Bỏ "Đã tạo BG" + "Đã hủy" (thuần Sales / đã chết) khỏi
// hàng đợi việc của Kỹ thuật cho đỡ rối — chúng vẫn còn đầy đủ ở list Sales.
// Nhãn rút gọn "Đã xử lý xong" (thay chuỗi dài "…– chờ tạo báo giá") để thanh
// chip cân đối. "Tất cả" đứng ĐẦU cho đồng bộ với mọi màn chip khác (BOM, Báo
// giá, Phê duyệt, Khách hàng…) — dù chip mặc định vẫn là "Cần xử lý" (context
// search_default_to_process).
const TECH_CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "to_process", label: "Cần xử lý" },
    { key: "overdue", label: "Quá hạn" },
    { key: "returned", label: "Trả lại bổ sung" },
    { key: "confirmed", label: "Đã xử lý xong" },
];

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

    // Các chip ánh xạ 1-1 tới filter bật/tắt được ("all" = bỏ lọc, không có
    // filter). Suy thẳng từ dlChips để mỗi biến thể (Sales / Kỹ thuật) tự có
    // đúng tập chip của nó — không dùng hằng số module chung.
    get _filterKeys() {
        return this.dlChips.filter((c) => c.key !== "all").map((c) => c.key);
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
        const keys = this._filterKeys;
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && keys.includes(i.name)
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

// "RFQ cần xử lý" (Kỹ thuật) — chỉ khác list Sales ở bộ chip (TECH_CHIPS); mọi
// hành vi còn lại (đếm, single-select, mở chi tiết tự do) kế thừa nguyên vẹn.
export class DlRfqListMyController extends DlRfqListController {
    get dlChips() {
        return TECH_CHIPS;
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
