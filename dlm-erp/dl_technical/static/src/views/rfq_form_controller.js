/** @odoo-module **/
// ============================================================
//  DL RFQ Form — đồng bộ chrome form Yêu cầu báo giá (D1).
// ============================================================

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setupFormActionsMenu, setupStatusbarButtons } from "@dl_base/js/actions_menu";

// Các field bảng dòng RFQ có thể xuất hiện trên form (tùy view):
//  - form xử lý: line_ids (1 bảng)
//  - form Tạo RFQ (Sales): trading_line_ids + manufactured_line_ids (2 bảng)
const DL_LINE_FIELDS = ["line_ids", "trading_line_ids", "manufactured_line_ids"];

export class DlRfqFormController extends FormController {
    setup() {
        super.setup();
        setupStatusbarButtons(this);
        setupFormActionsMenu(this);
    }

    displayName() {
        if (this.model.root.isNew) {
            return _t("Thêm yêu cầu báo giá");
        }
        return this.model.root.data.display_name?.split("\n")[0] || "";
    }

    // Validate INLINE "RFQ phải có ≥1 dòng sản phẩm": đánh dấu field bảng dòng là
    // invalid (tô đỏ) để record.save() gom vào TOAST "Trường không hợp lệ" chung
    // với customer_id — cùng một cơ chế, KHÔNG modal. Phải tự làm vì `required`
    // native trên one2many (kể cả biểu thức động cross-required) không kích hoạt
    // ổn định ở form này. record.save() vẫn tự lo hiển thị toast + focus lỗi đầu.
    async _dlMarkLinePresence(record) {
        const data = record.data;
        // Chỉ xét field bảng dòng thực sự có trên view hiện tại.
        const present = DL_LINE_FIELDS.filter((f) => f in data && data[f]);
        if (!present.length) {
            return; // không có bảng dòng nào → không phải form RFQ có dòng
        }
        // Đếm tổng dòng: ưu tiên line_ids (form xử lý), nếu không thì cộng 2 bảng
        // tách (form Tạo RFQ) — trading/manufactured là tập con rời nhau của line_ids.
        let total;
        if ("line_ids" in data && data.line_ids) {
            total = data.line_ids.count;
        } else {
            total = present.reduce((n, f) => n + data[f].count, 0);
        }
        for (const f of present) {
            if (total === 0) {
                await record.setInvalidField(f);
            } else {
                record.resetFieldValidity(f);
            }
        }
    }

    async save(params = {}) {
        const record = this.model.root;
        // RFQ đã hủy được miễn (giữ hành vi cũ của _check_has_lines).
        if (record.data.status !== "cancelled") {
            await this._dlMarkLinePresence(record);
        }
        return super.save(params);
    }
}

registry.category("views").add("dl_rfq_form", {
    ...formView,
    Controller: DlRfqFormController,
});
