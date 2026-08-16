/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";
import { wireRailChildren } from "@dl_base/js/rail_children";

// ⚠️ KHÔNG phải bản nav_patch thứ 5+: hàm dùng chung `wireRailChildren` nằm ở
// dl_base/static/src/js/rail_children.js. File này chỉ khai DỮ LIỆU mục con.

const PURCHASE_CHILDREN = [
  {
    // Việc chính của Mua hàng, đứng đầu. Badge đếm đơn NHÁP + CHỜ BÁO GIÁ —
    // đơn nháp do điều phối kho sinh ra sẽ nằm im nếu không có gì đếm nó.
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
    // Badge = việc CHƯA XONG của Mua hàng: đơn nháp (điều phối vừa đẩy sang)
    // và đơn đã gửi hỏi giá chưa có hồi âm. Đơn đã chốt không đếm — nó đang
    // nằm ở kho chờ hàng về, không phải việc của Mua hàng nữa.
    this.registerBadge("purchase_order", () =>
      orm.searchCount("dl.purchase.order", [
        ["state", "in", ["draft", "sent"]],
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
