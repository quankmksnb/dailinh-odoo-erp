/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// ─────────────────────────────────────────────────────────────────────────────
// Stepper trạng thái DÙNG CHUNG cho mọi form dl.* — thay thanh statusbar mặc
// định bằng dải bước tròn ✓ (xanh lá = đã qua, xanh dương = đang ở, xám = chưa
// tới), kèm nhãn pill cho trạng thái NHÁNH (ngoài trục chính: hủy/từ chối/…).
//
// Trục chính lấy từ `statusbar_visible` của view (nếu thiếu → toàn bộ selection);
// nhãn lấy thẳng từ selection của field nên không phải khai báo lại. Trạng thái
// không nằm trên trục = nhánh: màu suy ra theo từ khóa, có thể ghi đè bằng
// options="{'branches': {'ma_trang_thai': {'kind': 'warn', 'after': 'moc'}}}".
//
// Preset "quotation" giữ nguyên cấu hình cũ của form Báo giá (nhãn rút gọn +
// mốc rẽ nhánh `after`) để KHÔNG đổi giao diện màn đã chốt.
// ─────────────────────────────────────────────────────────────────────────────

// Suy ra "tính chất" nhánh theo từ khóa mã trạng thái → màu pill.
const BRANCH_KIND_BY_KEY = {
    cancelled: "muted",
    canceled: "muted",
    superseded: "muted",
    obsolete: "muted",
    rejected: "danger",
    refused: "danger",
    infeasible: "danger",
    returned: "warn",
    supplemented: "warn",
    expired: "warn",
    revision_requested: "warn",
};

function branchKind(key) {
    return BRANCH_KIND_BY_KEY[key] || "warn";
}

// Preset riêng cho form Báo giá — trục + nhãn rút gọn + mốc rẽ nhánh.
const QUOTATION_AXIS = ["draft", "approved", "sent", "accepted", "ordered"];
const QUOTATION_LABELS = {
    draft: "Nháp",
    approved: "Duyệt nội bộ",
    sent: "Đã gửi khách",
    accepted: "Khách đồng ý",
    ordered: "Đã lên đơn",
};
const QUOTATION_BRANCHES = {
    revision_requested: { kind: "warn", after: "sent" },
    expired: { kind: "warn", after: "sent" },
    rejected: { kind: "danger", after: null },
    superseded: { kind: "muted", after: null },
    cancelled: { kind: "muted", after: null },
};

export class DlStepper extends Component {
    static template = "dl_base.DlStepper";
    static props = {
        ...standardFieldProps,
        axis: { type: Array, element: String, optional: true },
        branches: { type: Object, optional: true },
        labels: { type: Object, optional: true },
        preset: { type: String, optional: true },
    };

    get currentState() {
        return this.props.record.data[this.props.name];
    }

    // Danh sách [value, label] theo đúng thứ tự khai báo của selection.
    get selection() {
        return this.props.record.fields[this.props.name].selection || [];
    }

    // Cấu hình đã "giải": { axis: [...], labels: {value: label}, branches: {value: {kind, after}} }.
    get config() {
        const labels = {};
        for (const [value, label] of this.selection) {
            labels[value] = label;
        }
        // Nhãn riêng theo từng màn: selection của Odoo nói ngôn ngữ của Odoo
        // ("Sẵn sàng", "Hoàn tất"), không phải ngôn ngữ của xưởng. Trên phiếu
        // nhận, "Hoàn tất" khiến thủ kho tưởng xong cả việc kiểm.
        Object.assign(labels, this.props.labels || {});

        // Preset Báo giá — giữ nguyên giao diện cũ (nhãn rút gọn + mốc rẽ nhánh).
        if (this.props.preset === "quotation") {
            return {
                axis: QUOTATION_AXIS,
                labels: { ...labels, ...QUOTATION_LABELS, ...(this.props.labels || {}) },
                branches: QUOTATION_BRANCHES,
            };
        }

        // Chung: trục = statusbar_visible (nếu có) hoặc toàn bộ selection.
        const allValues = this.selection.map(([value]) => value);
        const axis = this.props.axis?.length ? this.props.axis : allValues;
        const axisSet = new Set(axis);

        // Nhánh = mọi trạng thái ngoài trục. Nhánh "warn" (còn quay lại trục
        // được) nối vào mốc là axis-member gần nhất ĐỨNG TRƯỚC nó trong thứ tự
        // selection; nhánh kết thúc tiêu cực (muted/danger) hiển thị pill trơn.
        const branches = {};
        for (const [value] of this.selection) {
            if (axisSet.has(value)) {
                continue;
            }
            const override = this.props.branches?.[value] || {};
            const kind = override.kind || branchKind(value);
            let after = "after" in override ? override.after : null;
            if (after === null && kind === "warn") {
                let prevAxis = null;
                for (const [v] of this.selection) {
                    if (v === value) {
                        break;
                    }
                    if (axisSet.has(v)) {
                        prevAxis = v;
                    }
                }
                after = prevAxis;
            }
            branches[value] = { kind, after };
        }
        return { axis, labels, branches };
    }

    get branch() {
        const cfg = this.config;
        const b = cfg.branches[this.currentState];
        if (!b) {
            return null;
        }
        return { ...b, label: cfg.labels[this.currentState] || this.currentState };
    }

    get steps() {
        const cfg = this.config;
        const current = this.currentState;
        const b = cfg.branches[current];
        if (b) {
            // Nhánh: hiển thị các bước đã đi qua (tới mốc rẽ), tất cả đánh dấu
            // hoàn thành; nhãn nhánh render riêng ở template.
            const reachedIdx = b.after ? cfg.axis.indexOf(b.after) : -1;
            return cfg.axis.slice(0, reachedIdx + 1).map((value, i) => ({
                key: value,
                label: cfg.labels[value] || value,
                index: i + 1,
                done: true,
                current: false,
            }));
        }
        const curIdx = cfg.axis.indexOf(current);
        return cfg.axis.map((value, i) => ({
            key: value,
            label: cfg.labels[value] || value,
            index: i + 1,
            done: curIdx !== -1 && curIdx > i,
            current: value === current,
        }));
    }
}

export const dlStepper = {
    component: DlStepper,
    supportedTypes: ["selection"],
    extractProps: ({ attrs, options }) => ({
        axis: attrs.statusbar_visible?.trim().split(/\s*,\s*/g),
        branches: options.branches,
        labels: options.labels,
        preset: options.preset,
    }),
};

registry.category("fields").add("dl_stepper", dlStepper);
