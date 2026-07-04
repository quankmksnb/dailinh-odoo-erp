/** @odoo-module **/

import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ErrorHandler } from "@web/core/utils/components";

const systrayRegistry = registry.category("systray");

const NAV_ITEMS = [
    {
        key: "home",
        name: "Trang chủ",
        icon: "fa-home",
        actionXmlId: null,
        active: true,
    },
    {
        key: "customer",
        name: "Khách hàng",
        icon: "fa-users",
        actionXmlId: "dl_sale.action_dl_customer",
    },
    {
        key: "quotation",
        name: "Báo giá",
        icon: "fa-file-text-o",
        actionXmlId: "dl_sale.action_dl_quotation",
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        icon: "fa-cogs",
        actionXmlId: null,
    },
    {
        key: "material",
        name: "Vật tư",
        icon: "fa-cubes",
        actionXmlId: "dlm_material.action_dl_material",
    },
    {
        key: "report",
        name: "Báo cáo",
        icon: "fa-bar-chart",
        actionXmlId: null,
    },
    {
        key: "config",
        name: "Cấu hình",
        icon: "fa-sliders",
        actionXmlId: null,
    },
];

const STATS = [
    { key: "month", label: "Báo giá tháng", value: "48", sub: "▲ 12%", subClass: "up", dot: "#5b4b9e" },
    { key: "pending", label: "Chờ duyệt", value: "3", sub: "hôm nay", subClass: "muted", dot: "#e0a044" },
    { key: "winrate", label: "Tỷ lệ BG thành công", value: "62%", sub: "▲ 4%", subClass: "up", dot: "#1b9e57" },
    { key: "revenue", label: "Doanh số BG", value: "1.2 tỷ", sub: "đã duyệt", subClass: "muted", dot: "#2f6fdb" },
];

const RECENT_QUOTATIONS = [
    { key: "q48", name: "BG/2026/0048", partner: "Cty TNHH Đại Linh", amount: "72.500.000", state: "Nháp", stateClass: "draft" },
    { key: "q47", name: "BG/2026/0047", partner: "Đinh Thị Thúy", amount: "31.500.000", state: "Đã gửi", stateClass: "sent" },
    { key: "q46", name: "BG/2026/0046", partner: "Cty Hoàng Gia", amount: "128.000.000", state: "Đã duyệt", stateClass: "approved" },
];

export class DlHome extends Component {
    static template = "dl_base.DlHome";
    static props = { ...standardActionServiceProps };
    static components = { Dropdown, DropdownItem, ErrorHandler };

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.userService = useService("user");
        this.navItems = NAV_ITEMS;
        this.stats = STATS;
        this.recentQuotations = RECENT_QUOTATIONS;

        // Ép "app hiện tại" luôn là DLM-ERP mỗi khi mở Dashboard (dù vào từ app
        // launcher, card trang Apps, hay URL trực tiếp) để rail + header tùy biến
        // hiển thị đúng khi sang các view con (Khách hàng/Báo giá).
        const dlmApp = this.menuService
            .getApps()
            .find((app) => app.xmlid === "dl_base.menu_dl_root");
        if (dlmApp && this.menuService.getCurrentApp()?.id !== dlmApp.id) {
            this.menuService.setCurrentMenu(dlmApp);
        }

        this.rootRef = useRef("root");
        this._closeTimer = null;
        this._onDocMouseMove = this._onDocMouseMove.bind(this);
        onMounted(() => document.addEventListener("mousemove", this._onDocMouseMove));
        onWillUnmount(() => {
            document.removeEventListener("mousemove", this._onDocMouseMove);
            if (this._closeTimer) { clearTimeout(this._closeTimer); }
        });
    }

    get userName() {
        return this.userService.name || "";
    }

    get greeting() {
        const hour = new Date().getHours();
        if (hour < 11) return "Chào buổi sáng";
        if (hour < 14) return "Chào buổi trưa";
        if (hour < 18) return "Chào buổi chiều";
        return "Chào buổi tối";
    }

    get systrayItems() {
        // Ẩn menu Developer tools khỏi header này.
        const HIDDEN = ["web.debug_mode_menu"];
        return systrayRegistry
            .getEntries()
            .filter(([key]) => !HIDDEN.includes(key))
            .map(([key, value]) => ({ key, ...value }))
            .filter((item) => ("isDisplayed" in item ? item.isDisplayed(this.env) : true))
            .reverse();
    }

    handleItemError(error, item) {
        item.isDisplayed = () => false;
        Promise.resolve().then(() => {
            throw error;
        });
    }

    get apps() {
        return this.menuService.getApps();
    }

    getMenuItemHref(payload) {
        const parts = [`menu_id=${payload.id}`];
        if (payload.actionID) {
            parts.push(`action=${payload.actionID}`);
        }
        return "#" + parts.join("&");
    }

    onAppSelected(menu) {
        if (menu) {
            this.menuService.selectMenu(menu);
        }
    }

    // Menu Odoo render ở portal (ngoài .dl-home) nên nghe ở document; timer
    // trễ để không đóng khi chuột đi qua khe hở giữa nút và menu.
    _onDocMouseMove(ev) {
        const t = ev.target;
        const overToggle = t.closest && t.closest(".dl-home .dropdown-toggle");
        const overMenu = t.closest && t.closest(".dropdown-menu, .o-dropdown--menu");

        if (overToggle || overMenu) {
            if (this._closeTimer) { clearTimeout(this._closeTimer); this._closeTimer = null; }

            // Rê vào một nút chưa mở → đóng nút khác đang mở rồi mở nút này
            if (
                overToggle &&
                overToggle !== this._openTgl &&
                overToggle.getAttribute("aria-expanded") === "false"
            ) {
                const root = this.rootRef.el;
                root && root
                    .querySelectorAll('.dropdown-toggle[aria-expanded="true"]')
                    .forEach((x) => { if (x !== overToggle) { x.click(); } });
                this._openTgl = overToggle;
                overToggle.click();
            }
            return;
        }

        if (!this._closeTimer && this._openTgl) {
            this._closeTimer = setTimeout(() => {
                this._closeTimer = null;
                this._openTgl = null;
                const root = this.rootRef.el;
                root && root
                    .querySelectorAll('.dropdown-toggle[aria-expanded="true"]')
                    .forEach((tg) => tg.click());
            }, 220);
        }
    }

    openModule(actionXmlId) {
        if (!actionXmlId) return;
        // clearBreadcrumbs: reset stack để breadcrumb không tích lũy dài.
        this.actionService.doAction(actionXmlId, { clearBreadcrumbs: true });
    }
}

registry.category("actions").add("dl_base.DlHomeAction", DlHome);
