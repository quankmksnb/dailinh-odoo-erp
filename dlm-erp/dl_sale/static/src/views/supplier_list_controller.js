/** @odoo-module **/
// ============================================================
//  DL Supplier List — kế thừa DlListBaseController (khung chung).
//  Đăng ký view js_class="dl_supplier_list" (dùng ở supplier_views.xml).
//  Đồng bộ giao diện với danh sách Khách hàng:
//   1) Avatar chữ cái nền màu cho từng dòng.
//  (Chip lọc theo Nhóm vật tư cung cấp đã bỏ — category_id là Tags multi-
//   value, dùng Group By chuẩn của Odoo thay vì chip loại trừ lẫn nhau.)
// ============================================================

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { DlListBaseController } from "./dl_list_controller";

const AVA_PALETTE = [
    { bg: "#dbe7ff", fg: "#1e4fa3" },
    { bg: "#e3f6e8", fg: "#1b7a3d" },
    { bg: "#fff1cc", fg: "#8a5a00" },
    { bg: "#ece0fb", fg: "#5b3fa0" },
    { bg: "#d9f2f4", fg: "#0f6b73" },
    { bg: "#fde2e4", fg: "#b23a48" },
];
function avaColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) {
        h = (h * 31 + name.charCodeAt(i)) >>> 0;
    }
    return AVA_PALETTE[h % AVA_PALETTE.length];
}

export class DlSupplierListController extends DlListBaseController {
    get dlCountNoun() {
        return "nhà cung cấp";
    }

    _dlRenderChrome(root) {
        super._dlRenderChrome(root);
        this._renderAvatars(root);
    }

    // Chèn avatar chữ cái theo tên NCC vào ô avatar_128 mỗi dòng.
    _renderAvatars(root) {
        const rows = root.querySelectorAll(".o_list_table tbody tr.o_data_row");
        for (const row of rows) {
            const cell = row.querySelector("td[name='avatar_128']");
            const nameCell = row.querySelector("td[name='name']");
            if (!cell || !nameCell) {
                continue;
            }
            const name = (nameCell.textContent || "").trim();
            let ava = cell.querySelector(".dl-letter-ava");
            if (!ava) {
                ava = document.createElement("span");
                ava.className = "dl-letter-ava";
                cell.appendChild(ava);
            }
            const c = avaColor(name);
            ava.textContent = name ? name[0].toUpperCase() : "?";
            ava.style.background = c.bg;
            ava.style.color = c.fg;
        }
    }
}

registry.category("views").add("dl_supplier_list", {
    ...listView,
    Controller: DlSupplierListController,
});
