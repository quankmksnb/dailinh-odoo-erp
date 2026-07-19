/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const CARDS = [
    {
        key: "uom",
        name: "Đơn vị tính",
        desc: "Đơn vị và nhóm quy đổi",
        icon: "fa-balance-scale",
        group: "master",
        actionXmlId: "dl_config.action_dl_uom",
    },
    {
        key: "company",
        name: "Công ty",
        desc: "Thông tin công ty phát hành",
        icon: "fa-building-o",
        group: "master",
        actionXmlId: "dl_config.action_dl_company",
    },
    {
        key: "pricing_config",
        name: "Cấu hình Báo giá",
        desc: "Hao hụt, công đoạn, chi phí chung, lợi nhuận, chiết khấu và phê duyệt",
        icon: "fa-calculator",
        group: "system",
        actionXmlId: "dl_config.action_dl_pricing_config",
    },
    {
        key: "user",
        name: "Quản lý User",
        desc: "Tài khoản, gán vai trò, khóa/mở, Backup Approver",
        icon: "fa-users",
        group: "system",
        actionXmlId: "dl_config.action_dl_user_admin",
    },
    {
        key: "role_perm",
        name: "Phân quyền",
        desc: "Định nghĩa vai trò, tick quyền Xem/Thêm/Sửa/Xóa & thao tác đặc biệt (RBAC)",
        icon: "fa-shield",
        group: "system",
        actionXmlId: "dl_config.action_dl_role_perm",
    },
];

const GROUPS = [
    { key: "master", label: "Dữ liệu danh mục" },
    { key: "system", label: "Hệ thống & phân quyền" },
];

export class DlConfigHome extends Component {
    static template = "dl_config.DlConfigHome";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.cards = CARDS;
    }

    get sections() {
        return GROUPS.map((g) => ({
            ...g,
            items: CARDS.filter((c) => c.group === g.key),
        })).filter((g) => g.items.length);
    }

    openCard(actionXmlId) {
        if (!actionXmlId) {
            return;
        }
        this.actionService.doAction(actionXmlId);
    }
}

registry.category("actions").add("dl_config.DlConfigHome", DlConfigHome);
