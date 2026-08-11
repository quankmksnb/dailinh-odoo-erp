/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";
import { wireRailChildren } from "@dl_base/js/rail_children";

// ⚠️ ĐÂY KHÔNG PHẢI "bản nav_patch thứ 5". Hàm dùng chung `wireRailChildren` đã
// được rút về dl_base/static/src/js/rail_children.js — file này chỉ khai DỮ LIỆU
// mục con của nhóm Kho rồi gắn vào rail.

// Xếp theo TẦN SUẤT dùng của thủ kho, không theo thứ tự luồng nghiệp vụ.
// K7–K8 sẽ chèn thêm: Phế liệu. Kiểm kê CỐ Ý không lên rail — nó là nút trên
// màn Tồn kho (§11.11).
//
// "Trả hàng NCC" có mặt ở đây dù §11.11 xếp nó về rail của Mua hàng: rail đó
// thuộc B3, chưa tồn tại. Mỗi mục con đã được lọc theo RBAC của menu đích nên
// thủ kho KHÔNG thấy mục này — chỉ Mua hàng / Admin / CEO thấy. Chuyển sang
// rail Mua hàng khi B3 dựng xong.
const INVENTORY_CHILDREN = [
  {
    key: "stock_quant",
    name: "Tồn kho",
    icon: "fa-cubes",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_stock_quant"],
  },
  {
    key: "receipt",
    name: "Nhận hàng",
    icon: "fa-download",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_receipt"],
  },
  {
    key: "qc",
    name: "Kiểm hàng",
    icon: "fa-check-square-o",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_qc"],
  },
  {
    key: "transfer",
    name: "Chuyển kho",
    icon: "fa-exchange",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_transfer"],
  },
  {
    key: "delivery",
    name: "Giao hàng",
    icon: "fa-upload",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_delivery"],
  },
  {
    key: "vendor_return",
    name: "Trả hàng NCC",
    icon: "fa-reply",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_vendor_return"],
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

    // Badge "Trả hàng NCC": phiếu trả sinh ra ở trạng thái NHÁP và nằm im cho
    // tới khi Mua hàng thoả thuận xong với NCC — không đếm thì nó là việc tồn
    // vô hình. Rail chỉ gọi fetcher của mục user THẤY được (_refreshBadges lọc
    // theo visibleChildren), nên thủ kho không phát sinh truy vấn này.
    const orm = useService("orm");
    this.registerBadge("vendor_return", () =>
      orm.searchCount("stock.picking", [
        ["picking_type_id.sequence_code", "=", "TR"],
        ["state", "=", "draft"],
      ]),
    );
  },
});
