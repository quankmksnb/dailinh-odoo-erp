/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
    {
        key: "bom_quotation",
        name: "BOM sản phẩm / BTP",
        desc: "Công thức BOM gắn với 1 thành phẩm hoặc bán thành phẩm cụ thể",
        icon: "fa-list-alt",
        actionXmlId: "dl_bom.action_dl_bom",
    },
    {
        key: "bom_template",
        name: "Khung mẫu cấp nhóm",
        desc: "BOM trừu tượng theo nhóm sản phẩm, dùng để sao chép khi tạo SP mới",
        icon: "fa-clone",
        actionXmlId: "dl_bom.action_dl_bom_template",
    },
    {
        key: "rfq",
        name: "Yêu cầu báo giá (RFQ)",
        desc: "Nhận RFQ từ Sales, đánh giá SP mới/tương tự/cũ",
        icon: "fa-inbox",
        actionXmlId: "dl_bom.action_dl_quotation_request_my",
    },
    {
        key: "product",
        name: "Danh mục sản phẩm",
        desc: "Thành phẩm và thông số kỹ thuật",
        icon: "fa-cube",
        actionXmlId: "dl_bom.action_dl_product",
    },
    {
        key: "product_category",
        name: "Nhóm sản phẩm",
        desc: "Nhóm SP và BOM mẫu mặc định",
        icon: "fa-sitemap",
        actionXmlId: "dl_bom.action_dl_product_category",
    },
    {
        key: "semi_product",
        name: "Bán thành phẩm",
        desc: "Cấu kiện trung gian dùng trong BOM đệ quy",
        icon: "fa-puzzle-piece",
        actionXmlId: "dl_bom.action_dl_semi_product",
    },
    {
        key: "drawing",
        name: "Bản vẽ kỹ thuật",
        desc: "Bản vẽ và file đính kèm theo sản phẩm",
        icon: "fa-file-pdf-o",
        actionXmlId: "dl_bom.action_dl_drawing",
    },
];

export class DlTechnicalHome extends Component {
    static template = "dl_bom.DlTechnicalHome";
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

registry.category("actions").add("dl_bom.DlTechnicalHome", DlTechnicalHome);
