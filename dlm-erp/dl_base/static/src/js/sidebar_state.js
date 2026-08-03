/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

const STORAGE_KEY = "dlm.sidebar.collapsed";
const ACTIVE_KEY = "dlm.sidebar.activeKey";
const ACTIVE_CHILD_KEY = "dlm.sidebar.activeChildKey";

export const sidebarState = reactive({
    collapsed: browser.localStorage.getItem(STORAGE_KEY) === "1",
    activeKey: browser.localStorage.getItem(ACTIVE_KEY) || null,
    // Mục con đang mở trong submenu (vd "rfq" dưới nhóm "technical"). Tách khỏi
    // activeKey (nhóm cha) để tô đúng CẢ nhóm lẫn mục con đang xem.
    activeChildKey: browser.localStorage.getItem(ACTIVE_CHILD_KEY) || null,
});

export function toggleSidebar() {
    sidebarState.collapsed = !sidebarState.collapsed;
    browser.localStorage.setItem(STORAGE_KEY, sidebarState.collapsed ? "1" : "0");
}

export function setActiveKey(key) {
    sidebarState.activeKey = key;
    browser.localStorage.setItem(ACTIVE_KEY, key || "");
}

// Đặt mục con đang active (null = không mục con nào, dùng khi vào màn leaf/nhóm).
export function setActiveChildKey(key) {
    sidebarState.activeChildKey = key || null;
    browser.localStorage.setItem(ACTIVE_CHILD_KEY, key || "");
}
