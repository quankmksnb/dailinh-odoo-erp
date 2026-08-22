/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";

// ─────────────────────────────────────────────────────────────────────────────
// Widget SỐ LƯỢNG dùng chung — đánh dấu "ô này là SỐ LƯỢNG, không phải tiền"
// (đối trọng của dl_money: không ký hiệu ₫, không ép 0 phần thập phân).
//
// Việc cắt đuôi số 0 thừa nay do dl_base/static/src/js/float_trim.js lo cho MỌI
// field số, nên ở đây không cần override cách hiện nữa. Vẫn giữ tên widget vì
// ~40 view đang dùng và nó nói rõ ý đồ ngay tại chỗ khai báo.
//
// Độ chính xác "Product Unit of Measure" để 4 chữ số (dl_product/data/uom_data.xml)
// vì định mức BOM chia theo cây thép 6m sẽ bị bóp méo nếu chỉ 2 chữ số — KHÔNG
// hạ bằng digits="[16, 0]" vì digits LÀM TRÒN 12,5 thành "13".
// ─────────────────────────────────────────────────────────────────────────────

export class DlQtyField extends FloatField {}

export const dlQtyField = {
    ...floatField,
    component: DlQtyField,
};

registry.category("fields").add("dl_qty", dlQtyField);
