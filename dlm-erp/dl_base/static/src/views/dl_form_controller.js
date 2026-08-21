/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "../js/actions_menu";

// Form controller dùng chung: dời cụm nút statusbar LÊN góc trên-phải (cạnh
// breadcrumb) và để dải trạng thái (dl_stepper) một mình bên trái — đúng bố cục
// các màn Báo giá / Đơn bán / BOM đã làm. Trước đây mỗi form tự viết một
// controller y hệt chỉ để gọi đúng hai hàm này (saleorder/drawing/bom/rfq…);
// bản dùng chung để form nào cần chỉ khai js_class="dl_form", không đẻ thêm file.
//
// KHÔNG override displayName ở đây: đó là phần tuỳ biến riêng của từng màn
// (tiêu đề "Thêm …" khi tạo mới). Form nào cần tiêu đề riêng thì vẫn viết
// controller riêng như cũ; bản chung này chỉ lo VỊ TRÍ nút/trạng thái.
export class DlFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }
}

registry.category("views").add("dl_form", {
    ...formView,
    Controller: DlFormController,
});
