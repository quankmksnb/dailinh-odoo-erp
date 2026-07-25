/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { sidebarState, toggleSidebar, setActiveKey } from "@dl_base/js/sidebar_state";

const DLM_APP_XMLID = "dl_base.menu_dl_root";

const RAIL_ITEMS = [
    { key: "customer", name: "Khách hàng", icon: "fa-users", actionXmlId: "dl_partner.action_dl_customer" },
    { key: "supplier", name: "NCC / Thầu phụ", icon: "fa-truck", actionXmlId: "dl_partner.action_dl_supplier" },
    { key: "quotation", name: "Báo giá", icon: "fa-file-text-o", actionXmlId: "dl_sale.action_dl_quotation" },
    // Phê duyệt — chỉ hiện với user thấy được menu (CEO/Trưởng KD/vai trò duyệt).
    // menuXmlIds ⇒ rail LỌC RBAC đồng bộ Home; actionXmlId do dl_sale nav_patch gán.
    {
        key: "approval",
        name: "Phê duyệt",
        icon: "fa-check-square-o",
        actionXmlId: null,
        menuXmlIds: ["dl_sale.menu_dl_sale_quote_approval"],
    },
    { key: "product", name: "Sản phẩm & Vật tư", icon: "fa-cube", actionXmlId: null },
    { key: "technical", name: "Kỹ thuật", icon: "fa-cogs", actionXmlId: null },
    { key: "pricing", name: "Bảng giá", icon: "fa-money", actionXmlId: null },
    { key: "report", name: "Báo cáo", icon: "fa-bar-chart", actionXmlId: null },
    { key: "config", name: "Cấu hình", icon: "fa-sliders", actionXmlId: null },
];

export class DlmRail extends Component {
    static template = "dl_base.DlmRail";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.railItems = RAIL_ITEMS;
        this._dlmApp = this.menuService.getApps().find((app) => app.xmlid === DLM_APP_XMLID);
        this.state = useState({ visible: this._inDlmApp(), expanded: {} });
        this.sidebar = useState(sidebarState);

        // "MENUS:APP-CHANGED" chỉ phát khi ĐỔI app (selectMenu / app switcher);
        // điều hướng nội bộ DLM bằng doAction không đổi app nên rail vẫn hiện.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            this.state.visible = this._inDlmApp();
        });

        // Đồng bộ class trên <body> để CSS ẩn navbar Odoo + chừa chỗ cho rail.
        useEffect(
            (visible, collapsed) => {
                document.body.classList.toggle("dlm-rail-active", visible);
                document.body.classList.toggle("dlm-rail-collapsed", visible && collapsed);
                return () => {
                    document.body.classList.remove("dlm-rail-active");
                    document.body.classList.remove("dlm-rail-collapsed");
                };
            },
            () => [this.state.visible, this.sidebar.collapsed]
        );
    }

    toggleSidebar() {
        toggleSidebar();
    }

    _inDlmApp() {
        const app = this.menuService.getCurrentApp();
        return !!app && app.xmlid === DLM_APP_XMLID;
    }

    // Mục KHÔNG khai báo menuXmlIds → luôn hiện (giữ nguyên hành vi cũ). Mục CÓ
    // khai báo (vd Phê duyệt) → chỉ hiện khi user thấy được menu đích trong cây
    // menu đã lọc theo groups ⇒ rail đồng bộ RBAC với các card ở Trang chủ.
    get visibleItems() {
        return this.railItems.filter((item) => {
            if (!item.menuXmlIds || !item.menuXmlIds.length) return true;
            return item.menuXmlIds.some((xmlid) => this._menuVisible(xmlid));
        });
    }

    _menuVisible(xmlid) {
        if (!this._dlmApp) return false;
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        return !!this._findMenuByXmlId(tree, xmlid);
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

    toggleSubmenu(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    openModule(actionXmlId, key) {
        if (!actionXmlId) return;
        if (key) {
            setActiveKey(key);
        }
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("main_components").add("dlm_rail.DlmRail", { Component: DlmRail });
