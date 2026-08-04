/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

// ─────────────────────────────────────────────────────────────────────────────
// Widget nhập Mã số thuế (MST) — dùng cho field `vat` trên form Khách hàng.
//
// Kế thừa CharField của Odoo, chỉ giữ lớp lọc phím LIVE: chỉ cho gõ chữ số và
// dấu '-', ký tự khác bị loại ngay.
//
// Kiểm tra ĐỊNH DẠNG do controller lo (dl_sale/customer_form_controller.js —
// _dlValidateCustomer): sai định dạng ⇒ toast gọn góc phải "Kiểm tra lại thông
// tin" như các lỗi bắt buộc/điện thoại/email khác, KHÔNG ném lỗi ở đây (tránh
// đường "Trường không hợp lệ" cứng của Odoo hay bung hộp thoại backend). Backend
// vẫn chốt lại ở res_partner.py — _check_tax_code_format.
// ─────────────────────────────────────────────────────────────────────────────

const DISALLOWED_RE = /[^0-9-]/g;

export class DlTaxCodeField extends CharField {
    static template = "dl_partner.DlTaxCodeField";

    // Lọc ký tự ngay khi gõ: chỉ giữ chữ số và dấu '-'.
    onInput(ev) {
        const input = ev.target;
        const cleaned = input.value.replace(DISALLOWED_RE, "");
        if (cleaned !== input.value) {
            const dropped = input.value.length - cleaned.length;
            const pos = Math.max(0, (input.selectionStart || 0) - dropped);
            input.value = cleaned;
            input.setSelectionRange?.(pos, pos);
        }
    }
}

export const dlTaxCodeField = {
    ...charField,
    component: DlTaxCodeField,
};

registry.category("fields").add("dl_tax_code", dlTaxCodeField);
