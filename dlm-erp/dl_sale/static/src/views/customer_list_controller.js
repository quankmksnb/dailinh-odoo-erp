/** @odoo-module **/
// ============================================================
//  DL Customer List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_customer_list" (dùng ở customer_views.xml).
//  Phần RIÊNG của khách hàng:
//   1) Chip lọc theo LOẠI có số đếm (Tất cả · Cá nhân · Doanh nghiệp ·
//      Đại lý) — bấm = bật/tắt filter sẵn trong search view.
//   2) Chuyển nút chuyển view (List/Kanban) vào cuối hàng chip.
//   3) Avatar chữ cái nền màu cho từng dòng.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "./dl_list_controller";

// filter: tên filter trong search view · ctype: giá trị customer_type để đếm.
// key "all" = không lọc loại.
const CHIPS = [
    { key: "all",        label: "Tất cả",       filter: null,                ctype: null },
    { key: "individual", label: "Cá nhân",      filter: "filter_individual", ctype: "individual" },
    { key: "company",    label: "Doanh nghiệp", filter: "filter_company",    ctype: "company" },
    { key: "dealer",     label: "Đại lý",       filter: "filter_dealer",     ctype: "dealer" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

const AVA_PALETTE = [
    { bg: "#fde2e4", fg: "#b23a48" },
    { bg: "#dbe7ff", fg: "#1e4fa3" },
    { bg: "#e3f6e8", fg: "#1b7a3d" },
    { bg: "#fff1cc", fg: "#8a5a00" },
    { bg: "#ece0fb", fg: "#5b3fa0" },
    { bg: "#ffe1f0", fg: "#a3226e" },
    { bg: "#d9f2f4", fg: "#0f6b73" },
];
// Hash tên → màu ổn định (cùng tên luôn ra cùng màu)
function avaColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) {
        h = (h * 31 + name.charCodeAt(i)) >>> 0;
    }
    return AVA_PALETTE[h % AVA_PALETTE.length];
}

export class DlCustomerListController extends DlListBaseController {
    get dlChips() {
        return CHIPS;
    }

    get dlCountNoun() {
        return "khách hàng";
    }

    _dlRenderChrome(root) {
        super._dlRenderChrome(root);
        this._renderAvatars(root);
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "res.partner",
            [["partner_role", "=", "customer"]],
            ["customer_type"],
            ["customer_type"]
        );
        const counts = {};
        let total = 0;
        for (const g of groups) {
            const n = g.__count ?? g.customer_type_count ?? 0;
            counts[g.customer_type] = n;
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

    // Single-select: tắt hết filter loại rồi bật 1
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
        return chip.key === "all" ? this.dlCounts.all : this.dlCounts[chip.ctype];
    }

    _afterChipbar(root, bar) {
        const sw = root.querySelector("nav.o_cp_switch_buttons");
        if (sw && sw.parentElement !== bar) {
            sw.classList.add("dl-view-switch");
            bar.appendChild(sw);
        }
    }

    // Odoo trả hình người xám cho khách hàng (không có user nội bộ): ẩn bằng
    // CSS và tự chèn avatar chữ cái theo tên vào ô avatar_128 mỗi dòng.
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

registry.category("views").add("dl_customer_list", {
    ...listView,
    Controller: DlCustomerListController,
});
