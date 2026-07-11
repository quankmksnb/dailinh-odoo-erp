/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "@dl_base/js/actions_menu";

export class DlUomFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }
}

registry.category("views").add("dl_uom_form", {
    ...formView,
    Controller: DlUomFormController,
});
