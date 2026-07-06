/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

const STORAGE_KEY = "dlm.sidebar.collapsed";

export const sidebarState = reactive({
    collapsed: browser.localStorage.getItem(STORAGE_KEY) === "1",
});

export function toggleSidebar() {
    sidebarState.collapsed = !sidebarState.collapsed;
    browser.localStorage.setItem(STORAGE_KEY, sidebarState.collapsed ? "1" : "0");
}
