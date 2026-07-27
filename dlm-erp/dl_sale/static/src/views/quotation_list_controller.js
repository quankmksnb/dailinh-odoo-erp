/** @odoo-module **/
// ============================================================
//  DL Quotation List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_quotation_list" (dùng ở quotation_views.xml).
//  Phần RIÊNG của báo giá: chip lọc theo TRẠNG THÁI có số đếm. Bấm chip =
//  bật/tắt filter sẵn trong search view nên đồng bộ hoàn toàn với bộ lọc
//  gốc của Odoo.
//
//  QUAN TRỌNG — single-select phải quản TẤT CẢ filter trạng thái (kể cả
//  composite open/closed/history + filter mặc định 'open' trên action), vì
//  mọi filter state nằm CHUNG một nhóm OR trong search view. Nếu chỉ tắt
//  vài filter, composite 'open' vẫn active ⇒ 'open OR draft' ⇒ chip không
//  lọc được (bug cũ chỉ quản 4 filter draft/sent/approved/rejected).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// Chip hiển thị — mỗi key trùng name của một <filter> trong search view.
// "open" là composite (pipeline đang sống) = filter mặc định của action;
// "history" = superseded (bản cũ bị thay thế).
const CHIPS = [
    { key: "open", label: "Đang xử lý" },
    { key: "draft", label: "Nháp" },
    { key: "approved", label: "Đã duyệt" },
    { key: "sent", label: "Đã gửi" },
    { key: "revision_requested", label: "Điều chỉnh" },
    { key: "accepted", label: "Khách đồng ý" },
    { key: "ordered", label: "Đã lên đơn" },
    { key: "rejected", label: "Từ chối" },
    { key: "expired", label: "Hết hiệu lực" },
    { key: "history", label: "Lịch sử" },
];

// Toàn bộ filter trạng thái mà chip cần quản để single-select sạch — gồm cả
// composite (open/closed/history) lẫn từng trạng thái. Bấm 1 chip: tắt hết
// những cái đang active trong tập này rồi bật đúng 1.
const MANAGED_FILTERS = [
    "open", "closed", "history",
    "draft", "approved", "sent", "revision_requested",
    "accepted", "ordered", "rejected", "expired",
    "cancelled", "superseded",
];

export class DlQuotationListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "báo giá";
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "dl.quotation",
            [],
            ["state"],
            ["state"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.state_count ?? 0;
            counts[g.state] = n;
            total += n;
        }
        counts.all = total;
        // Số đếm cho các chip gộp (đồng bộ đúng domain composite ở search view).
        const sum = (...keys) => keys.reduce((s, k) => s + (counts[k] || 0), 0);
        counts.open = sum(
            "draft", "approved", "sent", "revision_requested", "accepted", "ordered"
        );
        counts.closed = sum("rejected", "expired", "cancelled");
        counts.history = counts.superseded || 0;
        this.dlCounts = counts;
    }

    // Tất cả filter trạng thái trong search view (composite + từng state).
    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && MANAGED_FILTERS.includes(i.name)
        );
    }

    // Chip đang active = filter state đang bật mà trùng một chip key. Mặc định
    // action bật 'open' ⇒ chip "Đang xử lý" sáng.
    _activeChip() {
        const chipKeys = new Set(CHIPS.map((c) => c.key));
        const active = this._stateFilters().find(
            (i) => i.isActive && chipKeys.has(i.name)
        );
        return active ? active.name : "all";
    }

    // Single-select: tắt MỌI filter trạng thái đang active rồi bật đúng 1.
    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._stateFilters();
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

registry.category("views").add("dl_quotation_list", {
    ...listView,
    Controller: DlQuotationListController,
});
