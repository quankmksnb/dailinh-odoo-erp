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
import { DlListBaseController } from "@dl_base/views/dl_list_controller";
import { avatarInitial, avatarColor } from "@dl_base/js/avatar_letter";
import { useService } from "@web/core/utils/hooks";
import { onWillStart } from "@odoo/owl";

export class DlSupplierListController extends DlListBaseController {
    setup() {
        super.setup();
        this.userService = useService("user");
        // Chỉ Admin và Mua hàng được sửa dữ liệu NCC — khớp ir.model.access:
        // dl_group_purchasing 1,1,1,0 và dl_group_admin 1,1,1,1; CEO, Trưởng KD
        // và Kế toán đều chỉ có perm_read.
        //
        // Trước đây điều kiện là `isSM && !isAdmin && !isAcc`, tức mặc định coi
        // mọi vai trò khác là toàn quyền — CEO vào menu NCC (menu_dl_sale_supplier
        // có nhóm CEO) thấy nút Thêm/Xoá rồi bấm là ăn lỗi quyền. Đảo lại thành
        // danh sách CHO PHÉP để không sót vai trò nào.
        this._dlReadonly = false;
        onWillStart(async () => {
            const [isAdmin, isPurchasing] = await Promise.all([
                this.userService.hasGroup("dl_base.dl_group_admin"),
                this.userService.hasGroup("dl_base.dl_group_purchasing"),
            ]);
            this._dlReadonly = !(isAdmin || isPurchasing);
            if (this._dlReadonly) {
                const aa = this.activeActions || (this.archInfo && this.archInfo.activeActions);
                if (aa) {
                    aa.create = false;
                    aa.delete = false;
                    aa.duplicate = false;
                }
            }
        });
    }

    get dlCountNoun() {
        return "nhà cung cấp";
    }

    get dlFilterDropdowns() {
        return [
            {
                key: "status",
                label: "Tất cả trạng thái",
                filters: [
                    { name: "active", label: "Đang hợp tác" },
                    { name: "inactive", label: "Ngừng hợp tác" },
                ],
            },
            {
                key: "date",
                label: "Tất cả thời gian",
                filters: [
                    { name: "date_today", label: "Hôm nay" },
                    { name: "date_7days", label: "7 ngày qua" },
                    { name: "date_30days", label: "30 ngày qua" },
                ],
            },
        ];
    }

    _dlRenderChrome(root) {
        super._dlRenderChrome(root);
        this._renderAvatars(root);
        if (this._dlReadonly) {
            // Fallback DOM: ẩn cụm nút Thêm nếu template còn render.
            const btns = root.querySelector(".o_control_panel_main_buttons");
            if (btns) {
                btns.style.display = "none";
            }
        }
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
            const c = avatarColor(name);
            ava.textContent = avatarInitial(name);
            ava.style.background = c.bg;
            ava.style.color = c.fg;
        }
    }
}

registry.category("views").add("dl_supplier_list", {
    ...listView,
    Controller: DlSupplierListController,
});
