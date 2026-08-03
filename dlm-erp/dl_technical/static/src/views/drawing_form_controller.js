/** @odoo-module **/
// ============================================================
//  DL Drawing Form — đồng bộ chrome form Bản vẽ kỹ thuật (B1).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

export class DlDrawingFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }

    displayName() {
        if (this.model.root.isNew) {
            return _t("Thêm bản vẽ");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }
}

registry.category("views").add("dl_drawing_form", {
    ...formView,
    Controller: DlDrawingFormController,
});
