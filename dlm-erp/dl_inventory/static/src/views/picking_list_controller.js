/** @odoo-module **/
// ============================================================
//  Danh sách phiếu kho — thanh chip lọc theo trạng thái (có số đếm).
//  Dựng trên khung chung DlListBaseController (giống list Báo giá): bấm chip chỉ
//  bật/tắt các <filter> có sẵn trong search view nên khớp hoàn toàn bộ lọc gốc.
//
//  Vì sao cần: hàng đợi mặc định chỉ hiện việc-cần-làm (Cần nhận / Chờ kiểm) cho
//  gọn, nhưng phiếu ĐÃ XỬ LÝ không được biến mất không dấu vết — chip cho thấy
//  còn bao nhiêu ở mỗi trạng thái và mở ra bằng một cú bấm.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Khung chung cho 2 màn: chip là chọn-một, ánh xạ key ↔ tên <filter>.
class DlPickingSegmentController extends DlListBaseController {
    // Tên các <filter> mà chip quản (để chọn-một cho sạch).
    _managedNames() {
        return this.dlChips.filter((c) => c.filter).map((c) => c.filter);
    }

    _stateFilters() {
        const names = this._managedNames();
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && names.includes(i.name)
        );
    }

    // Chip đang sáng: không lọc gì → "all"; đang bật filter lẻ (dropdown) → "".
    _activeChip() {
        const active = this._stateFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        const chip = this.dlChips.find((c) => c.filter === active.name);
        return chip ? chip.key : "";
    }

    // Bấm chip: tắt mọi filter trạng thái đang bật rồi bật đúng 1 (chung nhóm OR).
    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._stateFilters();
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        if (key !== "all") {
            const chip = this.dlChips.find((c) => c.key === key);
            const it = chip && items.find((i) => i.name === chip.filter);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }

    // Số đếm theo trạng thái, gói trong ĐÚNG loại phiếu của màn (không đếm lẫn
    // phiếu chuyển/giao). Subclass khai _countDomain() + _countsFromStates().
    async _loadCounts() {
        const domain = this._countDomain();
        const groups = await this.orm.readGroup(
            "stock.picking",
            domain,
            ["state"],
            ["state"]
        );
        const byState = {};
        let total = 0;
        for (const g of groups) {
            // Odoo 17 trả count dưới khoá `<groupby>_count` (ở đây state_count);
            // __count không phải lúc nào cũng có ⇒ fallback như list Báo giá.
            const n = g.__count ?? g.state_count ?? 0;
            byState[g.state] = n;
            total += n;
        }
        const counts = this._countsFromStates(byState);
        counts.all = total;
        this.dlCounts = counts;
        await this._loadExtraCounts(counts, domain);
    }

    async _loadExtraCounts() {}
}

// ── Màn Nhận hàng NCC ────────────────────────────────────────────────────────
const RECEIPT_CHIPS = [
    { key: "todo", label: "Cần nhận", filter: "todo" },
    { key: "received", label: "Đã nhận", filter: "received" },
    { key: "draft", label: "Nháp", filter: "draft" },
    { key: "cancelled", label: "Đã huỷ", filter: "cancelled" },
    { key: "all", label: "Tất cả", filter: null },
];

export class DlReceiptListController extends DlPickingSegmentController {
    get dlChips() {
        return RECEIPT_CHIPS;
    }
    get dlCountNoun() {
        return "phiếu nhận";
    }
    _countDomain() {
        return [["picking_type_id.code", "=", "incoming"]];
    }
    _countsFromStates(s) {
        return {
            todo: (s.waiting || 0) + (s.confirmed || 0) + (s.assigned || 0),
            received: s.done || 0,
            draft: s.draft || 0,
            cancelled: s.cancel || 0,
        };
    }
}

registry.category("views").add("dl_receipt_list", {
    ...listView,
    Controller: DlReceiptListController,
});

// ── Màn Kiểm hàng ────────────────────────────────────────────────────────────
const QC_CHIPS = [
    { key: "pending", label: "Chờ kiểm", filter: "pending" },
    { key: "has_reject", label: "Có hàng loại", filter: "has_reject" },
    { key: "waiting_receipt", label: "Chờ hàng về", filter: "waiting_receipt" },
    { key: "checked", label: "Đã kiểm", filter: "checked" },
    { key: "all", label: "Tất cả", filter: null },
];

export class DlQcListController extends DlPickingSegmentController {
    get dlChips() {
        return QC_CHIPS;
    }
    get dlCountNoun() {
        return "phiếu kiểm";
    }
    _countDomain() {
        return [["picking_type_id.sequence_code", "=", "KC"]];
    }
    _countsFromStates(s) {
        // "Chờ kiểm" = state not in (done, cancel, waiting) — khớp filter pending.
        return {
            pending: (s.draft || 0) + (s.confirmed || 0) + (s.assigned || 0),
            waiting_receipt: s.waiting || 0,
            checked: s.done || 0,
        };
    }
    // "Có hàng loại" không phải một trạng thái mà là cờ dlm_qty_rejected_total>0
    // (cắt ngang các trạng thái) ⇒ đếm riêng.
    async _loadExtraCounts(counts, domain) {
        counts.has_reject = await this.orm.searchCount("stock.picking", [
            ...domain,
            ["dlm_qty_rejected_total", ">", 0],
        ]);
    }
}

registry.category("views").add("dl_qc_list", {
    ...listView,
    Controller: DlQcListController,
});
