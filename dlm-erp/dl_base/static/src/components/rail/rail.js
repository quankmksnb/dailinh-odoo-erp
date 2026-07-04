/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";

const DLM_APP_XMLID = "dl_base.menu_dl_root";

const RAIL_ITEMS = [
    { key: "home", name: "Trang chủ", icon: "fa-home", actionXmlId: "dl_base.action_dl_home" },
    { key: "customer", name: "Khách hàng", icon: "fa-users", actionXmlId: "dl_sale.action_dl_customer" },
    { key: "quotation", name: "Báo giá", icon: "fa-file-text-o", actionXmlId: "dl_sale.action_dl_quotation" },
    { key: "technical", name: "Kỹ thuật", icon: "fa-cogs", actionXmlId: null },
    { key: "material", name: "Vật tư", icon: "fa-cubes", actionXmlId: null },
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

        // "MENUS:APP-CHANGED" chỉ phát khi ĐỔI app (selectMenu / app switcher);
        // điều hướng nội bộ DLM bằng doAction không đổi app nên rail vẫn hiện.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            this.state.visible = this._inDlmApp();
        });

        // Đồng bộ class trên <body> để CSS ẩn navbar Odoo + chừa chỗ cho rail.
        useEffect(
            (visible) => {
                document.body.classList.toggle("dlm-rail-active", visible);
                return () => document.body.classList.remove("dlm-rail-active");
            },
            () => [this.state.visible]
        );
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
