/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";
import { formatFloat } from "@web/views/fields/formatters";

// ─────────────────────────────────────────────────────────────────────────────
// Widget SỐ LƯỢNG dùng chung — cắt đuôi số 0 thừa khi hiển thị.
//
// Độ chính xác "Product Unit of Measure" để 4 chữ số (dl_product/data/uom_data.xml)
// vì định mức BOM chia theo cây thép 6m sẽ bị bóp méo nếu chỉ 2 chữ số. Cái giá
// phải trả là MỌI ô số lượng đều hiện "6.000,0000" — 4 số 0 không nói thêm điều
// gì mà làm bảng phiếu kho rối mắt.
//
// Chỉ đổi CÁCH HIỆN, không đụng giá trị lưu lẫn phép tính, và KHÔNG làm tròn:
//   6000     → "6.000"      (trước: "6.000,0000")
//   12.5     → "12,5"       (trước: "12,5000")
//   0.0625   → "0,0625"     (giữ nguyên — phần lẻ có nghĩa thì vẫn hiện đủ)
// Khác hẳn cách đặt digits="[16, 0]": digits sẽ LÀM TRÒN 12,5 thành "13".
// ─────────────────────────────────────────────────────────────────────────────

export class DlQtyField extends FloatField {
    get formattedValue() {
        // Các chế độ đặc biệt của FloatField (không format / input số / rút gọn
        // kiểu "500G") giữ nguyên hành vi gốc — đuôi số 0 không phải chuyện ở đó.
        if (
            !this.props.formatNumber ||
            this.props.humanReadable ||
            this.props.inputType === "number"
        ) {
            return super.formattedValue;
        }
        return formatFloat(this.value, { digits: this.digits, trailingZeros: false });
    }
}

export const dlQtyField = {
    ...floatField,
    component: DlQtyField,
};

registry.category("fields").add("dl_qty", dlQtyField);
