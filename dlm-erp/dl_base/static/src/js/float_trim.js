/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { FloatField } from "@web/views/fields/float/float_field";
import { formatFloat } from "@web/views/fields/formatters";

// ─────────────────────────────────────────────────────────────────────────────
// Cắt đuôi số 0 thừa cho MỌI số thập phân trong hệ thống.
//
// Số ở đây gần như luôn là số nguyên (số lượng cây thép, tiền VNĐ, % chiết
// khấu), nhưng field khai digits 2 chữ số nên Odoo hiện "424.000,00 ₫",
// "0,00 %", "30,00" — phần ",00" không nói thêm điều gì mà làm bảng biểu rối
// mắt. Chỉ đổi CÁCH HIỆN, KHÔNG làm tròn và không đụng giá trị lưu:
//   424000   → "424.000"   (trước: "424.000,00")
//   30.5     → "30,5"      (trước: "30,50")
//   0.0625   → "0,0625"    (giữ nguyên — phần lẻ có nghĩa thì hiện đủ)
// Khác hẳn digits="[16, 0]": digits sẽ LÀM TRÒN 30,5 thành "31".
//
// Vá ở hai chỗ vì Odoo hiện số qua hai đường khác nhau:
//   • FloatField — ô field trên form và trong list (kể cả dl_money, dl_qty,
//     dl_supplier_price vì chúng đều kế thừa FloatField).
//   • formatter "float" của registry — dòng TỔNG cuối list (sum=) không dựng
//     component field mà gọi thẳng formatter (list_renderer.js `aggregates`).
// ─────────────────────────────────────────────────────────────────────────────

patch(FloatField.prototype, {
    get formattedValue() {
        // Các chế độ đặc biệt (không format / ô input số / rút gọn kiểu "500G")
        // giữ nguyên hành vi gốc — đuôi số 0 không phải chuyện ở đó.
        if (
            !this.props.formatNumber ||
            (this.props.inputType === "number" && !this.props.readonly && this.value) ||
            (this.props.humanReadable && !this.state.hasFocus)
        ) {
            return super.formattedValue;
        }
        return formatFloat(this.value, { digits: this.digits, trailingZeros: false });
    },
});

registry.category("formatters").add(
    "float",
    (value, options = {}) => formatFloat(value, { ...options, trailingZeros: false }),
    { force: true }
);
