/** @odoo-module **/
// ============================================================
//  DL BOM List — đồng bộ giao diện danh sách với các màn khác (S08).
//  Tái dùng DlListBaseController của dl_base (hạ tầng dùng chung).
//  Phần RIÊNG của BOM: chip lọc theo TRẠNG THÁI có số đếm (Tất cả · Nháp ·
//  Đã xác nhận · Đã khóa · Lưu trữ) thay cho dropdown ẩn cũ — cho dễ kiểm
//  soát trực quan (giống màn Báo giá / RFQ). Bấm chip = bật/tắt filter sẵn
//  trong search view nên đồng bộ hoàn toàn với bộ lọc gốc của Odoo.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

// key "all" = không filter trạng thái nào; các key còn lại trùng name filter
// trong search view (view_dl_bom_search) nên bấm chip là bật đúng filter đó.
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "draft", label: "Nháp" },
    { key: "confirmed", label: "Đã xác nhận" },
    { key: "locked", label: "Đã khóa" },
    { key: "archived", label: "Lưu trữ" },
];
const STATUS_KEYS = ["draft", "confirmed", "locked", "archived"];

export class DlBomListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "BOM";
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "dl.bom",
            [],
            ["status"],
            ["status"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.status_count ?? 0;
            counts[g.status] = n;
            total += n;
        }
        counts.all = total;
        this.dlCounts = counts;
    }

    _statusFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && STATUS_KEYS.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._statusFilters().find((i) => i.isActive);
        return active ? active.name : "all";
    }

    // Single-select: tắt hết filter trạng thái rồi bật 1 (giống màn Báo giá).
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

registry.category("views").add("dl_bom_list", {
    ...listView,
    Controller: DlBomListController,
});
