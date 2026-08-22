/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DlMoneyField, dlMoneyField } from "@dl_base/components/money/money_field";

// Ô "Giá mua" của Bảng giá NCC: đọc thì xếp 2 dòng — giá là dòng chính, đơn vị
// ("/ Cây") là dòng phụ ngay dưới. Nhờ vậy gộp được cột Đơn vị vào cột Giá,
// bớt một cột và cho cột Vật tư/NCC rộng ra. Lúc SỬA vẫn là ô nhập tiền
// group-hàng-nghìn của dl_money (kế thừa nguyên), nên list editable không vỡ.
export class DlSupplierPriceField extends DlMoneyField {
    static template = "dl_product.DlSupplierPriceField";

    // Nhãn đơn vị lấy từ field product_uom cùng dòng (m2o → [id, "Cây"]).
    get uomLabel() {
        const uom = this.props.record.data.product_uom;
        return uom ? uom[1] : "";
    }
}

registry.category("fields").add("dl_supplier_price", {
    ...dlMoneyField,
    component: DlSupplierPriceField,
    // PHẢI khai ở đây chứ không phải bằng <field column_invisible="1"> trong arch:
    // với many2one, Odoo chỉ xin display_name khi field KHÔNG invisible
    // (relational_model/utils.js getFieldsSpec) — field ẩn chỉ về mỗi id, nên tên
    // đơn vị ra rỗng. Khai kiểu này thì display_name được nạp mà cột vẫn không hiện.
    fieldDependencies: [
        { name: "product_uom", type: "many2one", relation: "uom.uom", readonly: true },
    ],
});
