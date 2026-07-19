/** @odoo-module **/
// ============================================================
//  DL Quotation Form — FormController tuỳ biến cho Báo giá.
//  Đăng ký view js_class="dl_quotation_form" (dùng ở quotation_views.xml).
//  Tuỳ biến:
//   1) Đưa cụm nút Duyệt/Từ chối/Về nháp (statusbar) LÊN hàng breadcrumb
//      cho gọn như Figma.
//   2) Menu ⋮ Nhân bản/Xoá góc trên phải (dùng chung setupFormActionsMenu).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

export class DlQuotationFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }

    displayName() {
        if (this.model.root.isNew) {
            return _t("Tạo báo giá");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }
}

registry.category("views").add("dl_quotation_form", {
    ...formView,
    Controller: DlQuotationFormController,
});
