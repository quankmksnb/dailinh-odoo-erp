/** @odoo-module **/
// ============================================================
//  DL Material Form — đồng bộ chrome form Vật tư với các màn khác.
//  Menu ⋮ + breadcrumb "Thêm vật tư" cho bản ghi mới.
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "@dl_sale/js/actions_menu";

export class DlMaterialFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }

    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            (this.model.root.isNew && _t("Thêm vật tư")) ||
            ""
        );
    }
}

registry.category("views").add("dl_material_form", {
    ...formView,
    Controller: DlMaterialFormController,
});
