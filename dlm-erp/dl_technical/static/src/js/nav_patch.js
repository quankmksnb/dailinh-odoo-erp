/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlmRail } from "@dl_base/components/rail/rail";

// Rail: nhóm Kỹ thuật xổ thành mục con điều hướng thẳng (không có màn hub trung
// chuyển). Card trên Home không cần actionXmlId — DlHome tự mở menu con đầu tiên.
//
// Thứ tự = ngày làm việc của KTV: mở hòm việc → lập/sửa BOM → gắn bản vẽ.
// "RFQ cần xử lý" đứng đầu vì đó là màn KTV land vào (LANDING_RULES) — bản
// trước để nó ở vị trí thứ 3, land một đằng rail chỉ một nẻo. "BOM mẫu" là
// thư viện mẫu, đụng thưa hơn hẳn ⇒ xuống cuối.
const TECHNICAL_CHILDREN = [
    {
        key: "rfq",
        name: "RFQ cần xử lý",
        icon: "fa-inbox",
        actionXmlId: "dl_technical.action_dl_quotation_request_my",
        menuXmlIds: ["dl_technical.menu_rfq_my"],
    },
    {
        key: "bom_quotation",
        name: "BOM sản phẩm / Bán thành phẩm",
        icon: "fa-list-alt",
        actionXmlId: "dl_technical.action_dl_bom",
        menuXmlIds: ["dl_technical.menu_bom_quotation"],
    },
    {
        key: "drawing",
        name: "Bản vẽ kỹ thuật",
        icon: "fa-file-pdf-o",
        actionXmlId: "dl_technical.action_dl_drawing",
        menuXmlIds: ["dl_technical.menu_drawing"],
    },
    {
        key: "bom_template",
        name: "BOM mẫu",
        icon: "fa-clone",
        actionXmlId: "dl_technical.action_dl_bom_template",
        menuXmlIds: ["dl_technical.menu_bom_template"],
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
