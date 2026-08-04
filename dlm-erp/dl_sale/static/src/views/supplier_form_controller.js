/** @odoo-module **/
// ============================================================
//  DL Supplier Form — FormController tuỳ biến cho NCC / Thầu phụ.
//  Đăng ký view js_class="dl_supplier_form" (dùng ở supplier_views.xml).
//  Tuỳ biến:
//   - menu ⋮ Nhân bản/Xoá + breadcrumb "Thêm nhà cung cấp" cho bản ghi mới.
//   - Trưởng KD: chỉ đọc (S04).
//   - Chặn TỰ LƯU khi rời form: mặc định Odoo auto-save bản ghi dirty lúc rời
//     (form_controller.beforeLeave). Vì onchange tìm–liên kết điền sẵn form
//     ⇒ form "dirty", bấm quay lại sẽ tự lưu (gộp) ngoài ý muốn. Ta hỏi
//     xác nhận / xả bỏ thay vì tự lưu — chỉ gộp khi người dùng bấm Lưu.
//     (Đồng bộ hành vi với form Khách hàng.)
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onMounted, useEffect } from "@odoo/owl";

// PHẢI khớp _TAX_CODE_RE ở backend (res_partner.py) và widget dl_tax_code.
const TAX_CODE_RE = /^\d{10}(-\d{3})?$/;

export class DlSupplierFormController extends FormController {
    setup() {
        super.setup();
        this.userService = useService("user");
        this.dlNotification = useService("notification");
        this.dlDialog = useService("dialog");
        // Trưởng KD chỉ được XEM chi tiết NCC (S04) — không Sửa/Thêm/Xoá.
        // Bảo mật thật do ir.rule; đây chỉ khoá form ở UI. Kế toán/Admin full CRUD.
        this._dlGroupReadonly = false;
        // Chỉ coi là "có thay đổi thật" khi người dùng thực sự tương tác input —
        // fill tự động từ onchange KHÔNG bật cờ này.
        this._dlUserTouched = false;

        onWillStart(async () => {
            const [isSM, isAdmin, isAcc] = await Promise.all([
                this.userService.hasGroup("dl_base.dl_group_sales_manager"),
                this.userService.hasGroup("dl_base.dl_group_admin"),
                this.userService.hasGroup("dl_base.dl_group_accountant"),
            ]);
            this._dlGroupReadonly = isSM && !isAdmin && !isAcc;
            if (this._dlGroupReadonly) {
                this.canEdit = false;
                const aa = this.archInfo && this.archInfo.activeActions;
                if (aa) {
                    aa.edit = false;
                    aa.create = false;
                    aa.delete = false;
                    aa.duplicate = false;
                }
            }
        });

        setupStatusbarButtons(this);
        setupFormActionsMenu(this);

        onMounted(() => {
            const el = this.rootRef?.el;
            if (!el) {
                return;
            }
            const mark = () => {
                this._dlUserTouched = true;
            };
            el.addEventListener("input", mark, true);
            el.addEventListener("change", mark, true);
        });

        // Đổi bản ghi (pager / mở NCC khác) → reset cờ tương tác; và ép readonly
        // cho Trưởng KD (canEdit đã tính trong super.setup()).
        useEffect(
            () => {
                this._dlUserTouched = false;
                if (
                    this._dlGroupReadonly &&
                    this.model.root &&
                    this.model.root.isInEdition
                ) {
                    this.model.root.switchMode("readonly");
                }
            },
            () => [this.model.root.resId]
        );
    }

    // Form chỉ đọc: Trưởng KD, hoặc NCC đã ngừng hợp tác.
    get _dlReadonly() {
        return this._dlGroupReadonly || this.model.root.data.active === false;
    }

    // Bản ghi mới đã nhập/điền coi như có thay đổi; bản ghi cũ chỉ tính khi
    // người dùng thực sự chỉnh (tránh hỏi vô cớ do fill tự động).
    get _dlHasRealChanges() {
        return this.model.root.dirty && this._dlUserTouched;
    }

