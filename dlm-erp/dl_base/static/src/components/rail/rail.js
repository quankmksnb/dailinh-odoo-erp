/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { ErrorHandler } from "@web/core/utils/components";
import { sidebarState, toggleSidebar, setActiveKey } from "@dl_base/js/sidebar_state";

const DLM_APP_XMLID = "dl_base.menu_dl_root";
const systrayRegistry = registry.category("systray");

const RAIL_ITEMS = [
    {
        key: "customer",
        name: "Khách hàng",
        icon: "fa-users",
        actionXmlId: "dl_partner.action_dl_customer",
        menuXmlIds: ["dl_partner.menu_dl_sale_customer"],
    },
    {
        key: "supplier",
        name: "NCC / Thầu phụ",
        icon: "fa-truck",
        actionXmlId: "dl_partner.action_dl_supplier",
        menuXmlIds: [
            "dl_partner.menu_dl_sale_supplier",
            "dl_partner.menu_dl_sale_supplier_readonly",
        ],
        // Trưởng KD dùng action chỉ đọc; luôn mở action của menu thực tế theo vai trò.
        preferMenu: true,
    },
    {
        key: "quotation",
        name: "Báo giá",
        icon: "fa-file-text-o",
        actionXmlId: "dl_sale.action_dl_quotation",
        menuXmlIds: ["dl_sale.menu_dl_sale_quotation"],
    },
    // Phê duyệt — chỉ hiện với user thấy được menu (CEO/Trưởng KD/vai trò duyệt).
    // menuXmlIds ⇒ rail LỌC RBAC đồng bộ Home; actionXmlId do dl_sale nav_patch gán.
    {
        key: "approval",
        name: "Phê duyệt",
        icon: "fa-check-square-o",
        actionXmlId: null,
        menuXmlIds: ["dl_sale.menu_dl_sale_quote_approval"],
    },
    {
        key: "product",
        name: "Sản phẩm & Vật tư",
        icon: "fa-cube",
        actionXmlId: null,
        menuXmlIds: ["dl_base.menu_dl_product"],
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        icon: "fa-cogs",
        actionXmlId: null,
        menuXmlIds: ["dl_base.menu_dl_technical"],
    },
    {
        key: "pricing",
        name: "Bảng giá",
        icon: "fa-money",
        actionXmlId: null,
        menuXmlIds: ["dl_product.menu_dl_pricing_root"],
    },
    {
        key: "report",
        name: "Báo cáo",
        icon: "fa-bar-chart",
        actionXmlId: null,
        menuXmlIds: ["dl_base.menu_dl_report"],
    },
    {
        key: "config",
        name: "Cấu hình",
        icon: "fa-sliders",
        actionXmlId: null,
        menuXmlIds: ["dl_base.menu_dl_config"],
    },
];

export class DlmRail extends Component {
    static template = "dl_base.DlmRail";
    static props = {};
    static components = { ErrorHandler };

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.railItems = RAIL_ITEMS;
        this._dlmApp = this.menuService.getApps().find((app) => app.xmlid === DLM_APP_XMLID);
        this.state = useState({ visible: this._inDlmApp(), expanded: {} });
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

    toggleSidebar() {
        toggleSidebar();
    }

    _inDlmApp() {
        const app = this.menuService.getCurrentApp();
        return !!app && app.xmlid === DLM_APP_XMLID;
    }

    // Chỉ hiện mục khi user thấy menu đích và menu đó thực sự mở được một màn
    // (trực tiếp hoặc qua menu con). Nhờ đó không còn mục dẫn tới trang trắng.
    // Nhóm có children (đã dẹp hub thành submenu) hiện khi còn ít nhất 1 mục con
    // user thấy được — RBAC của nhóm suy ra từ RBAC các mục con.
    get visibleItems() {
        return this.railItems.filter((item) => {
            // Nhóm: giữ nguyên gate RBAC cấp cha (menu container) rồi mới xét còn
            // mục con nào thấy được — không để lộ nhóm cho vai trò không có quyền.
            if (item.children && item.children.length) {
                return this._entryVisible(item) && this.visibleChildren(item).length > 0;
            }
            return this._entryVisible(item);
        });
    }

    // Một entry (mục cha leaf hoặc mục con) hiện được khi có menu đích mở được màn.
    _entryVisible(entry) {
        if (!entry.menuXmlIds || !entry.menuXmlIds.length) return false;
        return entry.menuXmlIds.some((xmlid) => {
            const menu = this._findVisibleMenu(xmlid);
            return menu && this._hasActionableMenu(menu);
        });
    }

    // Các mục con của nhóm mà user thấy được (lọc theo RBAC như mục cha).
    visibleChildren(item) {
        return (item.children || []).filter((child) => this._entryVisible(child));
    }

    // Bấm nhãn nhóm: mở thẳng màn con đầu tiên (màn dùng nhiều nhất) + xổ submenu
    // để thấy các màn còn lại → bỏ hẳn màn hub trung chuyển.
    openGroupDefault(item) {
        const children = this.visibleChildren(item);
        if (!children.length) return;
        this.state.expanded[item.key] = true;
        this.openChild(children[0], item.key);
    }

    openChild(child, groupKey) {
        setActiveKey(groupKey);
        // preferMenu: mở qua menu để lấy đúng action theo vai trò (bản đầy đủ /
        // chỉ-đọc khác nhau — vd Sản phẩm, Bảng giá).
        if (child.preferMenu) {
            const menu = this._resolveItemMenu(child);
            if (menu) {
                this.menuService.selectMenu(menu);
                return;
            }
        }
        if (child.actionXmlId) {
            this.actionService.doAction(child.actionXmlId, { clearBreadcrumbs: true });
        }
    }

    // Khối tài khoản đáy rail — chỉ lấy user menu (Đăng xuất / Tùy chọn). Không
    // lấy messaging/activities để tránh mount trùng khi rail còn ẩn trên Trang chủ.
    get accountSystrayItems() {
        return systrayRegistry
            .getEntries()
            .filter(([key]) => key === "web.user_menu")
            .map(([key, value]) => ({ key, ...value }));
    }

    handleSystrayError(error, item) {
        item.isDisplayed = () => false;
        Promise.resolve().then(() => { throw error; });
    }

    _menuVisible(xmlid) {
        const menu = this._findVisibleMenu(xmlid);
        return !!menu && this._hasActionableMenu(menu);
    }

    _findVisibleMenu(xmlid) {
        if (!this._dlmApp) return null;
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        return this._findMenuByXmlId(tree, xmlid);
    }

    _hasActionableMenu(menu) {
        if (!menu) return false;
        if (menu.actionID) return true;
        return (menu.childrenTree || []).some((child) => this._hasActionableMenu(child));
    }

    _resolveItemMenu(item) {
        if (!this._dlmApp) return null;
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        for (const xmlid of item.menuXmlIds || []) {
            const menu = this._findMenuByXmlId(tree, xmlid);
            if (menu && this._hasActionableMenu(menu)) return menu;
        }
        return null;
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

    toggleSubmenu(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    openModule(actionXmlId, key) {
        if (!actionXmlId) return;
        if (key) {
            setActiveKey(key);
        }
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }

    openItem(item) {
        setActiveKey(item.key);
        if (item.preferMenu) {
            const menu = this._resolveItemMenu(item);
            if (menu) {
                this.menuService.selectMenu(menu);
                return;
            }
        }
        this.openModule(item.actionXmlId, item.key);
    }
}

registry.category("main_components").add("dlm_rail.DlmRail", { Component: DlmRail });
