/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";

// Ô "Vật tư" trên list Bảng giá NCC. Dòng phương án khác (dlm_is_alternative)
// thuộc về vật tư của dòng ngay trên, nên in lại tên vật tư ở đây chỉ tổ rối:
// thay bằng một nhãn ngắn nói rõ vai trò của dòng. Chỉ đổi phần ĐỌC — lúc sửa
// vẫn là ô chọn many2one gốc, nên list editable không vỡ.
export class DlAltProductField extends Many2OneField {
    get displayName() {
        if (this.props.record.data.dlm_is_alternative) {
            return "Nhà cung cấp khác";
        }
        return super.displayName;
    }

    // Tên vật tư nhiều dòng bị cắt xuống extraLines — dòng phụ không cần.
    get extraLines() {
        return this.props.record.data.dlm_is_alternative ? [] : super.extraLines;
    }
}

registry.category("fields").add("dl_alt_product", {
    ...many2OneField,
    component: DlAltProductField,
});
