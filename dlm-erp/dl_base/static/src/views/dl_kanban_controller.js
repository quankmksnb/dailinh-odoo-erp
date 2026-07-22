/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useEffect } from "@odoo/owl";
import { buildActionsMenu } from "../js/actions_menu";

export class DlKanbanBaseController extends KanbanController {
    setup() {
        super.setup();
        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            this._relocateCreateButton(root);
            this._renderActionsMenu(root);
            this._renderFilterDropdowns(root);
        });
    }

    _renderActionsMenu(root) {
        const host =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_actions");
        buildActionsMenu(host, [
            { label: "Nhập dữ liệu", icon: "fa-upload", onClick: () => this._dlImport() },
            { label: "Xuất dữ liệu", icon: "fa-download", onClick: () => this._dlExport() },
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

    _dlExport() {
        this.actionService.switchView("list");
    }

    get dlFilterDropdowns() {
        return [];
    }

    _relocateCreateButton(root) {
        const buttons = root.querySelector(".o_control_panel_main_buttons");
        const actions = root.querySelector(".o_control_panel_actions");
        if (buttons && actions && buttons.parentElement !== actions) {
            buttons.classList.add("dl-create-cluster");
            actions.appendChild(buttons);
        }
    }

    // Chỉ hiện các filter thực sự có trong search view của action hiện tại —
    // cùng 1 js_class được nhiều action dùng lại với search view khác nhau
    // (VD: màn Sản phẩm lọc Gia công/Thương mại, màn Vật tư lọc Vật tư/BTP,
    // màn Bảng giá không có filter loại SP).
    _dlAvailableDropdowns() {
        const sm = this.env.searchModel;
        const available = new Set(
            sm.getSearchItems((i) => i.type === "filter").map((i) => i.name)
        );
        return this.dlFilterDropdowns
            .map((dd) => ({
                ...dd,
                filters: dd.filters.filter((f) => available.has(f.name)),
            }))
            .filter((dd) => dd.filters.length);
    }

    _renderFilterDropdowns(root) {
        const dropdowns = this._dlAvailableDropdowns();
        if (!dropdowns.length) {
            return;
        }
        const actions = root.querySelector(".o_control_panel_actions");
        if (!actions) {
            return;
        }

        let container = actions.querySelector(".dl-filter-group");
        if (!container) {
            container = document.createElement("div");
            container.className = "dl-filter-group";
            const createCluster = actions.querySelector(".dl-create-cluster");
            if (createCluster) {
                actions.insertBefore(container, createCluster);
            } else {
                actions.appendChild(container);
            }
        }

        for (const dd of dropdowns) {
            let select = container.querySelector(`select[data-dl-filter="${dd.key}"]`);
            if (!select) {
                select = document.createElement("select");
                select.className = "dl-filter-select";
                select.dataset.dlFilter = dd.key;

                const allOpt = document.createElement("option");
                allOpt.value = "";
                allOpt.textContent = dd.label;
                select.appendChild(allOpt);

                for (const f of dd.filters) {
                    const opt = document.createElement("option");
                    opt.value = f.name;
                    opt.textContent = f.label;
                    select.appendChild(opt);
                }

                select.addEventListener("change", () =>
                    this._onFilterDropdownChange(dd, select.value)
                );
                container.appendChild(select);
            }

            select.value = this._getActiveDropdownFilter(dd) || "";
        }
    }

    _getActiveDropdownFilter(dd) {
        const sm = this.env.searchModel;
        const names = dd.filters.map((f) => f.name);
        const items = sm.getSearchItems(
            (i) => i.type === "filter" && names.includes(i.name)
        );
        const active = items.find((i) => i.isActive);
        return active ? active.name : "";
    }

    _onFilterDropdownChange(dd, value) {
        const sm = this.env.searchModel;
        const names = dd.filters.map((f) => f.name);
        const items = sm.getSearchItems(
            (i) => i.type === "filter" && names.includes(i.name)
        );
        for (const it of items) {
            if (it.isActive) {
                sm.toggleSearchItem(it.id);
            }
        }
        if (value) {
            const it = items.find((i) => i.name === value);
            if (it) {
                sm.toggleSearchItem(it.id);
            }
        }
    }
}

registry.category("views").add("dl_kanban", {
    ...kanbanView,
    Controller: DlKanbanBaseController,
});
