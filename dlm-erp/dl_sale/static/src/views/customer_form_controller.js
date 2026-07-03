/** @odoo-module **/
// ============================================================
//  DL Customer Form — FormController tuỳ biến cho Khách hàng.
//  Đăng ký view js_class="dl_customer_form" (dùng ở customer_views.xml).
//  Tuỳ biến: menu ⋮ Nhân bản/Xoá góc trên phải (dùng chung
//  setupFormActionsMenu — giống form Báo giá).
// ============================================================

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "../js/actions_menu";

export class DlCustomerFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }
}

registry.category("views").add("dl_customer_form", {
    ...formView,
    Controller: DlCustomerFormController,
});
