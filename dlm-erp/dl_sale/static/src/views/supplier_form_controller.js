/** @odoo-module **/
// ============================================================
//  DL Supplier Form — FormController tuỳ biến cho NCC / Thầu phụ.
//  Đăng ký view js_class="dl_supplier_form" (dùng ở supplier_views.xml).
//  Tuỳ biến: menu ⋮ Nhân bản/Xoá + breadcrumb "Thêm nhà cung cấp"
//  cho bản ghi mới (giống form Khách hàng).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "../js/actions_menu";

export class DlSupplierFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }

    // Breadcrumb bản ghi mới: "New" → "Thêm nhà cung cấp".
    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            (this.model.root.isNew && _t("Thêm nhà cung cấp")) ||
            ""
        );
    }
}

registry.category("views").add("dl_supplier_form", {
    ...formView,
    Controller: DlSupplierFormController,
});
