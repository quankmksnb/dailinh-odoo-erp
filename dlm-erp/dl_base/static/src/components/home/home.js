/** @odoo-module **/

import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ErrorHandler } from "@web/core/utils/components";
import { setActiveKey, setActiveChildKey } from "@dl_base/js/sidebar_state";

const systrayRegistry = registry.category("systray");

// Card = một menu đích (menuXmlIds: cái ĐẦU TIÊN user thấy được sẽ dùng).
// Server đã lọc cây menu theo groups ⇒ card không tìm thấy menu nào là user
// không có quyền → ẨN card (RBAC hiển thị đồng nhất với menu, không cần
// hasGroup phía client).
const MODULE_CARDS = [
    {
        key: "customer",
        name: "Khách hàng",
        description: "Danh bạ khách hàng & liên hệ",
        icon: "fa-users",
        color: "#7c5caf",
        menuXmlIds: ["dl_partner.menu_dl_sale_customer"],
    },
    {
        key: "supplier",
        name: "Nhà cung cấp / Thầu phụ",
        description: "Nhà cung cấp & thầu phụ",
        icon: "fa-truck",
        color: "#2a8c82",
        // Trưởng KD chỉ có bản chỉ-đọc — menu nào thấy được thì mở menu đó.
        menuXmlIds: [
            "dl_partner.menu_dl_sale_supplier",
            "dl_partner.menu_dl_sale_supplier_readonly",
        ],
    },
    {
        key: "quotation",
        name: "Báo giá",
        description: "Yêu cầu báo giá & Báo giá",
        icon: "fa-file-text-o",
        color: "#4a90d9",
        // Trỏ thẳng menu hub Báo giá — trỏ menu cha "CRM & Báo giá" sẽ mở
        // nhầm menu con đầu tiên (Khách hàng).
        menuXmlIds: ["dl_sale.menu_dl_sale_quotation"],
    },
    {
        key: "approval",
        name: "Phê duyệt",
        description: "Báo giá vượt ngưỡng chờ duyệt",
        icon: "fa-check-square-o",
        color: "#c05c43",
        // Menu chỉ cấp cho CEO/Trưởng KD/op-group "Duyệt báo giá" — user khác
        // không thấy menu ⇒ card tự ẩn (cơ chế lọc chung ở trên).
        menuXmlIds: ["dl_sale.menu_dl_sale_quote_approval"],
        // Badge: số yêu cầu duyệt báo giá đang chờ — chỉ đếm khi card hiển thị.
        badge: {
            model: "dl.pricing.approval.request",
            domain: [
                ["request_type", "=", "quote_over_threshold"],
                ["state", "=", "pending"],
            ],
        },
    },
    {
        key: "product",
        name: "Sản phẩm & Vật tư",
        description: "Quản lý Sản phẩm và Vật tư",
        icon: "fa-cube",
        color: "#1a9e6f",
        menuXmlIds: ["dl_base.menu_dl_product"],
    },
    {
        key: "technical",
        name: "Kỹ thuật",
        description: "BOM, bản vẽ & công thức tham số",
        icon: "fa-cogs",
        color: "#7c5caf",
        menuXmlIds: ["dl_base.menu_dl_technical"],
    },
    {
        key: "pricing",
        name: "Bảng giá",
        description: "Bảng giá sản phẩm thương mại / Vật tư",
        icon: "fa-money",
        color: "#c49052",
        menuXmlIds: ["dl_product.menu_dl_pricing_root"],
    },
    {
        key: "config",
        name: "Cấu hình",
        description: "Tham số giá, phân quyền & danh mục dùng chung",
        icon: "fa-sliders",
        color: "#5a6a6a",
        menuXmlIds: ["dl_base.menu_dl_config"],
    },
];

// Landing theo vai trò: đăng nhập vào THẲNG màn nghiệp vụ chính của vai trò,
// bỏ bước dừng ở lưới thẻ (giảm 1 click thừa lặp mỗi lần mở app).
// - Thứ tự = ĐỘ ƯU TIÊN khi user giữ nhiều vai trò (khớp rule đầu tiên).
// - actionXmlId là chuỗi module con — dl_base không cần phụ thuộc XML (giống rail.js).
// - Không khớp vai trò nào ⇒ giữ lưới thẻ làm fallback.
// Đích land = MÀN THẬT (không land vào hub — hub đã bị dẹp thành submenu ở rail).
// railKey = key nhóm rail tương ứng để tô đúng vệt sáng sidebar khi vào thẳng.
const LANDING_RULES = [
    { group: "dl_base.dl_group_ceo", actionXmlId: "dl_sale.action_dl_quote_approval", railKey: "approval" },
    { group: "dl_base.dl_group_sales_manager", actionXmlId: "dl_sale.action_dl_quotation", railKey: "quotation", railChildKey: "quotation_list" },
    { group: "dl_base.dl_group_ba", actionXmlId: "dl_sale.action_dl_quotation", railKey: "quotation", railChildKey: "quotation_list" },
    // Thủ kho land thẳng vào "Nhận hàng" — cùng mục với vệt sáng rail, hết lệch.
    // (Land vào Hàng đợi phiếu gây khó chịu: màn "Hàng đợi" nhưng rail tô "Nhận
    // hàng", vì hàng đợi cố ý không lên rail nên chỉ tô được mục con gần nhất.)
    { group: "dl_base.dl_group_warehouse", actionXmlId: "dl_inventory.action_dl_picking_receipt", railKey: "inventory", railChildKey: "receipt" },
    // Mua hàng sở hữu giá NCC → land thẳng Bảng giá Vật tư (bản có quyền sửa).
    { group: "dl_base.dl_group_purchasing", actionXmlId: "dl_product.action_dl_supplierinfo_material_full", railKey: "pricing", railChildKey: "material_price" },
    { group: "dl_base.dl_group_tech", actionXmlId: "dl_technical.action_dl_quotation_request_my", railKey: "technical", railChildKey: "rfq" },
    { group: "dl_base.dl_group_admin", actionXmlId: "dl_config.action_dl_user_admin", railKey: "config", railChildKey: "user" },
];

