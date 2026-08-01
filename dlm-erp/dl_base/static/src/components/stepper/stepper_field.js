/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Trục chính 5 bước của báo giá.
const STEP_ORDER = ["draft", "approved", "sent", "accepted", "ordered"];
const STEP_LABELS = {
    draft: "Nháp",
    approved: "Duyệt nội bộ",
    sent: "Đã gửi khách",
    accepted: "Khách đồng ý",
    ordered: "Đã lên đơn",
};

// Trạng thái NHÁNH (ngoài trục chính) — hiển thị bằng nhãn màu riêng ở cuối, kèm
// mốc trên trục mà nó rẽ ra ("after") để người dùng biết báo giá đã đi tới đâu.
const BRANCH = {
    revision_requested: { label: "Yêu cầu điều chỉnh", kind: "warn", after: "sent" },
    expired: { label: "Hết hiệu lực", kind: "warn", after: "sent" },
    rejected: { label: "Từ chối", kind: "danger", after: null },
    superseded: { label: "Đã thay bản mới", kind: "muted", after: null },
    cancelled: { label: "Đã hủy", kind: "muted", after: null },
};

export class DlStepper extends Component {
    static template = "dl_sale.DlStepper";
    static props = { ...standardFieldProps };

    get currentState() {
        return this.props.record.data[this.props.name];
    }

    get branch() {
        return BRANCH[this.currentState] || null;
    }

    get steps() {
        const current = this.currentState;
        const branch = BRANCH[current];
        if (branch) {
            // Nhánh: chỉ hiển thị các bước đã đi qua (tính tới mốc rẽ), tất cả
            // đánh dấu hoàn thành; nhãn nhánh render riêng ở template.
            const reachedIdx = branch.after ? STEP_ORDER.indexOf(branch.after) : -1;
            return STEP_ORDER.slice(0, reachedIdx + 1).map((value, i) => ({
                key: value,
                label: STEP_LABELS[value],
                index: i + 1,
                done: true,
                current: false,
            }));
        }
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
