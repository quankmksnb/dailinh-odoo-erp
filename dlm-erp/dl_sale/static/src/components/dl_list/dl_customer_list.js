/** @odoo-module **/
// ============================================================
//  DL Customer List — tuỳ biến màn Danh sách Khách hàng theo Figma
//  (cùng khuôn với dl_quotation_list.js):
//   1) Chip lọc theo LOẠI khách hàng có số đếm (Tất cả · Cá nhân ·
//      Doanh nghiệp · Đại lý) — bấm = bật/tắt filter sẵn có trong
//      search view (filter_individual/company/dealer).
//   2) Chuyển nút chuyển view (List/Kanban) vào ngay hàng chip.
//   3) Footer đáy bảng: "N khách hàng" + pager gốc.
//   4) Nút tạo ("+ Thêm") sang cụm bên phải ô tìm kiếm; caret tìm kiếm
//      hover-mở-menu.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useEffect } from "@odoo/owl";

// key: định danh chip · filter: tên filter trong search view · ctype:
// giá trị customer_type để lấy số đếm. key "all" = không lọc loại.
const CHIPS = [
    { key: "all",        label: "Tất cả",       filter: null,                ctype: null },
    { key: "individual", label: "Cá nhân",      filter: "filter_individual", ctype: "individual" },
    { key: "company",    label: "Doanh nghiệp", filter: "filter_company",    ctype: "company" },
    { key: "dealer",     label: "Đại lý",       filter: "filter_dealer",     ctype: "dealer" },
];
const FILTER_NAMES = CHIPS.filter((c) => c.filter).map((c) => c.filter);

// Avatar chữ cái: bảng màu pastel + chọn màu ổn định theo tên.
const AVA_PALETTE = [
    { bg: "#fde2e4", fg: "#b23a48" },
    { bg: "#dbe7ff", fg: "#1e4fa3" },
    { bg: "#e3f6e8", fg: "#1b7a3d" },
    { bg: "#fff1cc", fg: "#8a5a00" },
    { bg: "#ece0fb", fg: "#5b3fa0" },
    { bg: "#ffe1f0", fg: "#a3226e" },
    { bg: "#d9f2f4", fg: "#0f6b73" },
];
function avaColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) {
        h = (h * 31 + name.charCodeAt(i)) >>> 0;
    }
    return AVA_PALETTE[h % AVA_PALETTE.length];
}

