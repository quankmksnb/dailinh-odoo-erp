/** @odoo-module **/
// ============================================================
//  Menu ⋮ "Thao tác" dùng chung cho form & list của DLM.
//  Trước đây menu này bị dựng lặp ở nhiều controller (form: Nhân bản/
//  Xoá; list: Nhập/Xuất) → gom về MỘT nơi tại đây để không trùng code.
//  Menu do JS tự dựng (không qua Owl) nên gắn sự kiện an toàn; khung &
//  style .dl-actions-* nằm ở scss/control_panel.scss.
//  Cung cấp 2 hàm:
//    • buildActionsMenu(container, specs, opts) — dựng menu tổng quát.
//    • setupFormActionsMenu(ctrl) — hook sẵn cho FormController (Nhân
//      bản/Xoá + tooltip nút mở bản ghi liên kết).
// ============================================================

import { useEffect } from "@odoo/owl";

// ── Dựng menu ⋮ trong `container` ───────────────────────────
// Idempotent: gọi lại nhiều lần chỉ trả về menu đã dựng (tránh nhân
// đôi). Trả về phần tử .dl-actions-menu (hoặc null nếu thiếu container)
// để caller tuỳ biến (vd: ẩn khi bản ghi mới chưa lưu).
// specs: [{ label, icon, onClick, danger? }]. opts.prepend: chèn đầu
// container (form/list generic) thay vì cuối (list tuỳ biến).
export function buildActionsMenu(container, specs, { prepend = false } = {}) {
    if (!container) {
        return null;
    }
    const existing = container.querySelector(".dl-actions-menu");
    if (existing) {
        return existing;
    }

    const menu = document.createElement("div");
    menu.className = "dl-actions-menu";
    menu.setAttribute("tabindex", "0");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "dl-actions-toggle";
    toggle.setAttribute("aria-label", "Thao tác");
    toggle.dataset.tooltip = "Thao tác";
    toggle.innerHTML = '<i class="fa fa-ellipsis-v"></i>';

    const list = document.createElement("div");
    list.className = "dl-actions-list";
    list.setAttribute("role", "menu");
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
    if (prepend) {
        container.prepend(menu);
    } else {
        container.appendChild(menu);
    }
    return menu;
}

// ── Menu ⋮ cho FormController: Nhân bản / Xoá ───────────────
// Gọi trong setup() của controller (chạy trong useEffect nên an toàn
// với vòng đời render). Dùng thẳng handler sẵn có của Odoo:
// duplicateRecord() / deleteRecord() (deleteRecord đã có hộp xác nhận).
export function setupFormActionsMenu(ctrl) {
    useEffect(() => {
        const root = ctrl.rootRef.el;
        if (!root) {
            return;
        }
        const container =
            root.querySelector(".o_control_panel_navigation") ||
            root.querySelector(".o_control_panel_breadcrumbs");
        const menu = buildActionsMenu(
            container,
            [
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
            ],
            { prepend: true }
        );
        if (menu) {
            // Bản ghi mới chưa lưu → chưa có gì để nhân bản/xoá
            menu.style.display = ctrl.model.root.isNew ? "none" : "";
        }

        // Tooltip tiếng Việt cho nút "→" mở bản ghi liên kết (many2one)
        root.querySelectorAll(".o_field_many2one .o_external_button").forEach((btn) => {
            btn.dataset.tooltip = "Mở trang thông tin";
            btn.setAttribute("aria-label", "Mở trang thông tin");
        });
    });
}
