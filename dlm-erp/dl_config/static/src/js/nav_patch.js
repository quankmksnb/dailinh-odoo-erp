/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DlHome } from "@dl_base/components/home/home";
import { DlmRail } from "@dl_base/components/rail/rail";

const CONFIG_ACTION = "dl_config.action_dl_config_home";

// Rail: dẹp hub Cấu hình thành mục con điều hướng thẳng (bỏ màn hub trung chuyển).
const CONFIG_CHILDREN = [
    {
        key: "uom",
        name: "Đơn vị tính",
        icon: "fa-balance-scale",
        actionXmlId: "dl_config.action_dl_uom",
        menuXmlIds: ["dl_config.menu_dl_config_uom"],
    },
    {
        key: "company",
        name: "Công ty",
        icon: "fa-building-o",
        actionXmlId: "dl_config.action_dl_company",
        menuXmlIds: ["dl_config.menu_dl_config_company"],
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

// Home (fallback): giữ card mở hub như cũ.
function wireConfigHome(cards) {
    const item = cards && cards.find((i) => i.key === "config");
    if (item && !item.actionXmlId) {
        item.actionXmlId = CONFIG_ACTION;
    }
}

function wireConfigRail(items) {
    const item = items && items.find((i) => i.key === "config");
    if (item) {
        item.children = CONFIG_CHILDREN;
    }
}

patch(DlHome.prototype, {
    setup() {
        super.setup(...arguments);
        wireConfigHome(this.cards);
    },
});

patch(DlmRail.prototype, {
    setup() {
        super.setup(...arguments);
        wireConfigRail(this.railItems);
    },
});
