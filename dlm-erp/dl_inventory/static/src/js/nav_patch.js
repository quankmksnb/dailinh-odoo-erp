/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DlmRail } from "@dl_base/components/rail/rail";
import { wireRailChildren } from "@dl_base/js/rail_children";

// ⚠️ ĐÂY KHÔNG PHẢI "bản nav_patch thứ 5". Hàm dùng chung `wireRailChildren` đã
// được rút về dl_base/static/src/js/rail_children.js — file này chỉ khai DỮ LIỆU
// mục con của nhóm Kho rồi gắn vào rail.

// Xếp theo TẦN SUẤT dùng của thủ kho, không theo thứ tự luồng nghiệp vụ.
// Kiểm kê CỐ Ý không lên rail — nó là nút trên màn Tồn kho (§11.11).
//
// 🔴 MẢNG NÀY LÀ NGUỒN DUY NHẤT của rail Kho — rail KHÔNG tự đọc cây menu.
// Thêm `<menuitem>` vào menus.xml mà quên khai ở đây thì menu vẫn tồn tại, vẫn
// vào được bằng URL, nhưng **không xuất hiện trên rail** và không có lỗi nào
// nổ. Đã vấp thật với "Điều phối đơn hàng" (K16, 2026-08-14).
//
// ♻️ "Trả hàng NCC" ĐÃ RỜI khỏi đây (2026-08-14): rail Mua hàng nay tồn tại
// (`dl_purchase/static/src/js/nav_patch.js`), đúng chỗ §11.11 xếp nó từ đầu.
const INVENTORY_CHILDREN = [
  {
    // RS-10 — mục đầu tiên là VIỆC ĐANG CHỜ, không phải danh mục. Badge ở đây
    // là thứ duy nhất trên rail trả lời "hôm nay còn bao nhiêu phiếu phải làm".
    key: "picking_todo",
    name: "Hàng đợi",
    icon: "fa-tasks",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_todo"],
  },
  {
    // K16 — việc đầu ngày của thủ kho: đơn nào mới chốt, có làm được không.
    // Đứng ngay sau Hàng đợi và TRƯỚC Tồn kho: xem tồn là tra cứu, còn đây là
    // việc phải quyết.
    key: "dispatch",
    name: "Điều phối đơn hàng",
    icon: "fa-sitemap",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_dispatch_queue"],
  },
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
    // K13 — đầu ra của nhánh gia công. Đứng ngay sau Kiểm hàng vì nó là bước
    // "hàng vào kho" thứ hai, song song với nhận hàng NCC: một đường hàng mua
    // về, một đường hàng mình làm ra.
    key: "fg_receipt",
    name: "Nhập kho từ xưởng",
    icon: "fa-industry",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_picking_fg_receipt"],
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
    key: "scrap",
    name: "Phế liệu",
    icon: "fa-recycle",
    preferMenu: true,
    menuXmlIds: ["dl_inventory.menu_dl_scrap"],
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

    // Rail chỉ gọi fetcher của mục user THẤY được (_refreshBadges lọc theo
    // visibleChildren), nên vai trò không có mục đó không phát sinh truy vấn.
    const orm = useService("orm");

    // K16 — badge Điều phối: số đơn đã chốt mà kho CHƯA nhận việc. Đây là con
    // số trả lời "hôm nay có đơn mới nào không" — trước bản này thủ kho chỉ
    // biết bằng cách chờ Sales gọi xuống.
    this.registerBadge("dispatch", () =>
      orm.searchCount("dl.sale.order", [
        ["state", "=", "confirmed"],
        ["dlm_dispatch_state", "=", "to_dispatch"],
      ]),
    );

    // RS-10 — badge hàng đợi: TỔNG việc đang chờ thủ kho, khớp domain của
    // action_dl_picking_todo. Đây là con số thủ kho nhìn đầu tiên mỗi sáng.
    this.registerBadge("picking_todo", () =>
      orm.searchCount("stock.picking", [
        ["state", "=", "assigned"],
        ["picking_type_id.sequence_code", "in", ["NH", "KC", "CK", "GH"]],
      ]),
    );

    // §11.11 — badge việc còn treo của thủ kho: phiếu chờ kiểm và phiếu cần
    // giao. `assigned` = đã giữ chỗ đủ, sẵn sàng thao tác (đúng bộ lọc hàng
    // đợi). Rail chỉ gọi fetcher của mục user THẤY được nên vai trò khác không
    // phát sinh truy vấn thừa.
    this.registerBadge("qc", () =>
      orm.searchCount("stock.picking", [
        ["picking_type_id.sequence_code", "=", "KC"],
        ["state", "=", "assigned"],
      ]),
    );
    this.registerBadge("delivery", () =>
      orm.searchCount("stock.picking", [
        ["picking_type_id.sequence_code", "=", "GH"],
        ["state", "=", "assigned"],
      ]),
    );
  },
});
