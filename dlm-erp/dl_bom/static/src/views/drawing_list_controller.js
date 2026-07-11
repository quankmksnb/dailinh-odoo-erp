/** @odoo-module **/
// ============================================================
//  DL Drawing List — đồng bộ giao diện danh sách Bản vẽ kỹ thuật (B1).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlDrawingListController extends DlListBaseController {
    get dlCountNoun() {
        return "bản vẽ";
    }
}

registry.category("views").add("dl_drawing_list", {
    ...listView,
    Controller: DlDrawingListController,
});