    // Bấm "Huỷ" → hỏi xác nhận trước khi bỏ thay đổi.
    async discard() {
        if (!this._dlReadonly && this._dlHasRealChanges) {
            const confirmed = await this._dlConfirm({
                title: _t("Huỷ thay đổi"),
                body: _t(
                    "Bạn có chắc muốn huỷ các thay đổi chưa lưu? Thông tin vừa nhập sẽ không được lưu."
                ),
                confirmLabel: _t("Huỷ thay đổi"),
                cancelLabel: _t("Tiếp tục chỉnh sửa"),
            });
            if (!confirmed) {
                return;
            }
        }
        return super.discard();
    }

    // Rời form: KHÔNG tự lưu. Không có thay đổi thật (hoặc chỉ đọc) → xả bỏ.
    // Có thay đổi thật → hỏi Lưu / Rời đi / Ở lại.
    async beforeLeave() {
        const root = this.model.root;
        if (this._dlReadonly || !this._dlHasRealChanges) {
            if (root.dirty) {
                await root.discard();
            }
            return;
        }
        const choice = await this._dlLeavePrompt();
        if (choice === "stay") {
            throw new Error("dl_supplier_leave_cancelled");
        }
        if (choice === "discard") {
            await root.discard();
            return;
        }
        // choice === "save": validate trước, không hợp lệ thì giữ lại để sửa.
        const message = this._dlValidateSupplier(root);
        if (message) {
            this.dlNotification.add(message, {
                type: "danger",
                title: _t("Kiểm tra lại thông tin"),
            });
            throw new Error("dl_supplier_invalid_on_leave");
        }
        // Chỉ lúc này mới gộp/tạo (create → merge).
        const saved = await root.save();
        if (!saved) {
            throw new Error("dl_supplier_save_failed_on_leave");
        }
    }

    // Chặn lưu + báo lỗi bằng toast nếu dữ liệu không hợp lệ.
    async saveButtonClicked(params = {}) {
        const message = this._dlValidateSupplier(this.model.root);
        if (message) {
            this.dlNotification.add(message, {
                type: "danger",
                title: _t("Kiểm tra lại thông tin"),
            });
            return false;
        }
        return super.saveButtonClicked(params);
    }

    // MST NCC không bắt buộc; nếu đã nhập thì phải đúng định dạng
    // (10 số hoặc 10 số-3 số cho chi nhánh). Đồng bộ với form Khách hàng.
    _dlValidateSupplier(record) {
        const tax = (record.data.vat || "").trim();
        if (tax && !TAX_CODE_RE.test(tax)) {
            return `Mã số thuế '${tax}' không đúng định dạng. MST gồm 10 chữ số (VD: 0123456789) hoặc 10 số-3 số cho chi nhánh (VD: 0123456789-001).`;
        }
        return null;
    }

    _dlConfirm({ title, body, confirmLabel, cancelLabel }) {
        return new Promise((resolve) => {
            this.dlDialog.add(
                ConfirmationDialog,
                {
                    title,
                    body,
                    confirmLabel,
                    cancelLabel,
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) }
            );
        });
    }

    _dlLeavePrompt() {
        return new Promise((resolve) => {
            this.dlDialog.add(
                ConfirmationDialog,
                {
                    title: _t("Thay đổi chưa lưu"),
                    body: _t("Bạn có thay đổi chưa được lưu. Bạn muốn làm gì?"),
                    confirmLabel: _t("Lưu"),
                    cancelLabel: _t("Rời đi, không lưu"),
                    confirm: () => resolve("save"),
                    cancel: () => resolve("discard"),
                },
                { onClose: () => resolve("stay") }
            );
        });
    }

    // Breadcrumb bản ghi mới: "New" → "Thêm nhà cung cấp".
    displayName() {
        if (this.model.root.isNew) {
            return _t("Thêm nhà cung cấp");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }
}

registry.category("views").add("dl_supplier_form", {
    ...formView,
    Controller: DlSupplierFormController,
});
