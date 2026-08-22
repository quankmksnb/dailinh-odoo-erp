/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlmRail } from "@dl_base/components/rail/rail";

// Rail: nhóm Cấu hình xổ thành mục con điều hướng thẳng (không có màn hub trung
// chuyển). Card trên Home không cần actionXmlId — DlHome tự mở menu con đầu tiên.
//
// Thứ tự: việc của Admin trước (họ là vai DUY NHẤT thấy cả 4 mục, và land
// thẳng vào Quản lý người dùng — bản trước để nó ở vị trí thứ 3), rồi tới hai
// danh mục dùng chung. Ba vai còn lại chỉ thấy 1–2 mục nên không bị ảnh hưởng:
// Trưởng KD/Kỹ thuật chỉ có "Cấu hình Báo giá", CEO có thêm "Đơn vị tính".
const CONFIG_CHILDREN = [
    {
        key: "user",
        name: "Quản lý người dùng",
        icon: "fa-users",
        actionXmlId: "dl_config.action_dl_user_admin",
        menuXmlIds: ["dl_config.menu_dl_config_user_admin"],
    },
    {
        key: "role_perm",
        name: "Phân quyền",
        icon: "fa-shield",
        actionXmlId: "dl_config.action_dl_role_perm",
        menuXmlIds: ["dl_config.menu_dl_config_role_perm"],
    },
    {
        key: "pricing_config",
        name: "Cấu hình Báo giá",
        icon: "fa-calculator",
        actionXmlId: "dl_config.action_dl_pricing_config",
        menuXmlIds: ["dl_config.menu_dl_config_pricing"],
    },
    {
        key: "uom",
        name: "Đơn vị tính",
        icon: "fa-balance-scale",
        actionXmlId: "dl_config.action_dl_uom",
        menuXmlIds: ["dl_config.menu_dl_config_uom"],
    },
];

function wireConfigRail(items) {
    const item = items && items.find((i) => i.key === "config");
    if (item) {
        item.children = CONFIG_CHILDREN;
    }
}

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireConfigRail(this.railItems);
    },
});
