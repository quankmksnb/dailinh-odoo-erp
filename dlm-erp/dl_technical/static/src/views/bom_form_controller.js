/** @odoo-module **/
// ============================================================
//  DL BOM Form — đồng bộ chrome form BOM với các màn khác (S08).
//  Menu ⋮ + breadcrumb "Thêm BOM" cho bản ghi mới.
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu } from "@dl_base/js/actions_menu";

export class DlBomFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }

    displayName() {
        return (
            this.model.root.data.display_name?.split("\n")[0] ||
            (this.model.root.isNew && _t("Thêm BOM")) ||
            ""
        );
    }
}

registry.category("views").add("dl_bom_form", {
    ...formView,
    Controller: DlBomFormController,
});
