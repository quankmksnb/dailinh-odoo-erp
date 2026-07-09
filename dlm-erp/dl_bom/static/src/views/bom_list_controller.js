/** @odoo-module **/
// ============================================================
//  DL BOM List — đồng bộ giao diện danh sách với các màn khác (S08).
//  Tái dùng DlListBaseController của dl_sale (dl_bom depends dl_sale).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

export class DlBomListController extends DlListBaseController {
    get dlCountNoun() {
        return "BOM";
    }
}

registry.category("views").add("dl_bom_list", {
    ...listView,
    Controller: DlBomListController,
});
