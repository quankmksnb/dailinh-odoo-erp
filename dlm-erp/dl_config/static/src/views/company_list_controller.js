/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

export class DlCompanyListController extends DlListBaseController {
    get dlCountNoun() {
        return "công ty";
    }

    _renderChipbar() {}
}

registry.category("views").add("dl_company_list", {
    ...listView,
    Controller: DlCompanyListController,
});
