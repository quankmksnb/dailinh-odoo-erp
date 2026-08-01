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
        menuXmlIds: ["dl_config.menu_dl_config_uom"],
    },
    {
        key: "company",
        name: "Công ty",
        desc: "Thông tin công ty phát hành",
        icon: "fa-building-o",
        group: "master",
        actionXmlId: "dl_config.action_dl_company",
        menuXmlIds: ["dl_config.menu_dl_config_company"],
    },
    {
        key: "pricing_config",
        name: "Cấu hình Báo giá",
        desc: "Hao hụt, công đoạn, chi phí chung, lợi nhuận, chiết khấu và phê duyệt",
        icon: "fa-calculator",
        group: "system",
        actionXmlId: "dl_config.action_dl_pricing_config",
        menuXmlIds: ["dl_config.menu_dl_config_pricing"],
    },
    {
        key: "user",
        name: "Quản lý người dùng",
        desc: "Tài khoản, vai trò, khóa/mở và người duyệt thay thế",
        icon: "fa-users",
        group: "system",
        actionXmlId: "dl_config.action_dl_user_admin",
        menuXmlIds: ["dl_config.menu_dl_config_user_admin"],
    },
    {
        key: "role_perm",
        name: "Phân quyền",
        desc: "Thiết lập quyền Xem/Thêm/Sửa/Xóa và các thao tác theo vai trò",
        icon: "fa-shield",
        group: "system",
        actionXmlId: "dl_config.action_dl_role_perm",
        menuXmlIds: ["dl_config.menu_dl_config_role_perm"],
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
        this.menuService = useService("menu");
        this._dlmApp = this.menuService
            .getApps()
            .find((app) => app.xmlid === "dl_base.menu_dl_root");
    }

    get sections() {
        return GROUPS.map((g) => ({
            ...g,
            items: CARDS.filter((c) => c.group === g.key && this._resolveCardMenu(c)),
        })).filter((g) => g.items.length);
    }

    _findMenuByXmlId(node, xmlid) {
        if (!node) return null;
        if (node.xmlid === xmlid) return node;
        for (const child of node.childrenTree || []) {
            const found = this._findMenuByXmlId(child, xmlid);
            if (found) return found;
        }
        return null;
    }

    _resolveCardMenu(card) {
        if (!this._dlmApp) return null;
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        for (const xmlid of card.menuXmlIds || []) {
            const menu = this._findMenuByXmlId(tree, xmlid);
            if (menu && this._hasActionableMenu(menu)) return menu;
        }
        return null;
    }

    _hasActionableMenu(menu) {
        if (!menu) return false;
        if (menu.actionID) return true;
        return (menu.childrenTree || []).some((child) => this._hasActionableMenu(child));
    }

    openCard(card) {
        const menu = this._resolveCardMenu(card);
        if (menu) this.menuService.selectMenu(menu);
    }
}

registry.category("actions").add("dl_config.DlConfigHome", DlConfigHome);
