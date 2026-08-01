/** @odoo-module **/
// ============================================================
//  DL Quote Approval Form — FormController cho Yêu cầu phê duyệt báo giá.
//  Đăng ký view js_class="dl_quote_approval_form" (quote_approval_views.xml).
//  Tuỳ biến giống các form khác của hệ thống:
//   1) Dời cụm nút Phê duyệt/Từ chối (statusbar) LÊN hàng breadcrumb.
//   2) Menu ⋮ dùng chung — tự ẩn vì view create/delete=false (activeActions).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

export class DlQuoteApprovalFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }

    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            _t("Yêu cầu phê duyệt")
        );
    }
}

registry.category("views").add("dl_quote_approval_form", {
    ...formView,
    Controller: DlQuoteApprovalFormController,
});
