/** @odoo-module **/
// ============================================================
//  DL BOM List — đồng bộ giao diện danh sách với các màn khác (S08).
//  Tái dùng DlListBaseController của dl_base (hạ tầng dùng chung).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlBomListController extends DlListBaseController {
    get dlCountNoun() {
        return "BOM";
    }
}

registry.category("views").add("dl_bom_list", {
    ...listView,
    Controller: DlBomListController,
});
