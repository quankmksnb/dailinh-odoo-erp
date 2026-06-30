/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODULES = [
    {
        key: "customer",
        name: "Khách hàng",
        icon: "fa-users",
        color: "#7B5EA7",
        description: "Danh sách khách hàng",
        actionXmlId: "dl_sale.action_dl_customer",
    },
    {
        key: "quotation",
        name: "Báo giá",
        icon: "fa-file-text-o",
        color: "#2E86AB",
        description: "Tạo và quản lý báo giá",
        actionXmlId: "dl_sale.action_dl_quotation",
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        icon: "fa-cogs",
        color: "#5B8DB8",
        description: "Sản phẩm, BOM mẫu, BOM tham số",
        actionXmlId: null,
    },
    {
        key: "material",
        name: "Vật tư",
        icon: "fa-cubes",
        color: "#4A9B7F",
        description: "Danh mục vật tư, Bảng giá, Nhân công",
        actionXmlId: null,
    },
    {
        key: "report",
        name: "Báo cáo",
        icon: "fa-bar-chart",
        color: "#C0813A",
        description: "KPI báo giá, Margin, Win-rate",
        actionXmlId: null,
    },
    {
        key: "config",
        name: "Cấu hình",
        icon: "fa-sliders",
        color: "#7A7A7A",
        description: "Tham số giá, Quy tắc phê duyệt (CEO/Admin)",
        actionXmlId: null,
    },
];

export class DlHome extends Component {
    static template = "dl_base.DlHome";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.modules = MODULES;
    }

    openModule(actionXmlId) {
        if (!actionXmlId) return;
        this.actionService.doAction(actionXmlId);
    }
}

registry.category("actions").add("dl_base.DlHomeAction", DlHome);
