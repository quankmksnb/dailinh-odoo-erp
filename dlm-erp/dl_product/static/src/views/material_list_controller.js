/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlMaterialListController extends DlListBaseController {
    get dlCountNoun() {
        return "vật tư";
    }
}

registry.category("views").add("dl_material_list", {
    ...listView,
    Controller: DlMaterialListController,
});
