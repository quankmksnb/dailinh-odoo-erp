/** @odoo-module **/

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
        this.dlCounts = {};
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

    _dlRenderChrome(root) {
        this._relocateCreateButton(root);
        this._renderActionsMenu(root);
        this._setupSearchHover(root);
        this._renderChipbar(root);
        this._renderFooter(root);
    }

    get dlChips() {
        return [];
    } 
    get dlCountNoun() {
        return "";
    }
    async _loadCounts() {} // nạp this.dlCounts
    _activeChip() {
        return "all";
    }
    _selectChip() {}
    _chipCount(chip) {
        return this.dlCounts[chip.key];
    }
    _afterChipbar() {} 

    _relocateCreateButton(root) {
        const buttons = root.querySelector(".o_control_panel_main_buttons");
        const actions = root.querySelector(".o_control_panel_actions");
        if (buttons && actions && buttons.parentElement !== actions) {
            buttons.classList.add("dl-create-cluster");
            actions.appendChild(buttons);
        }
    }

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
}
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
