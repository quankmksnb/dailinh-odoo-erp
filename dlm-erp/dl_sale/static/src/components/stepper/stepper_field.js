/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// rejected / cancelled không nằm trên trục stepper
const STEP_ORDER = ["draft", "approved", "sent", "accepted", "ordered"];
const STEP_LABELS = {
    draft: "Nháp",
    approved: "Duyệt nội bộ",
    sent: "Đã gửi khách",
    accepted: "Khách đồng ý",
    ordered: "Đã lên đơn",
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
