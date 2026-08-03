/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";
import { regroupMoneyInput } from "../../js/money_format";

// ─────────────────────────────────────────────────────────────────────────────
// Widget tiền DÙNG CHUNG cho mọi field tiền dl.* — gõ tới đâu tự chèn dấu phân
// tách hàng nghìn tới đó (mỗi 3 số 1 dấu ".", theo ngôn ngữ vi_VN).
//
// Kế thừa FloatField của Odoo để giữ nguyên: parse theo lang (parseFloat bỏ dấu
// "." phân tách), hiển thị đọc-đã-group, readonly, digits… Chỉ thêm:
//   • t-on-input="onMoneyInput" → group LIVE ngay khi gõ (template riêng).
//   • mặc định 0 phần thập phân (VNĐ) khi field không khai báo digits.
//
// Dùng được cho cả field kiểu `monetary` lẫn `float`/`integer` (xem
// supportedTypes) — chỉ cần đổi widget="monetary" → widget="dl_money".
// ─────────────────────────────────────────────────────────────────────────────

export class DlMoneyField extends FloatField {
    static template = "dl_base.DlMoneyField";

    onMoneyInput(ev) {
        regroupMoneyInput(ev.target);
    }

    // VNĐ là số nguyên: nếu field không tự khai báo digits thì ép 0 phần thập
    // phân (tránh hiển thị ",00" cho field monetary theo tiền tệ).
    get digits() {
        const d = super.digits;
        return Array.isArray(d) ? d : [16, 0];
    }
}

export const dlMoneyField = {
    ...floatField,
    component: DlMoneyField,
    // Cho phép gắn lên field tiền dù khai báo là monetary, float hay integer.
    supportedTypes: ["float", "monetary", "integer"],
};

registry.category("fields").add("dl_money", dlMoneyField);
