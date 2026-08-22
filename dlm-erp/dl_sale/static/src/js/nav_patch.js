/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";

const APPROVAL_ACTION = "dl_sale.action_dl_quote_approval";

// Rail: nhóm "Báo giá" xổ thành các mục con điều hướng THẲNG (không có màn hub
// trung chuyển). Điều hướng theo actionXmlId; menuXmlIds chỉ để lọc RBAC (mục nào
// user không thấy menu thì ẩn).
//
// Thứ tự = HÀNG ĐỢI TRƯỚC, RỒI ĐẾN DÒNG ĐỜI. Bản trước mở đầu bằng "Danh sách
// báo giá" rồi mới tới RFQ — ngược mạch: RFQ đẻ ra báo giá, không phải ngược lại.
// "Quản lý RFQ" đứng đầu vì đó mới là hòm việc thật của Sales (list có cột ưu
// tiên đẩy RFQ Kỹ thuật vừa trả về lên trên).
//
// ⚠️ Bấm NHÃN NHÓM chỉ xổ/thu submenu (`toggleSubmenu`), KHÔNG mở màn nào —
// nên mục đầu không phải "màn mặc định". Bản trước comment ngược ở chỗ này.
const QUOTE_CHILDREN = [
    {
        key: "rfq_list",
        name: "Quản lý RFQ",
        icon: "fa-inbox",
        actionXmlId: "dl_technical.action_dl_quotation_request",
        menuXmlIds: ["dl_technical.menu_rfq_all"],
    },
    {
        key: "rfq_create",
        name: "Tạo RFQ",
        icon: "fa-plus-square",
        actionXmlId: "dl_technical.action_dl_quotation_request_create",
        menuXmlIds: ["dl_technical.menu_rfq_create"],
    },
    {
        key: "quotation_list",
        name: "Danh sách báo giá",
        icon: "fa-file-text-o",
        actionXmlId: "dl_sale.action_dl_quotation",
        menuXmlIds: ["dl_sale.menu_dl_sale_quotation"],
    },
    {
        key: "sale_order",
        name: "Đơn bán hàng",
        icon: "fa-shopping-cart",
        actionXmlId: "dl_sale.action_dl_sale_order",
        menuXmlIds: ["dl_sale.menu_dl_sale_order"],
    },
];

function wireQuoteRail(items) {
    const item = items && items.find((i) => i.key === "quotation");
    if (item) {
        item.children = QUOTE_CHILDREN;
    }
}

// Gán action cho mục "Phê duyệt" của rail (leaf, không có màn con).
function wireApproval(items) {
    const item = items && items.find((i) => i.key === "approval");
    if (item && !item.actionXmlId) {
        item.actionXmlId = APPROVAL_ACTION;
    }
}

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireQuoteRail(this.railItems);
        wireApproval(this.railItems);
        // Badge "Phê duyệt": đếm số báo giá vượt ngưỡng đang chờ mà user hiện
        // tại được duyệt. Chỉ Trưởng KD/Giám đốc thấy mục này nên user khác
        // không phát sinh truy vấn thừa. useService gọi trong setup (patch chạy
        // trong setup) nên hợp lệ.
        const orm = useService("orm");
        this.registerBadge("approval", () =>
            orm.call("dl.pricing.approval.request", "get_pending_approval_count", [])
        );
    },
});
