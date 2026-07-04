/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "@dl_sale/views/dl_list_controller";

// Danh sách Vai trò (RBAC) — dùng chrome DLM (footer đếm, ô search bo tròn,
// menu ⋮ Nhập/Xuất) từ lớp cơ sở. Không có thanh chip lọc trạng thái nên
// override _renderChipbar rỗng (giống màn Công ty).
export class DlRoleListController extends DlListBaseController {
    get dlCountNoun() {
        return "vai trò";
    }

    _renderChipbar() {}
}

registry.category("views").add("dl_role_list", {
    ...listView,
    Controller: DlRoleListController,
});
