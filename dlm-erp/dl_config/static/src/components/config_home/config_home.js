/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
    {
        key: "currency",
        name: "Tiền tệ",
        desc: "Danh mục tiền tệ, tỷ giá, ký hiệu",
        icon: "fa-money",
        actionXmlId: "dl_config.action_dl_currency",
    },
    {
        key: "uom",
        name: "Đơn vị tính",
        desc: "Đơn vị và nhóm quy đổi",
        icon: "fa-balance-scale",
        actionXmlId: "dl_config.action_dl_uom",
    },
    {
        key: "vat",
        name: "Thuế VAT",
        desc: "Thuế suất áp dụng cho báo giá",
        icon: "fa-percent",
        actionXmlId: "dl_config.action_dl_vat",
    },
    {
        key: "company",
        name: "Công ty",
        desc: "Thông tin công ty phát hành",
        icon: "fa-building-o",
        actionXmlId: "dl_config.action_dl_company",
    },
];

export class DlConfigHome extends Component {
    static template = "dl_config.DlConfigHome";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.cards = CARDS;
    }

    openCard(actionXmlId) {
        if (!actionXmlId) {
            return;
        }
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dl_config.DlConfigHome", DlConfigHome);
