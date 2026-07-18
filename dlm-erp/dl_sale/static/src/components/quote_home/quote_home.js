/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
    {
        key: "rfq_create",
        name: "Tạo RFQ",
        desc: "Tạo yêu cầu báo giá mới gửi Kỹ thuật xử lý",
        icon: "fa-plus-square",
        actionXmlId: "dl_technical.action_dl_quotation_request_create",
    },
    {
        key: "rfq_list",
        name: "Quản lý RFQ",
        desc: "Danh sách yêu cầu báo giá & trạng thái xử lý (mới / đang xử lý / đã báo giá)",
        icon: "fa-inbox",
        actionXmlId: "dl_technical.action_dl_quotation_request",
    },
    {
        key: "quotation_list",
        name: "Danh sách báo giá",
        desc: "Xem, gửi khách và theo dõi báo giá đã lập",
        icon: "fa-file-text-o",
        actionXmlId: "dl_sale.action_dl_quotation",
    },
    {
        key: "sale_order",
        name: "Đơn bán hàng",
        desc: "Đơn bán hàng chốt từ báo giá khách đã đồng ý",
        icon: "fa-shopping-cart",
        actionXmlId: "dl_sale.action_dl_sale_order",
    },
];

export class DlQuoteHome extends Component {
    static template = "dl_sale.DlQuoteHome";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.cards = CARDS;
    }

    openCard(actionXmlId) {
        if (!actionXmlId) {
            return;
        }
        this.actionService.doAction(actionXmlId);
    }
}

registry.category("actions").add("dl_sale.DlQuoteHome", DlQuoteHome);
