/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlSupplierinfoListController extends DlListBaseController {
    get dlCountNoun() {
        return "bảng giá nhà cung cấp";
    }

    get dlFilterDropdowns() {
        return [
            {
                key: "approval",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "draft", label: "Chờ duyệt" },
                    { name: "approved", label: "Đã duyệt" },
                    { name: "applied", label: "Đang áp dụng" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_supplierinfo_list", {
    ...listView,
    Controller: DlSupplierinfoListController,
});
