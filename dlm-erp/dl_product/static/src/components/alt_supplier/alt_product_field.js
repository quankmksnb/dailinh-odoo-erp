/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";

// Ô "Vật tư" trên list Bảng giá NCC. Dòng phụ (thụt vào dưới giá đang áp dụng)
// thuộc về vật tư của dòng ngay trên, nên in lại tên vật tư ở đây chỉ tổ rối:
// thay bằng nhãn nói rõ vai trò của dòng. Nhãn do server tính
// (`dlm_alt_label`) vì nó phụ thuộc nhà cung cấp của dòng đang áp dụng — thứ
// không có trong dữ liệu của riêng dòng này. Chỉ đổi phần ĐỌC — lúc sửa vẫn là
// ô chọn many2one gốc, nên list editable không vỡ.
export class DlAltProductField extends Many2OneField {
    get displayName() {
        return this.props.record.data.dlm_alt_label || super.displayName;
    }

    // Tên vật tư nhiều dòng bị cắt xuống extraLines — dòng phụ không cần.
    get extraLines() {
        return this.props.record.data.dlm_alt_label ? [] : super.extraLines;
    }
}

registry.category("fields").add("dl_alt_product", {
    ...many2OneField,
    component: DlAltProductField,
});
