/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlmRail } from "@dl_base/components/rail/rail";

// Rail: nhóm Cấu hình xổ thành mục con điều hướng thẳng (không có màn hub trung
// chuyển). Card trên Home không cần actionXmlId — DlHome tự mở menu con đầu tiên.
const CONFIG_CHILDREN = [
    {
        key: "uom",
        name: "Đơn vị tính",
        icon: "fa-balance-scale",
        actionXmlId: "dl_config.action_dl_uom",
        menuXmlIds: ["dl_config.menu_dl_config_uom"],
    },
    {
        key: "pricing_config",
        name: "Cấu hình Báo giá",
        icon: "fa-calculator",
        actionXmlId: "dl_config.action_dl_pricing_config",
        menuXmlIds: ["dl_config.menu_dl_config_pricing"],
    },
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
