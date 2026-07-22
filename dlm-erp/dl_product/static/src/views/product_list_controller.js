/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_base/views/dl_list_controller";

export class DlProductListController extends DlListBaseController {
    get dlCountNoun() {
        return "sản phẩm";
    }

    get dlFilterDropdowns() {
        return [
            {
                // Đủ 4 loại — base controller tự lược theo filter có trong
                // search view từng màn (Sản phẩm / Vật tư / Bảng giá)
                key: "kind",
                label: "Tất cả loại SP",
                filters: [
                    { name: "f_manufactured", label: "Gia công" },
                    { name: "f_trading", label: "Thương mại" },
                    { name: "f_material", label: "Vật tư" },
                    { name: "f_material_processed", label: "Bán thành phẩm" },
                ],
            },
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "active", label: "Đang dùng" },
                    { name: "inactive", label: "Ngừng" },
                ],
            },
        ];
    }
}

registry.category("views").add("dl_product_list", {
    ...listView,
    Controller: DlProductListController,
});
