/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { sidebarState, toggleSidebar } from "@dl_base/js/sidebar_state";
import { getModules, firstActionable, DLM_ROOT_XMLID } from "@dl_base/js/modules_nav";

<<<<<<< Updated upstream
const DLM_APP_XMLID = "dl_base.menu_dl_root";

const RAIL_ITEMS = [
    { key: "home", name: "Trang chủ", icon: "fa-home", actionXmlId: "dl_base.action_dl_home" },
    { key: "customer", name: "Khách hàng", icon: "fa-users", actionXmlId: "dl_sale.action_dl_customer" },
    { key: "supplier", name: "Nhà cung cấp", icon: "fa-truck", actionXmlId: "dl_sale.action_dl_supplier" },
    { key: "quotation", name: "Báo giá", icon: "fa-file-text-o", actionXmlId: "dl_sale.action_dl_quotation" },
    { key: "product", name: "Sản phẩm", icon: "fa-cube", actionXmlId: "dl_sale.action_dl_product" },
    { key: "technical", name: "Kỹ thuật", icon: "fa-cogs", actionXmlId: null },
    { key: "material", name: "Vật tư", icon: "fa-cubes", actionXmlId: null },
    { key: "report", name: "Báo cáo", icon: "fa-bar-chart", actionXmlId: null },
    { key: "config", name: "Cấu hình", icon: "fa-sliders", actionXmlId: null },
];
=======
const HOME_ACTION = "dl_base.action_dl_home";
>>>>>>> Stashed changes

export class DlmRail extends Component {
    static template = "dl_base.DlmRail";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
<<<<<<< Updated upstream
        this.railItems = RAIL_ITEMS;
        this.state = useState({ visible: this._inDlmApp() });
=======
        // Danh mục rail = Trang chủ + các module cấp 1 user được phép (RBAC).
        this.railItems = this._buildItems();
        this.state = useState({ visible: this._inDlmApp(), expanded: {} });
>>>>>>> Stashed changes
        this.sidebar = useState(sidebarState);

        // "MENUS:APP-CHANGED" chỉ phát khi ĐỔI app (selectMenu / app switcher);
        // điều hướng nội bộ DLM bằng doAction không đổi app nên rail vẫn hiện.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            this.state.visible = this._inDlmApp();
        });

        // Đồng bộ class trên <body> để CSS ẩn navbar Odoo + chừa chỗ cho rail.
        useEffect(
            (visible, collapsed) => {
                document.body.classList.toggle("dlm-rail-active", visible);
                document.body.classList.toggle("dlm-rail-collapsed", visible && collapsed);
                return () => {
                    document.body.classList.remove("dlm-rail-active");
                    document.body.classList.remove("dlm-rail-collapsed");
                };
            },
            () => [this.state.visible, this.sidebar.collapsed]
        );
    }

    // Item = { key, name, icon, action, node, children }
    //  - action  : mở thẳng launcher (Trang chủ / Cấu hình / Kỹ thuật / Báo giá)
    //  - children : module chưa có launcher (Sản phẩm / Vật tư) → xổ menu con
    //               để không mất lối vào các màn con.
    _buildItems() {
        const items = [
            { key: "home", name: "Trang chủ", icon: "fa-home", action: HOME_ACTION, node: null, children: null },
        ];
        for (const mod of getModules(this.menuService)) {
            const children = mod.expand
                ? (mod.node.childrenTree || []).map((leaf) => ({
                      key: leaf.xmlid || `menu_${leaf.id}`,
                      name: leaf.name,
                      target: firstActionable(leaf),
                  }))
                : null;
            items.push({
                key: mod.key,
                name: mod.name,
                icon: mod.icon,
                action: mod.action,
                target: mod.target,
                children: children && children.length ? children : null,
            });
        }
        return items;
    }

    toggleSidebar() {
        toggleSidebar();
    }

    _inDlmApp() {
        const app = this.menuService.getCurrentApp();
        return !!app && app.xmlid === DLM_ROOT_XMLID;
    }

<<<<<<< Updated upstream
    openModule(actionXmlId) {
        if (!actionXmlId) return;
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
=======
    toggleSubmenu(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    openItem(item) {
        if (item.action) {
            this.actionService.doAction(item.action, { clearBreadcrumbs: true });
        } else if (item.children) {
            this.toggleSubmenu(item.key);
        } else if (item.target) {
            this.menuService.selectMenu(item.target);
        }
    }

    openChild(child) {
        if (child.target) {
            this.menuService.selectMenu(child.target);
        }
>>>>>>> Stashed changes
    }
}

registry.category("main_components").add("dlm_rail.DlmRail", { Component: DlmRail });
