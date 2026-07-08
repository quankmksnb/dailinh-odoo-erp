/** @odoo-module **/
// ============================================================
//  DL Customer Form — FormController tuỳ biến cho Khách hàng.
//  Đăng ký view js_class="dl_customer_form" (dùng ở customer_views.xml).
//  Tuỳ biến: menu ⋮ Nhân bản/Xoá góc trên phải (dùng chung
//  setupFormActionsMenu — giống form Báo giá).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "../js/actions_menu";

export class DlCustomerFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }

    // Breadcrumb bản ghi mới: đổi "New" mặc định → "Thêm khách hàng".
    // Giữ nguyên hiển thị tên khi đã có (record cũ hoặc vừa nhập display_name).
    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            (this.model.root.isNew && _t("Thêm khách hàng")) ||
            ""
        );
    }
}

registry.category("views").add("dl_customer_form", {
    ...formView,
    Controller: DlCustomerFormController,
});
