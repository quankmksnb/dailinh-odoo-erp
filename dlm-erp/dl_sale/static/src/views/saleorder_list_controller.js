/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlSaleOrderListController extends DlListBaseController {
    get dlCountNoun() {
        return "đơn bán hàng";
    }

    get dlFilterDropdowns() {
        return [
            {
                key: "state",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "draft", label: "Nháp" },
                    { name: "confirmed", label: "Đã xác nhận" },
                    { name: "done", label: "Hoàn tất" },
                    { name: "not_cancelled", label: "Chưa hủy" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_saleorder_list", {
    ...listView,
    Controller: DlSaleOrderListController,
});
