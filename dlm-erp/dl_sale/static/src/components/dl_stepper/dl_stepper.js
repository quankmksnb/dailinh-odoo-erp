/** @odoo-module **/
// ============================================================
//  DL Stepper — widget hiển thị trạng thái báo giá dạng bước
//  (Nháp → Đã gửi → Đã duyệt) theo thiết kế Figma.
//  Chỉ HIỂN THỊ field state sẵn có; không đổi model/workflow.
//  Dùng widget riêng để kiểm soát hoàn toàn DOM, tránh xung đột
//  với statusbar gốc của Odoo (vốn có dropdown/trạng thái gấp).
// ============================================================

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Các bước trên trục chính (rejected không nằm trong stepper)
const STEP_ORDER = ["draft", "sent", "approved"];
const STEP_LABELS = {
    draft: "Nháp",
    sent: "Đã gửi",
    approved: "Đã duyệt",
};

export class DlStepper extends Component {
    static template = "dl_sale.DlStepper";
    static props = { ...standardFieldProps };

    get steps() {
        const current = this.props.record.data[this.props.name];
        const curIdx = STEP_ORDER.indexOf(current);
        return STEP_ORDER.map((value, i) => ({
            key: value,
            label: STEP_LABELS[value],
            index: i + 1,
            done: curIdx !== -1 && curIdx > i,
            current: value === current,
        }));
    }
}

export const dlStepper = {
    component: DlStepper,
    supportedTypes: ["selection"],
};

registry.category("fields").add("dl_stepper", dlStepper);
