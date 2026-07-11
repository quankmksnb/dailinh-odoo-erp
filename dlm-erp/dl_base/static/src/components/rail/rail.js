/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { sidebarState, toggleSidebar } from "@dl_base/js/sidebar_state";

const DLM_APP_XMLID = "dl_base.menu_dl_root";

const RAIL_ITEMS = [
    { key: "home", name: "Trang chủ", icon: "fa-home", actionXmlId: "dl_base.action_dl_home" },
    { key: "customer", name: "Khách hàng", icon: "fa-users", actionXmlId: "dl_partner.action_dl_customer" },
    { key: "supplier", name: "NCC / Thầu phụ", icon: "fa-truck", actionXmlId: "dl_partner.action_dl_supplier" },
    { key: "quotation", name: "Báo giá", icon: "fa-file-text-o", actionXmlId: "dl_sale.action_dl_quotation" },
    { key: "product", name: "Sản phẩm", icon: "fa-cube", actionXmlId: "dl_product.action_dl_product" },
    { key: "technical", name: "Kỹ thuật", icon: "fa-cogs", actionXmlId: null },
    { key: "material", name: "Vật tư", icon: "fa-cubes", actionXmlId: "dlm_material.action_dl_material" },
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
        this.state = useState({ visible: this._inDlmApp() });
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

    openModule(actionXmlId) {
        if (!actionXmlId) return;
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("main_components").add("dlm_rail.DlmRail", { Component: DlmRail });
