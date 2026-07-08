/** @odoo-module **/
// ============================================================
//  DL Supplier List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_supplier_list" (dùng ở supplier_views.xml).
//  Đồng bộ giao diện với danh sách Khách hàng:
//   1) Chip lọc theo NHÓM CUNG CẤP có số đếm.
//   2) Avatar chữ cái nền màu cho từng dòng.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "./dl_list_controller";

const CHIPS = [
    { key: "all",         label: "Tất cả",        filter: null,                      grp: null },
    { key: "steel",       label: "Thép xây dựng", filter: "filter_grp_steel",        grp: "steel" },
    { key: "paint",       label: "Sơn - mạ",      filter: "filter_grp_paint",        grp: "paint" },
    { key: "electric",    label: "Vật tư điện",   filter: "filter_grp_electric",     grp: "electric" },
    { key: "subcontract", label: "Gia công",      filter: "filter_grp_subcontract",  grp: "subcontract" },
    { key: "other",       label: "Khác",          filter: "filter_grp_other",        grp: "other" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

const AVA_PALETTE = [
    { bg: "#dbe7ff", fg: "#1e4fa3" },
    { bg: "#e3f6e8", fg: "#1b7a3d" },
    { bg: "#fff1cc", fg: "#8a5a00" },
    { bg: "#ece0fb", fg: "#5b3fa0" },
    { bg: "#d9f2f4", fg: "#0f6b73" },
    { bg: "#fde2e4", fg: "#b23a48" },
];
function avaColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) {
        h = (h * 31 + name.charCodeAt(i)) >>> 0;
    }
    return AVA_PALETTE[h % AVA_PALETTE.length];
}

export class DlSupplierListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "nhà cung cấp";
    }

    _dlRenderChrome(root) {
        super._dlRenderChrome(root);
        this._renderAvatars(root);
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "res.partner",
            [["is_dlm_supplier", "=", true]],
            ["dlm_supplier_group"],
            ["dlm_supplier_group"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.dlm_supplier_group_count ?? 0;
            counts[g.dlm_supplier_group] = n;
            total += n;
        }
        counts.all = total;
        this.dlCounts = counts;
    }

    _typeFilters() {
        return this.env.searchModel.getSearchItems(
            (i) => i.type === "filter" && FILTER_NAMES.includes(i.name)
        );
    }

    _activeChip() {
        const active = this._typeFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        const chip = CHIPS.find((c) => c.filter === active.name);
        return chip ? chip.key : "all";
    }

    _selectChip(key) {
        const sm = this.env.searchModel;
        const items = this._typeFilters();
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        const chip = CHIPS.find((c) => c.key === key);
        if (chip && chip.filter) {
            const it = items.find((i) => i.name === chip.filter);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }

    _chipCount(chip) {
        return chip.key === "all" ? this.dlCounts.all : this.dlCounts[chip.grp];
    }

    // Chèn avatar chữ cái theo tên NCC vào ô avatar_128 mỗi dòng.
    _renderAvatars(root) {
        const rows = root.querySelectorAll(".o_list_table tbody tr.o_data_row");
        for (const row of rows) {
            const cell = row.querySelector("td[name='avatar_128']");
            const nameCell = row.querySelector("td[name='name']");
            if (!cell || !nameCell) {
                continue;
            }
            const name = (nameCell.textContent || "").trim();
            let ava = cell.querySelector(".dl-letter-ava");
            if (!ava) {
                ava = document.createElement("span");
                ava.className = "dl-letter-ava";
                cell.appendChild(ava);
            }
            const c = avaColor(name);
            ava.textContent = name ? name[0].toUpperCase() : "?";
            ava.style.background = c.bg;
            ava.style.color = c.fg;
        }
    }
}

registry.category("views").add("dl_supplier_list", {
    ...listView,
    Controller: DlSupplierListController,
});
