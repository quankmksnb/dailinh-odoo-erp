/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

const STORAGE_KEY = "dlm.sidebar.collapsed";
const ACTIVE_KEY = "dlm.sidebar.activeKey";

export const sidebarState = reactive({
    collapsed: browser.localStorage.getItem(STORAGE_KEY) === "1",
    activeKey: browser.localStorage.getItem(ACTIVE_KEY) || null,
});

export function toggleSidebar() {
    sidebarState.collapsed = !sidebarState.collapsed;
    browser.localStorage.setItem(STORAGE_KEY, sidebarState.collapsed ? "1" : "0");
}

export function setActiveKey(key) {
    sidebarState.activeKey = key;
    browser.localStorage.setItem(ACTIVE_KEY, key || "");
}
