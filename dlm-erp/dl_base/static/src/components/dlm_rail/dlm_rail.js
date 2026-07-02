/** @odoo-module **/
// ============================================================
//  DLM-ERP — Rail điều hướng thu gọn (shell của app DLM-ERP)
//  Đăng ký vào main_components nên component luôn tồn tại, nhưng
//  CHỈ hiển thị khi người dùng đang ở trong app DLM-ERP (menu gốc
//  dl_base.menu_dl_root): Trang chủ + các view Khách hàng/Báo giá.
//  Ở các trang Odoo gốc (Apps, Discuss, Settings…) rail bị ẩn và
//  navbar tím mặc định của Odoo được khôi phục.
//  Trên chính Trang chủ (.dl-home) rail vẫn ẩn vì Home đã có
//  sidebar đầy đủ (xử lý bằng CSS). Tái dùng action sẵn có.
// ============================================================

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";

// App gốc của DLM-ERP — dùng để nhận biết "đang ở trong DLM-ERP"
const DLM_APP_XMLID = "dl_base.menu_dl_root";

// Mirror danh sách điều hướng của Trang chủ (dạng icon thu gọn)
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

        // menuService phát "MENUS:APP-CHANGED" mỗi khi app hiện tại đổi
        // (chuyển qua app khác qua selectMenu / app switcher). Điều hướng
        // trong nội bộ DLM bằng doAction không đổi app nên rail vẫn hiện.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            this.state.visible = this._inDlmApp();
        });

        // Đồng bộ class trên <body> để CSS biết khi nào rail đang bật:
        // chỉ khi đó mới ẩn navbar Odoo + dịch nội dung chừa chỗ cho rail.
        useEffect(
            (visible) => {
                document.body.classList.toggle("dlm-rail-active", visible);
                return () => document.body.classList.remove("dlm-rail-active");
            },
            () => [this.state.visible]
        );
    }

    // Đang ở trong app DLM-ERP? (app gốc hiện tại là menu_dl_root)
    _inDlmApp() {
        const app = this.menuService.getCurrentApp();
        return !!app && app.xmlid === DLM_APP_XMLID;
    }

    openModule(actionXmlId) {
        if (!actionXmlId) return;
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài
        // (giống hành vi chuyển app của Odoo).
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("main_components").add("dlm_rail.DlmRail", { Component: DlmRail });
