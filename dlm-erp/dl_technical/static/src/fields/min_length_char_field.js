/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useState } from "@odoo/owl";

// ─────────────────────────────────────────────────────────────────────────────
// Ô chữ có độ dài tối thiểu, báo NGAY KHI GÕ.
//
// Vì sao cần: ràng buộc độ dài nằm ở @api.constrains phía server, mà server chỉ
// được hỏi lúc bấm Lưu. Người dùng gõ tên một ký tự, điền tiếp cả form, bấm Lưu
// rồi mới biết sai — phải quay lại tìm đúng dòng đó. Widget này đẩy phản hồi lên
// ngay ô nhập.
//
// Backend VẪN chốt lại (_check_product_name_length): widget chỉ là lớp trải
// nghiệm, mọi đường ghi khác (import, RPC, code) không đi qua đây.
//
// Cùng cách làm với dl_partner/static/src/fields/tax_code_field.js.
//
// Dùng trong view:
//     <field name="product_name" widget="dl_min_length_char"
//            options="{'min_length': 2}"/>
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_MIN_LENGTH = 2;

export class DlMinLengthCharField extends CharField {
    static template = "dl_technical.DlMinLengthCharField";
    static props = {
        ...CharField.props,
        minLength: { type: Number, optional: true },
    };

    setup() {
        super.setup();
        this.ui = useState({ tooShort: false });
        this._syncValidity(this.props.record.data[this.props.name]);
    }

    get minLength() {
        return this.props.minLength || DEFAULT_MIN_LENGTH;
    }

    get message() {
        return `Cần ít nhất ${this.minLength} ký tự.`;
    }

    /** Ô rỗng KHÔNG tính là quá ngắn — "bắt buộc nhập" là luật khác, do
     *  required của view lo. Ở đây chỉ nói về độ dài của thứ đã gõ. */
    _isTooShort(value) {
        const text = (value || "").trim();
        return text.length > 0 && text.length < this.minLength;
    }

    /** Đánh dấu field invalid theo API chính chủ của Odoo (record.js) thay vì
     *  tự chế: nhờ vậy nút Lưu chặn lại và báo bằng toast "Trường không hợp lệ"
     *  của Odoo, không bung hộp thoại lỗi lưu form. */
    _syncValidity(value) {
        const tooShort = this._isTooShort(value);
        this.ui.tooShort = tooShort;
        const record = this.props.record;
        if (tooShort) {
            record.setInvalidField(this.props.name);
        } else {
            record.resetFieldValidity(this.props.name);
        }
    }

    onInput(ev) {
        this._syncValidity(ev.target.value);
    }
}

export const dlMinLengthCharField = {
    ...charField,
    component: DlMinLengthCharField,
    supportedOptions: [
        ...(charField.supportedOptions || []),
        {
            label: "Độ dài tối thiểu",
            name: "min_length",
            type: "number",
        },
    ],
    extractProps({ attrs, options }, dynamicInfo) {
        return {
            ...charField.extractProps({ attrs, options }, dynamicInfo),
            minLength: options.min_length,
        };
    },
};

registry.category("fields").add("dl_min_length_char", dlMinLengthCharField);
