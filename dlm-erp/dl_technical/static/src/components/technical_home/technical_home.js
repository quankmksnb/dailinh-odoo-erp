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
        actionXmlId: "dl_technical.action_dl_bom",
    },
    {
        key: "bom_template",
        name: "BOM mẫu",
        desc: "BOM trừu tượng theo nhóm sản phẩm, dùng để sao chép khi tạo SP mới",
        icon: "fa-clone",
        actionXmlId: "dl_technical.action_dl_bom_template",
    },
    {
        key: "rfq",
        name: "Yêu cầu báo giá (RFQ)",
        desc: "Nhận RFQ từ Sales, gán sản phẩm thật hoặc đánh dấu không khả thi",
        icon: "fa-inbox",
        actionXmlId: "dl_technical.action_dl_quotation_request_my",
    },
    {
        key: "drawing",
        name: "Bản vẽ kỹ thuật",
        desc: "Bản vẽ và file đính kèm theo sản phẩm",
        icon: "fa-file-pdf-o",
        actionXmlId: "dl_technical.action_dl_drawing",
    },
];
// Loại đo lường (Rule) / Hình dạng đo lường (Shape) — bỏ khỏi trang chủ Kỹ
// thuật (dữ liệu cấu hình, ít dùng hằng ngày). Vẫn truy cập đầy đủ qua menu
// "Sản phẩm & Vật tư > Đo lường" (dl_product/views/menus.xml).

export class DlTechnicalHome extends Component {
    static template = "dl_technical.DlTechnicalHome";
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

registry.category("actions").add("dl_technical.DlTechnicalHome", DlTechnicalHome);