export class DlHome extends Component {
    static template = "dl_base.DlHome";
    static props = { ...standardActionServiceProps };
    static components = { Dropdown, DropdownItem, ErrorHandler };

    setup() {
        this.actionService = useService("action");
        this.menuService = useService("menu");
        this.orm = useService("orm");
        this.userService = useService("user");
        // Số đếm badge theo card.key (vd Phê duyệt: số yêu cầu đang chờ).
        this.badgeCounts = useState({});
        // redirecting = true ⇒ template hiện loader thay vì chớp lưới thẻ rồi nhảy.
        this.state = useState({ redirecting: false });
        // Action đích + key nhóm rail sẽ dùng sau khi mount (khớp vai trò ở onWillStart).
        this._landingAction = null;
        this._landingKey = null;
        // Mục con trong submenu ứng với màn land (nếu land thẳng vào 1 mục con,
        // vd Kỹ thuật → RFQ cần xử lý). null = land vào màn nhóm/leaf.
        this._landingChildKey = null;

        this._dlmApp = this.menuService
            .getApps()
            .find((app) => app.xmlid === "dl_base.menu_dl_root");
        if (this._dlmApp && this.menuService.getCurrentApp()?.id !== this._dlmApp.id) {
            this.menuService.setCurrentMenu(this._dlmApp);
        }

        onWillStart(async () => {
            await this._resolveLanding();
            // Chỉ đếm badge khi ở lại lưới thẻ (không redirect) — tránh gọi thừa.
            if (!this.state.redirecting) {
                await this._loadBadges();
            }
        });
        // Redirect sau khi mount: doAction thay toàn bộ action hiện tại bằng màn
        // nghiệp vụ; rail vẫn hiện vì là main_component độc lập với action.
        onMounted(() => {
            if (this._landingAction) {
                // Tô đúng vệt sáng nhóm rail cho màn land (localStorage có thể còn
                // giữ key nhóm cũ từ phiên trước → lệch nếu không set lại).
                setActiveKey(this._landingKey);
                setActiveChildKey(this._landingChildKey);
                this.actionService.doAction(this._landingAction, { clearBreadcrumbs: true });
            }
        });
    }

    // Khớp vai trò user với LANDING_RULES đầu tiên; đặt cờ redirecting để template
    // hiện loader. Lỗi hasGroup (mạng/khởi tạo) thì bỏ qua → về lưới thẻ an toàn.
    async _resolveLanding() {
        for (const rule of LANDING_RULES) {
            try {
                if (await this.userService.hasGroup(rule.group)) {
                    this._landingAction = rule.actionXmlId;
                    this._landingKey = rule.railKey;
                    this._landingChildKey = rule.railChildKey || null;
                    this.state.redirecting = true;
                    return;
                }
            } catch {
                // bỏ qua rule lỗi, thử rule tiếp theo
            }
        }
    }

    async _loadBadges() {
        // Chỉ đếm cho card user thấy được; lỗi (vd thiếu quyền đọc) thì bỏ
        // badge, không làm vỡ trang chủ.
        await Promise.all(
            this.cards
                .filter((card) => card.badge)
                .map(async (card) => {
                    try {
                        this.badgeCounts[card.key] = await this.orm.searchCount(
                            card.badge.model, card.badge.domain);
                    } catch {
                        this.badgeCounts[card.key] = 0;
                    }
                })
        );
    }

    // Chỉ hiện card mà user thấy được menu đích (cây menu đã lọc theo groups).
    get cards() {
        return MODULE_CARDS.filter((card) => this._resolveCardMenu(card));
    }

    get _level1Menus() {
        if (!this._dlmApp) return [];
        const tree = this.menuService.getMenuAsTree(this._dlmApp.id);
        return tree?.childrenTree || [];
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

    get systrayItems() {
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
        Promise.resolve().then(() => { throw error; });
    }

    get apps() {
        return this.menuService.getApps();
    }

    getMenuItemHref(payload) {
        const parts = [`menu_id=${payload.id}`];
        if (payload.actionID) parts.push(`action=${payload.actionID}`);
        return "#" + parts.join("&");
    }

    onAppSelected(menu) {
        if (menu) this.menuService.selectMenu(menu);
    }

    openCard(card) {
        const menu = this._resolveCardMenu(card);
        if (!menu) return;
        // Ghi lại card đang active để rail/sidebar highlight (đồng bộ develop).
        setActiveKey(card.key);
        // Mở menu con đầu tiên có action. (Trước đây nav_patch gán actionXmlId
        // để card mở màn hub của module — tầng hub đã bỏ, xem CLAUDE.md.)
        const target = this._findFirstActionMenu(menu);
        if (target) this.menuService.selectMenu(target);
    }

    _findFirstActionMenu(menu) {
        if (menu.actionID) return menu;
        for (const child of menu.childrenTree || []) {
            const found = this._findFirstActionMenu(child);
            if (found) return found;
        }
        return null;
    }
}

registry.category("actions").add("dl_base.DlHomeAction", DlHome);
