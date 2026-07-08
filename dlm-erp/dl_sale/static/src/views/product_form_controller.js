/** @odoo-module **/
// ============================================================
//  DL Product Form — FormController tuỳ biến cho Sản phẩm (S05).
//  Đăng ký view js_class="dl_product_form".
//  Menu ⋮ Nhân bản/Xoá + breadcrumb "Thêm sản phẩm" cho bản ghi mới.
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "../js/actions_menu";

export class DlProductFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }

    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            (this.model.root.isNew && _t("Thêm sản phẩm")) ||
            ""
        );
    }
}

registry.category("views").add("dl_product_form", {
    ...formView,
    Controller: DlProductFormController,
});
