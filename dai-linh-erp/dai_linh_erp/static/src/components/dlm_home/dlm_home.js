/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class DlmHome extends Component {
    static template = "dai_linh_erp.DlmHome";

    setup() {
        this.action = useService("action");
    }

    get modules() {
        return [
            {
                id: "customers",
                name: "Khách hàng",
                description: "Quản lý danh sách khách hàng cá nhân, doanh nghiệp và đại lý",
                icon: "fa-users",
                color: "dlm-blue",
                action: "dai_linh_erp.action_dlm_customer",
                group: "Kinh Doanh",
            },
            {
                id: "products",
                name: "Sản phẩm",
                description: "Danh mục sản phẩm cơ khí theo đơn đặt hàng",
                icon: "fa-cube",
                color: "dlm-indigo",
                action: null,
                group: "Kỹ Thuật",
                soon: true,
            },
            {
                id: "materials",
                name: "Vật tư",
                description: "Quản lý nguyên vật liệu và giá nhập theo thời kỳ",
                icon: "fa-cogs",
                color: "dlm-teal",
                action: null,
                group: "Kỹ Thuật",
                soon: true,
            },
            {
                id: "bom",
                name: "Định mức BOM",
                description: "Bản vẽ kỹ thuật và định mức nguyên vật liệu theo sản phẩm",
                icon: "fa-sitemap",
                color: "dlm-orange",
                action: null,
                group: "Kỹ Thuật",
                soon: true,
            },
            {
                id: "quotation",
                name: "Báo giá",
                description: "Lập và theo dõi báo giá tích hợp BOM tự động",
                icon: "fa-file-text-o",
                color: "dlm-green",
                action: null,
                group: "Kinh Doanh",
                soon: true,
            },
            {
                id: "approval",
                name: "Phê duyệt",
                description: "Luồng phê duyệt báo giá theo ngưỡng giá trị và lợi nhuận",
                icon: "fa-check-circle-o",
                color: "dlm-red",
                action: null,
                group: "Quản Lý",
                soon: true,
            },
        ];
    }

    openModule(mod) {
        if (!mod.action) return;
        this.action.doAction(mod.action);
    }
}

registry.category("actions").add("dai_linh_erp.DlmHome", DlmHome);
