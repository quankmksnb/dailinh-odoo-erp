/** @odoo-module **/
// ============================================================
//  Controllers tuỳ biến cho DLM:
//  1) Form Báo giá: đưa nút Duyệt/Từ chối lên hàng breadcrumb.
//  2) Gom các action phụ vào MENU ⋮ ở góc trên phải (chuẩn ERP):
//     - Form: Nhân bản (secondary), Xoá (đỏ + xác nhận).
//     - List: Nhập, Xuất.
//  Menu do JS tự dựng (không do Owl quản lý) → gắn sự kiện an toàn;
//  gọi thẳng hàm sẵn có của Odoo (duplicateRecord/deleteRecord/
//  onExportData/action import). deleteRecord đã có hộp xác nhận.
// ============================================================

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useEffect } from "@odoo/owl";

// Dựng menu ⋮ (nếu chưa có) trong container, mở khi hover.
function ensureActionsMenu(container, specs) {
    if (!container || container.querySelector(".dl-actions-menu")) {
        return container && container.querySelector(".dl-actions-menu");
    }
    const menu = document.createElement("div");
    menu.className = "dl-actions-menu";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "dl-actions-toggle";
    toggle.setAttribute("aria-label", "Thao tác");
    toggle.dataset.tooltip = "Thao tác";
    toggle.innerHTML = '<i class="fa fa-ellipsis-v"></i>';

    const list = document.createElement("div");
    list.className = "dl-actions-list";
    for (const spec of specs) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "dl-actions-item" + (spec.danger ? " dl-actions-danger" : "");
        item.innerHTML = `<i class="fa ${spec.icon}"></i><span>${spec.label}</span>`;
        item.addEventListener("click", (ev) => {
            ev.stopPropagation();
            menu.classList.remove("dl-open");
            spec.onClick();
        });
        list.appendChild(item);
    }

    menu.appendChild(toggle);
    menu.appendChild(list);
    container.prepend(menu);
    return menu;
}

// ── Form: menu ⋮ với Nhân bản / Xoá ─────────────────────────
function setupFormActionsMenu(ctrl) {
    useEffect(() => {
        const root = ctrl.rootRef.el;
        if (!root) {
            return;
        }
        const container =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_breadcrumbs");
        const menu = ensureActionsMenu(container, [
            {
                label: "Nhân bản",
                icon: "fa-clone",
                onClick: () => ctrl.duplicateRecord && ctrl.duplicateRecord(),
            },
            {
                label: "Xoá",
                icon: "fa-trash-o",
                danger: true,
                onClick: () => ctrl.deleteRecord && ctrl.deleteRecord(),
            },
        ]);
        if (menu) {
            // Bản ghi mới chưa lưu → chưa có gì để nhân bản/xoá
            menu.style.display = ctrl.model.root.isNew ? "none" : "";
        }

        // Tooltip tiếng Việt cho nút "→" mở bản ghi liên kết
        root.querySelectorAll(".o_field_many2one .o_external_button").forEach((btn) => {
            btn.dataset.tooltip = "Mở trang thông tin";
            btn.setAttribute("aria-label", "Mở trang thông tin");
        });
    });
}

// ── Form Báo giá: + đưa nút Duyệt/Từ chối lên hàng breadcrumb ──
export class DlQuotationFormController extends FormController {
    setup() {
        super.setup();
        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            const buttons = root.querySelector(
                ".o_form_statusbar .o_statusbar_buttons"
            );
            const target =
                root.querySelector(".o_control_panel_breadcrumbs .o_breadcrumb") ||
                root.querySelector(".o_control_panel_breadcrumbs");
            if (buttons && target && buttons.parentElement !== target) {
                buttons.classList.add("dl-cp-actions");
                target.appendChild(buttons);
            }
        });
        setupFormActionsMenu(this);
    }
}

// ── Form Khách hàng: menu ⋮ Nhân bản / Xoá ──────────────────
export class DlCustomerFormController extends FormController {
    setup() {
        super.setup();
        setupFormActionsMenu(this);
    }
}

// ── List (báo giá + khách hàng): menu ⋮ Nhập / Xuất ─────────
export class DlListController extends ListController {
    setup() {
        super.setup();
        useEffect(() => {
            const root = this.rootRef.el;
            if (!root) {
                return;
            }
            const container =
                root.querySelector(".o_control_panel_navigation") ||
                root.querySelector(".o_control_panel_breadcrumbs");
            ensureActionsMenu(container, [
                { label: "Nhập", icon: "fa-upload", onClick: () => this.dlImport() },
                {
                    label: "Xuất",
                    icon: "fa-download",
                    onClick: () => this.onExportData && this.onExportData(),
                },
            ]);
        });
    }

    dlImport() {
        this.actionService.doAction({
            type: "ir.actions.client",
            tag: "import",
            params: { model: this.props.resModel, context: this.props.context },
        });
    }
}

registry.category("views").add("dl_quotation_form", {
    ...formView,
    Controller: DlQuotationFormController,
});
registry.category("views").add("dl_customer_form", {
    ...formView,
    Controller: DlCustomerFormController,
});
registry.category("views").add("dl_list", {
    ...listView,
    Controller: DlListController,
});
