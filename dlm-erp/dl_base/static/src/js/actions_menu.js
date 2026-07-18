/** @odoo-module **/

import { useEffect } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";

patch(SearchBar.prototype, {
    onSearchKeydown(ev) {
        if (ev.key !== "Enter" || !this.state.query.trim()) {
            return super.onSearchKeydown(ev);
        }

        const focusedItem = this.items[this.state.focusedIndex];
        if (!focusedItem || focusedItem.unselectable) {
            return super.onSearchKeydown(ev);
        }

        ev.preventDefault();

        for (const f of [...this.env.searchModel.facets]) {
            if (f.type === "field") {
                this.env.searchModel.deactivateGroup(f.groupId);
            }
        }

        const { searchItemId, label, operator, value } = focusedItem;
        this.env.searchModel.addAutoCompletionValues(searchItemId, {
            label,
            operator,
            value,
        });

        this.items.length = 0;
        this.state.expanded = [];
        this.state.focusedIndex = 0;
        this.subItems = {};
    },
});

export function buildActionsMenu(container, specs, { prepend = false } = {}) {
    if (!container) {
        return null;
    }
    const existing = container.querySelector(".dl-actions-menu");
    if (existing) {
        return existing;
    }

    const menu = document.createElement("div");
    menu.className = "dl-actions-menu";
    menu.setAttribute("tabindex", "0");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "dl-actions-toggle";
    toggle.setAttribute("aria-label", "Thao tác");
    toggle.dataset.tooltip = "Thao tác";
    toggle.innerHTML = '<i class="fa fa-ellipsis-v"></i>';

    const list = document.createElement("div");
    list.className = "dl-actions-list";
    list.setAttribute("role", "menu");
    for (const spec of specs) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "dl-actions-item" + (spec.danger ? " dl-actions-danger" : "");
        item.innerHTML = `<i class="fa ${spec.icon}"></i><span>${spec.label}</span>`;
        item.addEventListener("click", (ev) => {
            ev.stopPropagation();
            menu.classList.remove("dl-open");
            spec.onClick();
        });
        list.appendChild(item);
    }

    menu.appendChild(toggle);
    menu.appendChild(list);
    if (prepend) {
        container.prepend(menu);
    } else {
        container.appendChild(menu);
    }
    return menu;
}

export function setupStatusbarButtons(ctrl) {
    useEffect(() => {
        const root = ctrl.rootRef.el;
        if (!root) return;
        const buttons = root.querySelector(
            ".o_form_statusbar .o_statusbar_buttons"
        );
        const nav = root.querySelector(".o_control_panel_navigation");
        if (buttons && nav && buttons.parentElement !== nav) {
            buttons.classList.add("dl-cp-actions");
            nav.prepend(buttons);
        }
    });
}

export function setupFormActionsMenu(ctrl) {
    useEffect(() => {
        const root = ctrl.rootRef.el;
        if (!root) {
            return;
        }
        const container =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_breadcrumbs");
        // Tôn trọng activeActions: view chỉ-đọc (hoặc vai trò bị giới hạn) tắt
        // create/duplicate/delete ⇒ KHÔNG hiện Nhân bản / Xoá trong menu ⋮.
        const aa = (ctrl.archInfo && ctrl.archInfo.activeActions) || {};
        const specs = [];
        if (aa.create && aa.duplicate) {
            specs.push({
                label: "Nhân bản",
                icon: "fa-clone",
                onClick: () => ctrl.duplicateRecord && ctrl.duplicateRecord(),
            });
        }
        if (aa.delete) {
            specs.push({
                label: "Xoá",
                icon: "fa-trash-o",
                danger: true,
                onClick: () => ctrl.deleteRecord && ctrl.deleteRecord(),
            });
        }
        const menu = buildActionsMenu(container, specs, { prepend: true });
        if (menu) {
            // Ẩn menu khi bản ghi mới chưa lưu HOẶC không còn thao tác khả dụng.
            menu.style.display =
                specs.length === 0 || ctrl.model.root.isNew ? "none" : "";
        }

        // Tooltip tiếng Việt cho nút "→" mở bản ghi liên kết (many2one)
        root.querySelectorAll(".o_field_many2one .o_external_button").forEach((btn) => {
            btn.dataset.tooltip = "Mở trang thông tin";
            btn.setAttribute("aria-label", "Mở trang thông tin");
        });
    });
}
