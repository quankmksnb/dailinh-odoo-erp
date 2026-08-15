/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

// Widget ô Mã số thuế trên form Khách hàng: chỉ cho gõ chữ số và dấu '-'.
// Kiểm định dạng do customer_form_controller.js và backend lo, không báo lỗi ở đây.

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