export class DlCustomerListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dlCounts = {}; // { individual: n, company: n, dealer: n, all: total }

        onWillStart(async () => {
            await this._loadCounts();
        });

        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            this._relocateCreateButton(root);
            this._renderActionsMenu(root);
            this._setupSearchHover(root);
            this._renderChipbar(root);
            this._renderFooter(root);
            this._renderAvatars(root);
        });
    }

    async _loadCounts() {
        const groups = await this.orm.readGroup(
            "res.partner",
            [["is_dlm_customer", "=", true]],
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

    // Chip đang bật (đọc từ search model) → trả về key chip.
    _activeChip() {
        const active = this._typeFilters().find((i) => i.isActive);
        if (!active) {
            return "all";
        }
        const chip = CHIPS.find((c) => c.filter === active.name);
        return chip ? chip.key : "all";
    }

    // Bấm chip: single-select (tắt hết filter loại rồi bật 1).
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

    // ── Hàng chip (+ chuyển nút List/Kanban vào cuối hàng) ──────
    _renderChipbar(root) {
        const cp = root.querySelector(".o_control_panel");
        if (!cp) {
            return;
        }
        let bar = cp.querySelector(".dl-chipbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "dl-chipbar";
            for (const c of CHIPS) {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "dl-chip";
                chip.dataset.key = c.key;
                chip.innerHTML =
                    '<span class="dl-chip-label"></span>' +
                    '<span class="dl-chip-count"></span>';
                chip.addEventListener("click", () => this._selectChip(c.key));
                bar.appendChild(chip);
            }
            cp.appendChild(bar);
        }
        const active = this._activeChip();
        for (const c of CHIPS) {
            const chip = bar.querySelector(`.dl-chip[data-key="${c.key}"]`);
            if (!chip) {
                continue;
            }
            chip.querySelector(".dl-chip-label").textContent = c.label;
            const n = this._chipCount(c) ?? 0;
            chip.querySelector(".dl-chip-count").textContent = `· ${n}`;
            chip.classList.toggle("is-active", c.key === active);
        }

        // Chuyển cụm nút chuyển view (List/Kanban) vào cuối hàng chip.
        const sw = root.querySelector("nav.o_cp_switch_buttons");
        if (sw && sw.parentElement !== bar) {
            sw.classList.add("dl-view-switch");
            bar.appendChild(sw);
        }
    }

    // ── Footer đáy bảng: "N khách hàng" + pager gốc chuyển xuống ──
    _renderFooter(root) {
        const renderer = root.querySelector(".o_list_renderer");
        if (!renderer) {
            return;
        }
        let footer = renderer.querySelector(".dl-list-footer");
        if (!footer) {
            footer = document.createElement("div");
            footer.className = "dl-list-footer";
            const count = document.createElement("span");
            count.className = "dl-list-count";
            footer.appendChild(count);
            renderer.appendChild(footer);
        }
        const total = this.model.root.count ?? 0;
        footer.querySelector(".dl-list-count").textContent = `${total} khách hàng`;

        const pager = root.querySelector(".o_cp_pager");
        if (pager && pager.parentElement !== footer) {
            footer.appendChild(pager);
        }
    }

    // ── Caret ▾ Filters/Group By: hover mở, rời ra tự đóng ──────
    _setupSearchHover(root) {
        const toggler = root.querySelector(".o_searchview_dropdown_toggler");
        if (!toggler || toggler.dataset.dlHoverOpen) {
            return;
        }
        toggler.dataset.dlHoverOpen = "1";

        let timer = null;
        const isOpen = () => toggler.getAttribute("aria-expanded") === "true";
        const cancel = () => {
            clearTimeout(timer);
            timer = null;
        };
        const scheduleClose = () => {
            cancel();
            timer = setTimeout(() => {
                const menu = document.querySelector(".o_search_bar_menu");
                const overToggler = toggler.matches(":hover");
                const overMenu = menu && menu.matches(":hover");
                if (isOpen() && !overToggler && !overMenu) {
                    toggler.click();
                }
            }, 180);
        };
        const bindMenu = () => {
            const menu = document.querySelector(".o_search_bar_menu");
            if (menu && !menu.dataset.dlHoverBound) {
                menu.dataset.dlHoverBound = "1";
                menu.addEventListener("mouseenter", cancel);
                menu.addEventListener("mouseleave", scheduleClose);
            }
        };

        toggler.addEventListener("mouseenter", () => {
            cancel();
            if (!isOpen()) {
                toggler.click();
            }
            setTimeout(bindMenu, 50);
        });
        toggler.addEventListener("mouseleave", scheduleClose);
    }

    // ── Avatar chữ cái nền màu: Odoo trả hình người xám cho khách
    //    hàng (không có user nội bộ). Ẩn hình đó (CSS) và tự chèn 1
    //    avatar chữ cái theo tên vào ô avatar_128 của từng dòng.
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

    // ── Nút "+ Thêm" → sang cụm actions (bên phải ô tìm kiếm) ───
    _relocateCreateButton(root) {
        const buttons = root.querySelector(".o_control_panel_main_buttons");
        const actions = root.querySelector(".o_control_panel_actions");
        if (buttons && actions && buttons.parentElement !== actions) {
            buttons.classList.add("dl-create-cluster");
            actions.appendChild(buttons);
        }
    }

    // ── Menu Actions ⋮ (Nhập/Xuất) ở góc trên phải ─────────────
    // Cog gốc của Odoo bị ẩn theo design (control_panel.scss) nên dựng lại
    // menu ⋮ dùng đúng khung .dl-actions-menu có sẵn. Tái dùng handler gốc:
    // Xuất → onExportData() (dialog xuất của Odoo); Nhập → client action "import".
    _renderActionsMenu(root) {
        if (root.querySelector(".dl-actions-menu")) {
            return;
        }
        // Cụm điều hướng bên phải (pager/switch đã được chuyển đi) = góc trên
        // bên phải; fallback sang cụm actions nếu không có.
        const host = root.querySelector(".o_control_panel_navigation")
            || root.querySelector(".o_control_panel_actions");
        if (!host) {
            return;
        }
        const menu = document.createElement("div");
        menu.className = "dl-actions-menu";
        menu.setAttribute("tabindex", "0");
        menu.innerHTML =
            '<button type="button" class="dl-actions-toggle" aria-label="Thao tác">' +
            '<i class="fa fa-ellipsis-v"></i></button>' +
            '<div class="dl-actions-list" role="menu">' +
            '<button type="button" class="dl-actions-item" data-act="import">' +
            '<i class="fa fa-upload"></i> Nhập</button>' +
            '<button type="button" class="dl-actions-item" data-act="export">' +
            '<i class="fa fa-download"></i> Xuất</button>' +
            "</div>";
        menu.querySelector('[data-act="import"]')
            .addEventListener("click", () => this._dlImport());
        menu.querySelector('[data-act="export"]')
            .addEventListener("click", () => this.onExportData());
        host.appendChild(menu);
    }

    // Nhập: mở client action "import" gốc của Odoo cho model hiện tại.
    _dlImport() {
        const sm = this.env.searchModel;
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { model: sm.resModel, context: sm.context },
        });
    }
}

registry.category("views").add("dl_customer_list", {
    ...listView,
    Controller: DlCustomerListController,
});
