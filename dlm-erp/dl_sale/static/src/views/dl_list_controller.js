/** @odoo-module **/
// ============================================================
//  Danh sách DLM — LỚP CƠ SỞ dùng chung + view generic "dl_list".
//
//  DlListBaseController: gom hành vi chung của các màn danh sách tuỳ
//  biến (Báo giá / Khách hàng) theo Figma để KHÔNG lặp code:
//    • Chuyển nút tạo sang cụm bên phải ô tìm kiếm.
//    • Menu ⋮ Nhập/Xuất ở góc trên phải (buildActionsMenu dùng chung).
//    • Caret ▾ Filters/Group By: hover mở, rời ra tự đóng.
//    • Thanh CHIP lọc có SỐ ĐẾM (bấm = bật/tắt filter sẵn trong search).
//    • Footer đáy bảng: "N <đơn vị>" + pager gốc chuyển xuống.
//  Lớp con chỉ khai báo phần RIÊNG: dlChips, dlCountNoun, _loadCounts,
//  _activeChip, _selectChip, _chipCount (tuỳ chọn), _afterChipbar (hook).
//
//  DlListController (registry "dl_list"): view generic — chỉ thêm menu
//  ⋮ Nhập/Xuất. Giữ để tương thích js_class="dl_list" (chưa dùng trong XML).
//  Mọi thao tác DOM chạy trong useEffect, gọi thẳng API sẵn của Odoo.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useEffect } from "@odoo/owl";
import { buildActionsMenu } from "../js/actions_menu";

export class DlListBaseController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dlCounts = {}; // { <key>: n, all: total }

        // Số đếm tổng không phụ thuộc filter — nạp 1 lần; vào/ra 1 bản ghi
        // sẽ remount controller ⇒ số đếm tự làm mới.
        onWillStart(async () => {
            await this._loadCounts();
        });

        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            this._dlRenderChrome(root);
        });
    }

    // Điểm mở rộng cho lớp con (vd: khách hàng thêm avatar).
    _dlRenderChrome(root) {
        this._relocateCreateButton(root);
        this._renderActionsMenu(root);
        this._setupSearchHover(root);
        this._renderChipbar(root);
        this._renderFooter(root);
    }

    get dlChips() {
        return [];
    } // [{ key, label }]
    get dlCountNoun() {
        return "";
    } // đơn vị footer ("báo giá" / "khách hàng")
    async _loadCounts() {} // nạp this.dlCounts
    _activeChip() {
        return "all";
    }
    _selectChip() {}
    _chipCount(chip) {
        return this.dlCounts[chip.key];
    }
    _afterChipbar() {} // hook sau khi dựng hàng chip (vd: chèn nút List/Kanban)

    _relocateCreateButton(root) {
        const buttons = root.querySelector(".o_control_panel_main_buttons");
        const actions = root.querySelector(".o_control_panel_actions");
        if (buttons && actions && buttons.parentElement !== actions) {
            buttons.classList.add("dl-create-cluster");
            actions.appendChild(buttons);
        }
    }

    // Cog gốc bị ẩn theo design; tái dùng handler Nhập/Xuất gốc của Odoo.
    _renderActionsMenu(root) {
        const host =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_actions");
        buildActionsMenu(host, [
            { label: "Nhập", icon: "fa-upload", onClick: () => this._dlImport() },
            { label: "Xuất", icon: "fa-download", onClick: () => this.onExportData() },
        ]);
    }

    _dlImport() {
        const sm = this.env.searchModel;
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { model: sm.resModel, context: sm.context },
        });
    }

    _renderChipbar(root) {
        const cp = root.querySelector(".o_control_panel");
        if (!cp) {
            return;
        }
        let bar = cp.querySelector(".dl-chipbar");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "dl-chipbar";
            for (const c of this.dlChips) {
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
        for (const c of this.dlChips) {
            const chip = bar.querySelector(`.dl-chip[data-key="${c.key}"]`);
            if (!chip) {
                continue;
            }
            chip.querySelector(".dl-chip-label").textContent = c.label;
            const n = this._chipCount(c) ?? 0;
            chip.querySelector(".dl-chip-count").textContent = `· ${n}`;
            chip.classList.toggle("is-active", c.key === active);
        }
        this._afterChipbar(root, bar);
    }

    // Chèn NGAY TRONG bảng (.o_list_renderer) để footer trôi dưới bảng.
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
        footer.querySelector(".dl-list-count").textContent = `${total} ${this.dlCountNoun}`;

        const pager = root.querySelector(".o_cp_pager");
        if (pager && pager.parentElement !== footer) {
            footer.appendChild(pager);
        }
    }

    // Odoo Dropdown không có open-on-hover: tự mở/đóng, đóng sau ~180ms khi
    // chuột rời KHỎI CẢ caret lẫn menu (đủ thời gian di từ caret sang menu).
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
        // Kiểm tra tại thời điểm đóng nên không lệ thuộc thứ tự sự kiện
        // (menu render ở portal → tra bằng :hover).
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
}

// Giữ để tương thích js_class="dl_list"; hiện chưa dùng trong XML.
export class DlListController extends ListController {
    setup() {
        super.setup();
        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            const container =
                root.querySelector(".o_control_panel_navigation") ||
                root.querySelector(".o_control_panel_breadcrumbs");
            buildActionsMenu(
                container,
                [
                    { label: "Nhập", icon: "fa-upload", onClick: () => this.dlImport() },
                    {
                        label: "Xuất",
                        icon: "fa-download",
                        onClick: () => this.onExportData && this.onExportData(),
                    },
                ],
                { prepend: true }
            );
        });
    }

    dlImport() {
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { model: this.props.resModel, context: this.props.context },
        });
    }
}

registry.category("views").add("dl_list", {
    ...listView,
    Controller: DlListController,
});
