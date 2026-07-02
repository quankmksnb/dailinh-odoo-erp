/** @odoo-module **/
// ============================================================
//  DL Quotation List — tuỳ biến màn danh sách Báo giá theo Figma:
//   1) Thanh CHIP lọc trạng thái có SỐ ĐẾM (Tất cả · Nháp · …).
//      Đọc số đếm bằng read_group; bấm chip = bật/tắt filter sẵn có
//      trong search view (draft/sent/approved/rejected) nên đồng bộ
//      hoàn toàn với bộ lọc gốc của Odoo.
//   2) Footer dưới đáy: "N báo giá" + chuyển pager gốc xuống đây.
//   3) Đưa nút tạo mới ("+ Tạo báo giá") sang cụm bên phải ô tìm kiếm.
//  Chèn DOM theo đúng pattern đang dùng ở dl_quotation_controller.js
//  (thao tác an toàn trong useEffect, gọi thẳng API sẵn có của Odoo).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useEffect } from "@odoo/owl";

// Thứ tự chip + ánh xạ sang tên filter trong search view.
// key "all" = không filter trạng thái nào.
const CHIPS = [
    { key: "all", label: "Tất cả" },
    { key: "draft", label: "Nháp" },
    { key: "sent", label: "Đã gửi" },
    { key: "approved", label: "Đã duyệt" },
    { key: "rejected", label: "Từ chối" },
];
const STATE_KEYS = ["draft", "sent", "approved", "rejected"];

export class DlQuotationListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dlCounts = {}; // { draft: n, sent: n, ..., all: total }

        // Số đếm tổng thể (không phụ thuộc filter) — nạp 1 lần khi mở màn.
        // Vào/ra 1 báo giá sẽ remount controller ⇒ số đếm tự làm mới.
        onWillStart(async () => {
            await this._loadCounts();
        });

        // Chạy sau mỗi lần render: dựng/cập nhật chip, footer, vị trí nút tạo.
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
        });
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

    // ── Filter trạng thái đang bật (đọc từ search model) ─────────
    _activeChip() {
        const active = this._stateFilters().find((i) => i.isActive);
        return active ? active.name : "all";
    }

    // ── Bấm chip: single-select (tắt hết filter trạng thái rồi bật 1) ──
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

    // ── Thanh chip lọc (thêm thành 1 hàng trong control panel) ──
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
            const n = this.dlCounts[c.key] ?? 0;
            chip.querySelector(".dl-chip-count").textContent = `· ${n}`;
            chip.classList.toggle("is-active", c.key === active);
        }
    }

    // ── Footer đáy list: "N báo giá" + pager gốc chuyển xuống ───
    // Chèn NGAY TRONG bảng (.o_list_renderer, sau <table>) để trôi
    // dưới bảng — tránh vùng .o_content bị con phủ toàn bộ chiều cao.
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
        footer.querySelector(".dl-list-count").textContent = `${total} báo giá`;

        // Đưa pager gốc (giữ nguyên chức năng chuyển trang) xuống footer.
        const pager = root.querySelector(".o_cp_pager");
        if (pager && pager.parentElement !== footer) {
            footer.appendChild(pager);
        }
    }

    // ── Caret ▾ mở Filters/Group By: HOVER vào là mở, RỜI ra là đóng ──
    // (Odoo Dropdown không có sẵn open-on-hover.) Mở khi chuột vào caret;
    // đóng sau ~180ms khi chuột rời KHỎI CẢ caret lẫn menu — đủ thời gian
    // di từ caret sang menu mà không bị đóng. Không gắn listener toàn cục.
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
        // Đóng sau 180ms, NHƯNG chỉ khi lúc đó chuột không nằm trên caret
        // cũng không trên menu (menu render ở portal → tra bằng :hover).
        // Kiểm tra tại thời điểm đóng nên không lệ thuộc thứ tự sự kiện.
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
        // Gắn mouseleave cho menu (khi rời menu → lên lịch đóng).
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

    // ── Nút "+ Tạo báo giá" → sang cụm actions (bên phải ô tìm kiếm) ──
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

registry.category("views").add("dl_quotation_list", {
    ...listView,
    Controller: DlQuotationListController,
});
