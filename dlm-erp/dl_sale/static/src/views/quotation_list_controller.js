/** @odoo-module **/
// ============================================================
//  DL Quotation List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_quotation_list" (dùng ở quotation_views.xml).
//  Phần RIÊNG của báo giá: chip lọc theo TRẠNG THÁI có số đếm (Tất cả ·
//  Nháp · Đã gửi · Đã duyệt · Từ chối). Bấm chip = bật/tắt filter sẵn
//  trong search view nên đồng bộ hoàn toàn với bộ lọc gốc của Odoo.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "./dl_list_controller";

// key "all" = không filter trạng thái nào
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "draft", label: "Nháp" },
    { key: "sent", label: "Đã gửi" },
    { key: "approved", label: "Đã duyệt" },
    { key: "rejected", label: "Từ chối" },
];
const STATE_KEYS = ["draft", "sent", "approved", "rejected"];

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

registry.category("views").add("dl_quotation_list", {
    ...listView,
    Controller: DlQuotationListController,
});
