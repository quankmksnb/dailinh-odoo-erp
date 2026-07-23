/** @odoo-module **/
// ============================================================
//  DL Quote Approval List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_quote_approval_list" (quote_approval_views.xml).
//  Phần RIÊNG: chip lọc theo trạng thái yêu cầu duyệt có số đếm (Tất cả ·
//  Chờ duyệt · Đã duyệt · Từ chối · Đã hủy). Chip bật/tắt filter sẵn trong
//  search view nên đồng bộ với bộ lọc gốc của Odoo.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "pending", label: "Chờ duyệt" },
    { key: "approved", label: "Đã duyệt" },
    { key: "rejected", label: "Từ chối" },
    { key: "cancelled", label: "Đã hủy" },
];
const STATE_KEYS = ["pending", "approved", "rejected", "cancelled"];

export class DlQuoteApprovalListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "yêu cầu";
    }

    async _loadCounts() {
        // Chỉ đếm yêu cầu duyệt BÁO GIÁ — khớp domain của action màn này.
        const groups = await this.orm.readGroup(
            "dl.pricing.approval.request",
            [["request_type", "=", "quote_over_threshold"]],
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
        this.dlCounts = counts;
    }

    _stateFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && STATE_KEYS.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._stateFilters().find((i) => i.isActive);
        return active ? active.name : "all";
    }

    // Single-select: tắt hết filter trạng thái rồi bật 1
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

registry.category("views").add("dl_quote_approval_list", {
    ...listView,
    Controller: DlQuoteApprovalListController,
});
