/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const TECHNICAL_ACTION = "dl_technical.action_dl_technical_home";

// Rail: dẹp hub Kỹ thuật thành mục con điều hướng thẳng (bỏ màn hub trung chuyển).
const TECHNICAL_CHILDREN = [
    {
        key: "bom_quotation",
        name: "BOM sản phẩm / BTP",
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

// Home (fallback): giữ card mở hub như cũ.
function wireTechnicalHome(cards) {
    const item = cards && cards.find((i) => i.key === "technical");
    if (item && !item.actionXmlId) {
        item.actionXmlId = TECHNICAL_ACTION;
    }
}

function wireTechnicalRail(items) {
    const item = items && items.find((i) => i.key === "technical");
    if (item) {
        item.children = TECHNICAL_CHILDREN;
    }
}

patch(DlHome.prototype, {
    setup() {
        super.setup(...arguments);
        wireTechnicalHome(this.cards);
    },
});

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireTechnicalRail(this.railItems);
    },
});
