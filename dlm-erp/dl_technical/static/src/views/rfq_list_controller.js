/** @odoo-module **/
// ============================================================
//  DL RFQ List — đồng bộ giao diện danh sách Yêu cầu báo giá (D1).
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlRfqListController extends DlListBaseController {
    get dlCountNoun() {
        return "yêu cầu báo giá";
    }
}

registry.category("views").add("dl_rfq_list", {
    ...listView,
    Controller: DlRfqListController,
});
