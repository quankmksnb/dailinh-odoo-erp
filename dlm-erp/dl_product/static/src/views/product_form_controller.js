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

  displayName() {
    if (this.model.root.isNew) {
      return _t("Thêm sản phẩm");
    }
    return this.model.root.data.display_name?.split("\n")[0] || "";
  }

  // Chặn INLINE (tô đỏ ô Giá bán + toast, KHÔNG modal — cùng cơ chế form RFQ):
  // SP thương mại còn Nháp KHÔNG được lưu Giá bán < Giá vốn tham chiếu. Trước
  // đây chỉ cảnh báo mềm ở banner nhưng vẫn cho lưu → nay chặn hẳn ở bước lưu.
  // Bán lỗ (nếu thực sự cần) xử lý ở duyệt báo giá, không hạ giá niêm yết.
  async save(params = {}) {
    const record = this.model.root;
    const d = record.data;
    const belowCost =
      d.product_kind === "trading" &&
      d.dlm_lifecycle_state === "draft" &&
      d.list_price > 0 &&
      d.standard_price > 0 &&
      d.list_price < d.standard_price;
    if (belowCost) {
      await record.setInvalidField("list_price");
      this.notification.add(
        _t(
          "Giá bán (%s) không được thấp hơn Giá vốn tham chiếu (%s). Nếu thực sự cần bán lỗ, xử lý ở quy trình duyệt báo giá (CEO/Trưởng KD), không hạ giá niêm yết sản phẩm.",
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
