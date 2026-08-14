/** @odoo-module **/

import {
  Component,
  useState,
  useEffect,
  onWillStart,
  onWillUnmount,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { ErrorHandler } from "@web/core/utils/components";
import {
  sidebarState,
  toggleSidebar,
  setActiveKey,
  setActiveChildKey,
} from "@dl_base/js/sidebar_state";

// Chu kỳ làm mới badge (số việc chờ) — đủ nhanh để người duyệt thấy việc mới,
// đủ thưa để không dội server. Chỉ chạy khi rail đang hiện (trong app DLM).
const BADGE_POLL_MS = 60000;

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
    name: "Nhà cung cấp / Thầu phụ",
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
  // menuXmlIds ⇒ rail LỌC RBAC đồng bộ Home; actionXmlId do dl_sale/nav_patch.js gán.
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
  // Kho — mục con do dl_inventory/nav_patch.js gắn (Tồn kho, Lô hàng...).
  // menuXmlIds trỏ menu container ⇒ rail lọc RBAC đồng bộ với Home.
  {
    key: "inventory",
    name: "Kho",
    icon: "fa-archive",
    actionXmlId: null,
    menuXmlIds: ["dl_base.menu_dl_inventory"],
  },
  // Mua hàng — mục con do dl_purchase/nav_patch.js gắn (Đơn mua, Trả hàng NCC).
  // An toàn khi CHƯA cài dl_purchase: menu container khai ở dl_base nhưng lúc
  // đó không có mục con nào có action ⇒ `_hasActionableMenu` lọc cả nhóm ra
  // khỏi rail, đúng như Kho trước khi dl_inventory tồn tại.
  {
    key: "purchase",
    name: "Mua hàng",
    icon: "fa-shopping-cart",
    actionXmlId: null,
    menuXmlIds: ["dl_base.menu_dl_purchase"],
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
    this._dlmApp = this.menuService
      .getApps()
      .find((app) => app.xmlid === DLM_APP_XMLID);
    this.state = useState({ visible: this._inDlmApp(), expanded: {} });
    this.sidebar = useState(sidebarState);

    // Badge số việc chờ trên từng mục (vd "Phê duyệt"). Giá trị đếm do các
    // module nghiệp vụ đăng ký qua registerBadge (rail dl_base không biết
    // model phê duyệt) — xem dl_sale/nav_patch.js.
    this.badges = useState({});
    this._badgeFetchers = {};

    // "MENUS:APP-CHANGED" chỉ phát khi ĐỔI app (selectMenu / app switcher);
    // điều hướng nội bộ DLM bằng doAction không đổi app nên rail vẫn hiện.
    useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
      this.state.visible = this._inDlmApp();
      // Quay lại app DLM thì đồng bộ lại số việc chờ ngay (không đợi poll).
      if (this.state.visible) {
        this._refreshBadges();
      }
    });

    // Nạp số lần đầu SAU khi các patch (dl_sale…) đã đăng ký fetcher —
    // onWillStart chạy sau setup nên fetcher chắc chắn đã có mặt.
    onWillStart(() => this._refreshBadges());
    this._badgeTimer = browser.setInterval(() => {
      if (this.state.visible) {
        this._refreshBadges();
      }
    }, BADGE_POLL_MS);
    onWillUnmount(() => browser.clearInterval(this._badgeTimer));

    // Đồng bộ class trên <body> để CSS ẩn navbar Odoo + chừa chỗ cho rail.
    useEffect(
      (visible, collapsed) => {
        document.body.classList.toggle("dlm-rail-active", visible);
        document.body.classList.toggle(
          "dlm-rail-collapsed",
          visible && collapsed,
        );
        return () => {
          document.body.classList.remove("dlm-rail-active");
          document.body.classList.remove("dlm-rail-collapsed");
        };
      },
      () => [this.state.visible, this.sidebar.collapsed],
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
        return (
          this._entryVisible(item) && this.visibleChildren(item).length > 0
        );
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

  openChild(child, groupKey) {
    setActiveKey(groupKey);
    // Tô mục con đang chọn trong submenu (nhóm cha vẫn active nhờ groupKey).
    setActiveChildKey(child.key);
    // Điều hướng thường xảy ra sau khi vừa xử lý việc ở màn trước → làm mới
    // số việc chờ để badge phản ánh ngay, không đợi hết chu kỳ poll.
    this._refreshBadges();
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
      this.actionService.doAction(child.actionXmlId, {
        clearBreadcrumbs: true,
      });
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
    Promise.resolve().then(() => {
      throw error;
    });
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
    return (menu.childrenTree || []).some((child) =>
      this._hasActionableMenu(child),
    );
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
    // Khi rail đang thu gọn, cần mở rộng trước để submenu vừa được xổ có thể
    // nhìn thấy ngay. Mục cha chỉ điều khiển submenu, không điều hướng màn hình.
    if (this.sidebar.collapsed) {
      toggleSidebar();
      this.state.expanded[key] = true;
      return;
    }
    this.state.expanded[key] = !this.state.expanded[key];
  }

  // Module nghiệp vụ đăng ký hàm đếm việc chờ cho một mục rail. fetcher là
  // hàm async trả về số nguyên; rail hiện badge khi số > 0.
  registerBadge(key, fetcher) {
    this._badgeFetchers[key] = fetcher;
  }

  // Badge hiện trên ĐẦU NHÓM khi submenu đang thu gọn: gộp badge của chính nhóm
  // + của các mục con thấy được. Nhờ đó việc chờ (vd "Vật tư chờ định giá") vẫn
  // đập vào mắt dù chưa xổ nhóm — giống badge "Phê duyệt". Khi nhóm đã xổ thì
  // trả 0 để nhường chỗ cho badge riêng của từng mục con (khỏi đếm hai lần).
  groupBadgeCount(item) {
    // Nhường badge cho mục con CHỈ khi submenu thực sự đang hiện (đã xổ VÀ rail
    // không thu gọn). Rail thu gọn ẩn submenu bằng CSS dù state.expanded còn
    // bật, nên vẫn phải gộp lên đầu nhóm để không mất số việc chờ.
    if (this.state.expanded[item.key] && !this.sidebar.collapsed) {
      return 0;
    }
    let total = this.badges[item.key] || 0;
    for (const child of this.visibleChildren(item)) {
      total += this.badges[child.key] || 0;
    }
    return total;
  }

  async _refreshBadges() {
    // Chỉ đếm cho mục user thực sự thấy — vai trò không có tab Phê duyệt thì
    // không phát sinh truy vấn đếm thừa mỗi chu kỳ poll. Gồm cả mục con của
    // nhóm (vd "Vật tư chờ định giá" nằm trong nhóm "Bảng giá").
    const visibleKeys = new Set();
    for (const item of this.visibleItems) {
      visibleKeys.add(item.key);
      if (item.children && item.children.length) {
        for (const child of this.visibleChildren(item)) {
          visibleKeys.add(child.key);
        }
      }
    }
    for (const key of Object.keys(this._badgeFetchers)) {
      if (!visibleKeys.has(key)) {
        continue;
      }
      try {
        this.badges[key] = await this._badgeFetchers[key]();
      } catch {
        // Lỗi đếm (quyền/kết nối) không được làm hỏng rail — coi như 0.
        this.badges[key] = 0;
      }
    }
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
    // Mục leaf (không submenu) → không mục con nào active.
    setActiveChildKey(null);
    this._refreshBadges();
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

registry
  .category("main_components")
  .add("dlm_rail.DlmRail", { Component: DlmRail });
