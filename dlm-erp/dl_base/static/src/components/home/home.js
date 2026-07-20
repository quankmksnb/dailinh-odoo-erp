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

// Card = một menu đích (menuXmlIds: cái ĐẦU TIÊN user thấy được sẽ dùng).
// Server đã lọc cây menu theo groups ⇒ card không tìm thấy menu nào là user
// không có quyền → ẨN card (RBAC hiển thị đồng nhất với menu, không cần
// hasGroup phía client).
const MODULE_CARDS = [
    {
        key: "customer",
        name: "Khách hàng",
        description: "Danh bạ khách hàng & liên hệ",
        icon: "fa-users",
        color: "#7c5caf",
        menuXmlIds: ["dl_partner.menu_dl_sale_customer"],
    },
    {
        key: "supplier",
        name: "NCC / Thầu phụ",
        description: "Nhà cung cấp & thầu phụ",
        icon: "fa-truck",
        color: "#2a8c82",
        // Trưởng KD chỉ có bản chỉ-đọc — menu nào thấy được thì mở menu đó.
        menuXmlIds: [
            "dl_partner.menu_dl_sale_supplier",
            "dl_partner.menu_dl_sale_supplier_readonly",
        ],
    },
    {
        key: "quotation",
        name: "Báo giá",
        description: "Yêu cầu báo giá & Báo giá",
        icon: "fa-file-text-o",
        color: "#4a90d9",
        // Trỏ thẳng menu hub Báo giá — trỏ menu cha "CRM & Báo giá" sẽ mở
        // nhầm menu con đầu tiên (Khách hàng).
        menuXmlIds: ["dl_sale.menu_dl_sale_quotation"],
    },
    {
        key: "product",
        name: "Sản phẩm & Vật tư",
        description: "Quản lý Sản phẩm và Vật tư",
        icon: "fa-cube",
        color: "#1a9e6f",
        menuXmlIds: ["dl_base.menu_dl_product"],
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        description: "BOM, bản vẽ & công thức tham số",
        icon: "fa-cogs",
        color: "#7c5caf",
        menuXmlIds: ["dl_base.menu_dl_technical"],
    },
    {
        key: "pricing",
        name: "Bảng giá",
        description: "Bảng giá SP Thương mại / Vật tư",
        icon: "fa-money",
        color: "#c49052",
        menuXmlIds: ["dl_product.menu_dl_pricing_root"],
    },
    {
        key: "config",
        name: "Cấu hình",
        description: "Tham số giá, phân quyền & danh mục dùng chung",
        icon: "fa-sliders",
        color: "#5a6a6a",
        menuXmlIds: ["dl_base.menu_dl_config"],
    },
];

export class DlHome extends Component {
    static template = "dl_base.DlHome";
    static props = { ...standardActionServiceProps };
    static components = { Dropdown, DropdownItem, ErrorHandler };

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");

        this._dlmApp = this.menuService
            .getApps()
            .find((app) => app.xmlid === "dl_base.menu_dl_root");
        if (this._dlmApp && this.menuService.getCurrentApp()?.id !== this._dlmApp.id) {
            this.menuService.setCurrentMenu(this._dlmApp);
        }
    }

    // Chỉ hiện card mà user thấy được menu đích (cây menu đã lọc theo groups).
    get cards() {
        return MODULE_CARDS.filter((card) => this._resolveCardMenu(card));
    }

    get _level1Menus() {
        if (!this._dlmApp) return [];
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        return tree?.childrenTree || [];
    }

    _findMenuByXmlId(node, xmlid) {
        if (!node) return null;
        if (node.xmlid === xmlid) return node;
        for (const child of node.childrenTree || []) {
            const found = this._findMenuByXmlId(child, xmlid);
            if (found) return found;
        }
        return null;
    }

    _resolveCardMenu(card) {
        if (!this._dlmApp) return null;
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        for (const xmlid of card.menuXmlIds || []) {
            const menu = this._findMenuByXmlId(tree, xmlid);
            if (menu) return menu;
        }
        return null;
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
        const menu = this._resolveCardMenu(card);
        if (!menu) return;
        // Ghi lại card đang active để rail/sidebar highlight (đồng bộ develop).
        setActiveKey(card.key);
        // Ưu tiên "trang chủ module" (landing) khi module có — đồng bộ với rail,
        // tránh nhảy thẳng vào menu con đầu tiên (view sâu). actionXmlId do
        // nav_patch của từng module gán vào card.
        if (card.actionXmlId) {
            this.actionService.doAction(card.actionXmlId, { clearBreadcrumbs: true });
            return;
        }
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
