/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { onMounted, useEffect } from "@odoo/owl";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

const PHONE_RE = /^(0|\+84)[0-9]{9,10}$/;
const EMAIL_RE = /^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$/;
// PHẢI khớp _TAX_CODE_RE ở backend (res_partner.py) và widget dl_tax_code.
const TAX_CODE_RE = /^\d{10}(-\d{3})?$/;

export class DlCustomerFormController extends FormController {
    setup() {
        super.setup();
        this.dlNotification = useService("notification");
        this.dlOrm = useService("orm");
        this.dlDialog = useService("dialog");
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
        this._dlUserTouched = false;
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
        // Đổi bản ghi (pager / mở KH khác) → reset
        useEffect(
            () => {
                this._dlUserTouched = false;
            },
            () => [this.model.root.resId]
        );
    }

    // KH đã vô hiệu hóa → form chỉ đọc, không có gì để lưu.
    get _dlReadonly() {
        return this.model.root.data.active === false;
    }

    // Bản ghi mới đã nhập/điền (kể cả fill tự động từ onchange tìm–liên kết)
    // coi như có thay đổi → hỏi trước khi rời. Bản ghi cũ chỉ tính khi người
    // dùng thực sự chỉnh (tránh hỏi vô cớ).
    get _dlHasRealChanges() {
        return this.model.root.dirty && this._dlUserTouched;
    }

    // Hỏi xác nhận khi bấm "Huỷ" (bỏ thay đổi)
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

    // Cảnh báo khi rời trang còn thay đổi chưa lưu
    async beforeLeave() {
        const root = this.model.root;
        if (this._dlReadonly) {
            if (root.dirty) {
                await root.discard();
            }
            return;
        }

        if (!this._dlHasRealChanges) {
            if (root.dirty) {
                await root.discard();
            }
            return;
        }
        const choice = await this._dlLeavePrompt();
        if (choice === "stay") {
            throw new Error("dl_customer_leave_cancelled");
        }
        if (choice === "discard") {
            await root.discard();
            return;
        }
        // choice === "save": validate trước, không hợp lệ thì giữ lại để sửa.
        const message = await this._dlValidateCustomer(root);
        if (message) {
            this.dlNotification.add(message, {
                type: "danger",
                title: _t("Kiểm tra lại thông tin"),
            });
            throw new Error("dl_customer_invalid_on_leave");
        }
        const saved = await root.save();
        if (!saved) {
            throw new Error("dl_customer_save_failed_on_leave");
        }
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

    displayName() {
        if (this.model.root.isNew) {
            return _t("Thêm khách hàng");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }

    // Chặn lưu + báo lỗi bằng toast nếu dữ liệu không hợp lệ.
    async saveButtonClicked(params = {}) {
        const message = await this._dlValidateCustomer(this.model.root);
        if (message) {
            this.dlNotification.add(message, {
                type: "danger",
                title: _t("Kiểm tra lại thông tin"),
            });
            return false;
        }
        return super.saveButtonClicked(params);
    }

    async _dlValidateCustomer(record) {
        const d = record.data;
        if (!["customer", "both"].includes(d.partner_role)) {
            return null;
        }

        // Loại khách hàng bắt buộc.
        if (!d.partner_type) {
            return _t("Khách hàng phải có Loại khách hàng.");
        }

        // MST bắt buộc với khách Doanh nghiệp.
        const tax = (d.vat || "").trim();
        if (d.partner_type === "company" && !tax) {
            return _t("Khách hàng Doanh nghiệp bắt buộc phải có Mã số thuế (MST).");
        }

        // MST nếu đã nhập phải đúng định dạng (10 số hoặc 10 số-3 số cho chi nhánh).
        if (tax && !TAX_CODE_RE.test(tax)) {
            return `Mã số thuế '${tax}' không đúng định dạng. MST gồm 10 chữ số (VD: 0123456789) hoặc 10 số-3 số cho chi nhánh (VD: 0123456789-001).`;
        }

        // Điện thoại / Di động theo định dạng VN
        for (const [label, value] of [
            ["Điện thoại", d.phone],
            ["Di động", d.mobile],
        ]) {
            if (value && !PHONE_RE.test(String(value).replace(/[\s.\-]/g, ""))) {
                return `${label} '${value}' không hợp lệ. Số điện thoại Việt Nam phải bắt đầu bằng 0 hoặc +84 và gồm 10–11 chữ số.`;
            }
        }

        // Email.
        if (d.email && !EMAIL_RE.test(String(d.email).trim())) {
            return `Email '${d.email}' không hợp lệ.`;
        }

        // Người liên hệ: SĐT/email (nếu nhập) phải đúng định dạng — chặn sớm
        // bằng toast thay vì để backend bung hộp thoại. Backend vẫn chốt lại.
        const contacts = d.child_ids?.records || [];
        for (const contact of contacts) {
            const cd = contact.data || {};
            const cname = (cd.name || "").trim() || "(chưa đặt tên)";
            for (const [label, value] of [
                ["Điện thoại", cd.phone],
                ["Di động", cd.mobile],
            ]) {
                if (value && !PHONE_RE.test(String(value).replace(/[\s.\-]/g, ""))) {
                    return `Người liên hệ '${cname}': ${label} '${value}' không hợp lệ. Số điện thoại Việt Nam phải bắt đầu bằng 0 hoặc +84 và gồm 10–11 chữ số.`;
                }
            }
            if (cd.email && !EMAIL_RE.test(String(cd.email).trim())) {
                return `Người liên hệ '${cname}': Email '${cd.email}' không hợp lệ.`;
            }
        }

        // Trùng MST — trừ khi đánh dấu chi nhánh khác dùng chung MST
        if (tax && !d.dlm_allow_dup_tax) {
            const dup = await this.dlOrm.searchRead(
                "res.partner",
                [
                    ["id", "!=", record.resId || 0],
                    ["partner_role", "in", ["customer", "both"]],
                    ["vat", "=", tax],
                ],
                ["name", "dlm_code"],
                { limit: 1, context: { active_test: false } }
            );
            if (dup.length) {
                const ref = dup[0].dlm_code ? " — " + dup[0].dlm_code : "";
                return `MST '${tax}' đã tồn tại trong hệ thống (KH: ${dup[0].name}${ref}). Nếu đây là chi nhánh khác dùng chung MST, hãy tích 'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do.`;
            }
        }

        return null;
    }
}

registry.category("views").add("dl_customer_form", {
    ...formView,
    Controller: DlCustomerFormController,
});
