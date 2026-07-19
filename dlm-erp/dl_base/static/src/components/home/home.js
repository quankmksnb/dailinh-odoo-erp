/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ErrorHandler } from "@web/core/utils/components";
import { setActiveKey } from "@dl_base/js/sidebar_state";

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
        actionXmlId: "dl_sale.action_dl_quotation_home",
    },
    {
        key: "product",
        name: "Sản phẩm & Vật tư",
        description: "Quản lý Sản phẩm và Vật tư",
        icon: "fa-cube",
        color: "#1a9e6f",
        actionXmlId: "dl_product.action_dl_product_home",
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        description: "BOM, bản vẽ & công thức tham số",
        icon: "fa-cogs",
        color: "#7c5caf",
        actionXmlId: "dl_technical.action_dl_technical_home",
    },
    {
        key: "pricing",
        name: "Bảng giá",
        description: "Bảng giá SP Thương mại / Vật tư",
        icon: "fa-money",
        color: "#c49052",
        actionXmlId: "dl_product.action_dl_pricing_home",
    },
    {
        key: "config",
        name: "Cấu hình",
        description: "Tham số giá, phân quyền & danh mục dùng chung",
        icon: "fa-sliders",
        color: "#5a6a6a",
        actionXmlId: "dl_config.action_dl_config_home",
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
        if (!card.actionXmlId) return;
        setActiveKey(card.key);
        this.actionService.doAction(card.actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dl_base.DlHomeAction", DlHome);
