/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlSemiListController extends DlListBaseController {
    get dlCountNoun() {
        return "bán thành phẩm";
    }
}

registry.category("views").add("dl_semi_list", {
    ...listView,
    Controller: DlSemiListController,
});
