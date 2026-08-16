/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlmRail } from "@dl_base/components/rail/rail";

// Rail: nhóm Kỹ thuật xổ thành mục con điều hướng thẳng (không có màn hub trung
// chuyển). Card trên Home không cần actionXmlId — DlHome tự mở menu con đầu tiên.
const TECHNICAL_CHILDREN = [
    {
        key: "bom_quotation",
        name: "BOM sản phẩm / Bán thành phẩm",
        icon: "fa-list-alt",
        actionXmlId: "dl_technical.action_dl_bom",
        menuXmlIds: ["dl_technical.menu_bom_quotation"],
    },
    {
        key: "bom_template",
        name: "BOM mẫu",
        icon: "fa-clone",
        actionXmlId: "dl_technical.action_dl_bom_template",
        menuXmlIds: ["dl_technical.menu_bom_template"],
    },
    {
        key: "rfq",
        name: "RFQ cần xử lý",
        icon: "fa-inbox",
        actionXmlId: "dl_technical.action_dl_quotation_request_my",
        menuXmlIds: ["dl_technical.menu_rfq_my"],
    },
    {
        key: "drawing",
        name: "Bản vẽ kỹ thuật",
        icon: "fa-file-pdf-o",
        actionXmlId: "dl_technical.action_dl_drawing",
        menuXmlIds: ["dl_technical.menu_drawing"],
    },
];

function wireTechnicalRail(items) {
    const item = items && items.find((i) => i.key === "technical");
    if (item) {
        item.children = TECHNICAL_CHILDREN;
    }
}

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireTechnicalRail(this.railItems);
    },
});
