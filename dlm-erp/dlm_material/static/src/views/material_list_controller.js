/** @odoo-module **/
// ============================================================
//  DL Material List — đồng bộ giao diện danh sách với các màn khác.
//  Tái dùng DlListBaseController của dl_sale (dlm_material depends dl_sale):
//  control panel styled, nút "+ Thêm", ẩn cog/New, footer, menu ⋮ Nhập/Xuất.
//   • dl_material_list       → Danh mục Vật tư (S06)
//   • dl_material_price_list → Bảng giá Vật tư (lịch sử giá đứng riêng)
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

export class DlMaterialListController extends DlListBaseController {
    get dlCountNoun() {
        return "vật tư";
    }
}

export class DlMaterialPriceListController extends DlListBaseController {
    get dlCountNoun() {
        return "dòng giá";
    }
}

registry.category("views").add("dl_material_list", {
    ...listView,
    Controller: DlMaterialListController,
});

registry.category("views").add("dl_material_price_list", {
    ...listView,
    Controller: DlMaterialPriceListController,
});
