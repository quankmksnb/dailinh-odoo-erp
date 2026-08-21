/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

export class DlProductFormController extends FormController {
  setup() {
    super.setup();
    setupStatusbarButtons(this);
    setupFormActionsMenu(this);
    this.notification = useService("notification");
  }

  // Tiêu đề lúc tạo mới nói đúng thứ đang tạo: màn Vật tư mở form với
  // default_product_kind = material/material_processed → "Thêm vật tư".
  displayName() {
    if (this.model.root.isNew) {
      const kind = this.model.root.data.product_kind;
      const isMaterial = kind === "material" || kind === "material_processed";
      return isMaterial ? _t("Thêm vật tư") : _t("Thêm sản phẩm");
    }
    return this.model.root.data.display_name?.split("\n")[0] || "";
  }

  // Chặn INLINE (tô đỏ ô Giá bán + toast, KHÔNG modal — cùng cơ chế form RFQ):
  // SP thương mại phải có Giá bán CAO HƠN Giá vốn tham chiếu — ở MỌI trạng thái
  // vòng đời (Nháp lẫn Đã duyệt). Trước đây chỉ chặn khi còn Nháp nên sau khi
  // duyệt vẫn hạ được giá bán xuống dưới giá vốn (vô lý) → nay chặn cả khi active.
  // Bán lỗ (nếu thực sự cần) xử lý ở duyệt báo giá, không hạ giá niêm yết.
  // ⚠️ Phải khớp CHÍNH XÁC với ràng buộc server _check_sale_price_above_cost
  // (bán NGANG giá vốn cũng chặn) — lệch một dấu là báo lỗi hai kiểu khác nhau.
  async save(params = {}) {
    const record = this.model.root;
    const d = record.data;
    const belowCost =
      d.product_kind === "trading" &&
      d.list_price > 0 &&
      d.standard_price > 0 &&
      d.list_price <= d.standard_price;
    if (belowCost) {
      await record.setInvalidField("list_price");
      this.notification.add(
        _t(
          "Giá bán (%s) phải cao hơn Giá vốn tham chiếu (%s) — bán ngang giá vốn cũng không hợp lệ. Nếu thực sự cần bán lỗ, xử lý ở quy trình duyệt báo giá (CEO/Trưởng phòng KD), không hạ giá niêm yết sản phẩm.",
          d.list_price.toLocaleString("vi-VN"),
          d.standard_price.toLocaleString("vi-VN"),
        ),
        { type: "danger", title: _t("Giá bán không hợp lệ") },
      );
      return false;
    }
    record.resetFieldValidity("list_price");
    return super.save(params);
  }
}

registry.category("views").add("dl_product_form", {
  ...formView,
  Controller: DlProductFormController,
});
