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
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";
import { setupFormActionsMenu } from "../js/actions_menu";

export class DlQuotationFormController extends FormController {
    setup() {
        super.setup();
        // Chuyển nút hành động ở statusbar sang ngay sau breadcrumb.
        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            const buttons = root.querySelector(
                ".o_form_statusbar .o_statusbar_buttons"
            );
            const target =
                root.querySelector(".o_control_panel_breadcrumbs .o_breadcrumb") ||
                root.querySelector(".o_control_panel_breadcrumbs");
            if (buttons && target && buttons.parentElement !== target) {
                buttons.classList.add("dl-cp-actions");
                target.appendChild(buttons);
            }
        });
        setupFormActionsMenu(this);
    }
}

registry.category("views").add("dl_quotation_form", {
    ...formView,
    Controller: DlQuotationFormController,
});
