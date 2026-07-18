/** @odoo-module **/
// ============================================================
//  DL RFQ Form — đồng bộ chrome form Yêu cầu báo giá (D1).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

export class DlRfqFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }

    displayName() {
        if (this.model.root.isNew) {
            return _t("Thêm yêu cầu báo giá");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }
}

registry.category("views").add("dl_rfq_form", {
    ...formView,
    Controller: DlRfqFormController,
});
