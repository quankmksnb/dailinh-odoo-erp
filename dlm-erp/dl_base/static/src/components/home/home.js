/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ErrorHandler } from "@web/core/utils/components";

const systrayRegistry = registry.category("systray");

const MODULE_CARDS = [
    {
        key: "customer",
        name: "Khách hàng",
        description: "Danh bạ khách hàng & liên hệ",
        icon: "fa-users",
        color: "#7c5caf",
        actionXmlId: "dl_partner.action_dl_customer",
    },
    {
        key: "supplier",
        name: "NCC / Thầu phụ",
        description: "Nhà cung cấp & thầu phụ",
        icon: "fa-truck",
        color: "#2a8c82",
        actionXmlId: "dl_partner.action_dl_supplier",
    },
    {
        key: "quotation",
        name: "Báo giá",
        description: "Yêu cầu báo giá & Báo giá",
        icon: "fa-file-text-o",
        color: "#4a90d9",
        menuXmlId: "dl_base.menu_dl_sale",
    },
    {
        key: "product",
        name: "Sản phẩm",
        description: "Thành phẩm, bán thành phẩm & nhóm SP",
        icon: "fa-cube",
        color: "#1a9e6f",
        menuXmlId: "dl_product.menu_dl_product_root",
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        description: "BOM, bản vẽ & công thức tham số",
        icon: "fa-cogs",
        color: "#7c5caf",
        menuXmlId: "dl_base.menu_dl_technical",
    },
    {
        key: "material",
        name: "Vật tư",
        description: "Danh mục vật tư & bảng giá",
        icon: "fa-cubes",
        color: "#c49052",
        menuXmlId: "dl_base.menu_dl_material",
    },
    {
        key: "config",
        name: "Cấu hình",
        description: "Tham số giá, phân quyền & danh mục dùng chung",
        icon: "fa-sliders",
        color: "#5a6a6a",
        menuXmlId: "dl_base.menu_dl_config",
    },
];

export class DlHome extends Component {
    static template = "dl_base.DlHome";
    static props = { ...standardActionServiceProps };
    static components = { Dropdown, DropdownItem, ErrorHandler };

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.cards = MODULE_CARDS;

        this._dlmApp = this.menuService
            .getApps()
            .find((app) => app.xmlid === "dl_base.menu_dl_root");
        if (this._dlmApp && this.menuService.getCurrentApp()?.id !== this._dlmApp.id) {
            this.menuService.setCurrentMenu(this._dlmApp);
        }
    }

    get _level1Menus() {
        if (!this._dlmApp) return [];
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        return tree?.childrenTree || [];
    }

    get systrayItems() {
        const HIDDEN = ["web.debug_mode_menu"];
        return systrayRegistry
            .getEntries()
            .filter(([key]) => !HIDDEN.includes(key))
            .map(([key, value]) => ({ key, ...value }))
            .filter((item) => ("isDisplayed" in item ? item.isDisplayed(this.env) : true))
            .reverse();
    }

    handleItemError(error, item) {
        item.isDisplayed = () => false;
        Promise.resolve().then(() => { throw error; });
    }

    get apps() {
        return this.menuService.getApps();
    }

    getMenuItemHref(payload) {
        const parts = [`menu_id=${payload.id}`];
        if (payload.actionID) parts.push(`action=${payload.actionID}`);
        return "#" + parts.join("&");
    }

    onAppSelected(menu) {
        if (menu) this.menuService.selectMenu(menu);
    }

    openCard(card) {
        if (card.actionXmlId) {
            this.actionService.doAction(card.actionXmlId, { clearBreadcrumbs: true });
            return;
        }
        if (!card.menuXmlId) return;
        const menu = this._level1Menus.find((m) => m.xmlid === card.menuXmlId);
        if (!menu) return;
        const target = this._findFirstActionMenu(menu);
        if (target) this.menuService.selectMenu(target);
    }

    _findFirstActionMenu(menu) {
        if (menu.actionID) return menu;
        for (const child of menu.childrenTree || []) {
            const found = this._findFirstActionMenu(child);
            if (found) return found;
        }
        return null;
    }
}

registry.category("actions").add("dl_base.DlHomeAction", DlHome);
