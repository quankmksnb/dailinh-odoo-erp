/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
    {
        key: "rfq",
        name: "Đơn hàng mới (RFQ)",
        desc: "Lập báo giá mới, cấu hình tỷ lệ chi phí & xuất mẫu Nội bộ / Khách hàng",
        icon: "fa-file-text-o",
        actionXmlId: "dl_sale.action_dl_rfq",
    },
    {
        key: "request",
        name: "Yêu cầu khách hàng",
        desc: "Tiếp nhận & theo dõi yêu cầu báo giá từ khách hàng",
        icon: "fa-inbox",
        actionXmlId: "dl_sale.action_dl_customer_request",
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
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dl_sale.DlQuoteHome", DlQuoteHome);
