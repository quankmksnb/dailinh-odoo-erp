/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlmRail } from "@dl_base/components/rail/rail";
import { wireRailChildren } from "@dl_base/js/rail_children";

// ⚠️ ĐÂY KHÔNG PHẢI "bản nav_patch thứ 5". Hàm dùng chung `wireRailChildren` đã
// được rút về dl_base/static/src/js/rail_children.js — file này chỉ khai DỮ LIỆU
// mục con của nhóm Kho rồi gắn vào rail.

// Xếp theo TẦN SUẤT dùng của thủ kho, không theo thứ tự luồng nghiệp vụ.
// K5–K8 sẽ chèn thêm: Nhận hàng, Kiểm hàng (có badge), Chuyển kho, Giao hàng,
// Phế liệu. Trả hàng NCC và Kiểm kê CỐ Ý không lên rail (xem §11.11 thiết kế).
const INVENTORY_CHILDREN = [
  {
    key: "stock_quant",
    name: "Tồn kho",
    icon: "fa-cubes",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_stock_quant"],
  },
  {
    key: "stock_lot",
    name: "Lô hàng",
    icon: "fa-barcode",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_stock_lot"],
  },
];

patch(DlmRail.prototype, {
  setup() {
    super.setup(...arguments);
    wireRailChildren(this.railItems, "inventory", INVENTORY_CHILDREN);
  },
});
