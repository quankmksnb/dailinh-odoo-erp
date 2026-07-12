/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlCategoryListController extends DlListBaseController {
    get dlCountNoun() {
        return "nhóm";
    }
}

registry.category("views").add("dl_category_list", {
    ...listView,
    Controller: DlCategoryListController,
});
