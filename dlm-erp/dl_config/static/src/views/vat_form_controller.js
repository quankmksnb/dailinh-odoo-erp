/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "@dl_sale/js/actions_menu";

export class DlVatFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }
}

registry.category("views").add("dl_vat_form", {
    ...formView,
    Controller: DlVatFormController,
});
