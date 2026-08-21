/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";
import { wireRailChildren } from "@dl_base/js/rail_children";

// ⚠️ KHÔNG phải bản nav_patch thứ 5+: hàm dùng chung `wireRailChildren` nằm ở
// dl_base/static/src/js/rail_children.js. File này chỉ khai DỮ LIỆU mục con.

const PURCHASE_CHILDREN = [
  {
    // 🔴 THIẾU TỪ K22 tới 2026-08-21: menu + action đã có từ đầu nhưng không ai
    // khai vào mảng này ⇒ hàng đợi riêng của Mua hàng KHÔNG hề xuất hiện trên
    // rail, chỉ vào được bằng URL. Đúng cái bẫy mà comment đầu file nav_patch
    // của dl_inventory đã cảnh báo (vấp lần đầu với "Điều phối đơn hàng").
    //
    // Đứng đầu nhóm vì đây là việc CHẶN NGƯỜI KHÁC: báo giá của Sales không gửi
    // được cho khách chừng nào Mua hàng chưa ghi nhận giá NCC báo về.
    key: "purchase_rfq_queue",
    name: "Hỏi giá chờ trả lời",
    icon: "fa-hourglass-half",
    preferMenu: true,
    menuXmlIds: ["dl_purchase.menu_dl_purchase_rfq_queue"],
  },
  {
    key: "purchase_order",
    name: "Đơn mua hàng",
    icon: "fa-shopping-cart",
    preferMenu: true,
    menuXmlIds: ["dl_purchase.menu_dl_purchase_order"],
  },
  {
    key: "vendor_return",
    name: "Trả hàng nhà cung cấp",
    icon: "fa-reply",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_vendor_return"],
  },
];

patch(DlmRail.prototype, {
  setup() {
    super.setup(...arguments);
    wireRailChildren(this.railItems, "purchase", PURCHASE_CHILDREN);

    const orm = useService("orm");

    // Badge hỏi giá — khớp ĐÚNG domain của action_dl_purchase_rfq_queue, để số
    // trên rail bằng số dòng khi mở màn.
    this.registerBadge("purchase_rfq_queue", () =>
      orm.searchCount("dl.purchase.order", [
        ["state", "=", "sent"],
        ["dlm_quotation_id", "!=", false],
      ]),
    );

    // Badge = việc CHƯA XONG của Mua hàng: đơn nháp (điều phối vừa đẩy sang)
    // và đơn đã gửi hỏi giá chưa có hồi âm. Đơn đã chốt không đếm — nó đang
    // nằm ở kho chờ hàng về, không phải việc của Mua hàng nữa.
    //
    // 🔴 CỐ Ý TRỪ phần đã tính ở badge hỏi giá. `groupBadgeCount` CỘNG DỒN badge
    // các mục con lên đầu nhóm khi submenu thu gọn — để nguyên `["draft","sent"]`
    // thì đơn hỏi giá bị đếm HAI LẦN trên nhãn "Mua hàng". Tổng của hai badge
    // vẫn đúng bằng draft+sent như trước, chỉ chia lại cho khỏi chồng.
    this.registerBadge("purchase_order", () =>
      orm.searchCount("dl.purchase.order", [
        "|",
        ["state", "=", "draft"],
        "&",
        ["state", "=", "sent"],
        ["dlm_quotation_id", "=", false],
      ]),
    );

    // ♻️ Badge "Trả hàng NCC" DỜI TỪ dl_inventory sang đây cùng với mục menu.
    // Phiếu trả sinh ra ở trạng thái NHÁP và nằm im cho tới khi Mua hàng thoả
    // thuận xong với NCC — không đếm thì nó là việc tồn vô hình.
    this.registerBadge("vendor_return", () =>
      orm.searchCount("stock.picking", [
        ["picking_type_id.sequence_code", "=", "TR"],
        ["state", "=", "draft"],
      ]),
    );
  },
});
