/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

// ─────────────────────────────────────────────────────────────────────────────
// K8 — Định tuyến "Hàng đợi phiếu" (docs/Thiet_ke_phan_he_kho.md §11.11)
//
// Hàng đợi là MỘT list gộp mọi loại phiếu đang chờ xử lý. Nhưng mỗi loại có form
// riêng với nhãn cột trái ngược nhau: form Nhận hàng đếm "Dự kiến / Thực nhận",
// form Kiểm hàng ghi "NCC giao / Đạt / Loại". Mở phiếu kiểm bằng form nhận là
// mời thủ kho ghi hàng LỖI vào ô hàng THIẾU — đúng cái nhầm §6 dựng lên để
// tránh. Nên: click một dòng ⇒ doAction sang ĐÚNG action chuyên biệt của loại
// đó, mở thẳng form của nó cho bản ghi vừa chọn.
//
// Không phải "bản nav_patch thứ 5": đây là một js_class view riêng, chỉ gắn cho
// action Hàng đợi qua `js_class="dl_picking_todo_list"`.
// ─────────────────────────────────────────────────────────────────────────────

const DL_TODO_ROUTES = {
  receipt: "dl_inventory.action_dl_picking_receipt",
  qc: "dl_inventory.action_dl_picking_qc",
  transfer: "dl_inventory.action_dl_picking_transfer",
  delivery: "dl_inventory.action_dl_picking_delivery",
};

export class DlPickingTodoController extends ListController {
  /**
   * Thay vì mở bản ghi bằng form của chính action Hàng đợi (không có form),
   * điều hướng sang action chuyên biệt của loại phiếu và mở thẳng form của nó.
   */
  async openRecord(record) {
    const action = DL_TODO_ROUTES[record.data.dlm_picking_kind];
    if (action) {
      return this.actionService.doAction(action, {
        viewType: "form",
        props: { resId: record.resId },
      });
    }
    // Loại không định tuyến được (dữ liệu lạ) ⇒ giữ hành vi mặc định.
    return super.openRecord(record);
  }
}

registry.category("views").add("dl_picking_todo_list", {
  ...listView,
  Controller: DlPickingTodoController,
});
