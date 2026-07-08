/** @odoo-module **/
// ============================================================
//  DL Product List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_product_list" (dùng ở product_views.xml).
//  Nhóm sản phẩm là danh mục ĐỘNG (m2o) nên không dùng chip cố định —
//  lọc theo nhóm qua "Nhóm theo" trong search. Vẫn dùng control panel,
//  footer, menu ⋮ Nhập/Xuất như các danh sách khác.
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "./dl_list_controller";

export class DlProductListController extends DlListBaseController {
    get dlCountNoun() {
        return "sản phẩm";
    }
}

registry.category("views").add("dl_product_list", {
    ...listView,
    Controller: DlProductListController,
});
