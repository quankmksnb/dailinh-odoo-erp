/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ============================================================================
//  Cấu hình Báo giá (đặc tả V3) — màn OWL nhiều tab, đồng bộ style với S02.
//  Mỗi tab thao tác trên MỘT model quy tắc độc lập qua ORM thật (không mock):
//  Hao hụt · Công đoạn · Chi phí chung/hệ số · Lợi nhuận & Chiết khấu · Phê duyệt
//  · Danh mục. Kỹ thuật/kế toán áp dụng ngay; thương mại bắt buộc gửi duyệt.
// ============================================================================

const TABS = [
    { key: "waste", label: "Hao hụt & thu hồi", icon: "fa-scissors" },
    { key: "operation", label: "Chi phí công đoạn", icon: "fa-wrench" },
    { key: "cost", label: "Chi phí chung & hệ số", icon: "fa-cubes" },
    { key: "commercial", label: "Lợi nhuận & chiết khấu", icon: "fa-line-chart" },
    { key: "approval", label: "Phê duyệt", icon: "fa-check-square-o" },
    { key: "master", label: "Danh mục", icon: "fa-sliders" },
];

const M = {
    waste: "dl.pricing.waste.rule",
    operation: "dl.pricing.operation.rule",
    cost: "dl.pricing.cost.adjustment.rule",
    profit: "dl.pricing.profit.rule",
    discount: "dl.pricing.discount.rule",
    approval: "dl.pricing.approval.request",
    apprset: "dl.pricing.approval.setting",
    complexity: "dl.pricing.complexity.level",
    opcat: "dl.pricing.operation",
};

const STATE_LABEL = {
    draft: "Nháp", active: "Đang áp dụng", expired: "Hết hiệu lực",
    pending: "Chờ duyệt", rejected: "Từ chối", approved: "Đã duyệt",
};
const STATE_CLS = {
    draft: "is-draft", active: "is-active", expired: "is-expired",
    pending: "is-pending", rejected: "is-rejected", approved: "is-active",
};

const L = {
    wasteTarget: { category: "Theo category", product: "Theo vật tư" },
    opMethod: {
        percent_material: "% vật liệu liên quan", per_kg: "Theo kg",
        per_meter: "Theo mét", per_sqm: "Theo m²", per_unit: "Theo sản phẩm",
        per_batch: "Cố định theo lô",
    },
    costType: {
        workshop_overhead: "Chi phí chung xưởng", packing: "Đóng gói",
        shipping: "Vận chuyển", small_order: "Đơn hàng nhỏ", urgent: "Giao gấp",
        complexity: "Độ phức tạp gia công", contingency: "Dự phòng/rủi ro",
        other: "Chi phí khác",
    },
    costMethod: {
        percent_direct: "% chi phí trực tiếp", percent_cost: "% giá thành",
        per_unit: "đồng/sản phẩm", per_batch: "đồng/lô", fixed: "Tiền cố định",
        factor: "Hệ số nhân",
    },
    customerGroup: { new: "Khách mới", existing: "Khách cũ", potential: "Khách tiềm năng" },
    approvalType: {
        profit_config: "Cấu hình lợi nhuận mới", discount_config: "Cấu hình chiết khấu mới",
        quote_discount: "Chiết khấu báo giá vượt mặc định",
        quote_below_floor: "Báo giá dưới giá sàn/vượt trần",
    },
    approverRole: { sales_manager: "Trưởng kinh doanh", ceo: "Giám đốc" },
};

const asOptions = (map) => Object.keys(map).map((k) => ({ v: k, label: map[k] }));
const today = () => new Date().toISOString().slice(0, 10);

export class DlPricingConfig extends Component {
    static template = "dl_config.DlPricingConfig";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.tabs = TABS;
        this.L = L;
        this.opt = {
            wasteTarget: asOptions(L.wasteTarget),
            opMethod: asOptions(L.opMethod),
            costType: asOptions(L.costType),
            costMethod: asOptions(L.costMethod),
            customerGroup: asOptions(L.customerGroup),
            approverRole: asOptions(L.approverRole),
        };
        this.state = useState({
            tab: "waste",
            loading: true,
            perms: {},
            options: { categories: [], products: [], operations: [], complexity: [], approvers: [] },
            rows: {
                waste: [], operation: [], cost: [], profit: [], discount: [],
                approval: [], apprset: [], complexity: [], opcat: [],
            },
            form: null, // { section, id, ...fields }
            reject: null, // { id, comment }
            toast: null,
            dialog: null,
        });

        onWillStart(async () => {
            const boot = await this.orm.call("dl.pricing.ui", "get_bootstrap", []);
            this.state.perms = boot.perms;
            this.state.options = boot.options;
            await Promise.all([
                this.load("waste"), this.load("operation"), this.load("cost"),
                this.load("profit"), this.load("discount"), this.load("approval"),
                this.load("apprset"), this.load("complexity"), this.load("opcat"),
            ]);
            this.state.loading = false;
        });
    }

    // --- Nạp dữ liệu từng nhóm ---------------------------------------------
    _fields(section) {
        return {
            waste: ["target_type", "category_id", "product_id", "target_label", "waste_rate",
                "has_recovery", "recovery_rate", "scrap_product_id", "valid_from", "valid_to",
                "state", "revision", "change_reason", "write_uid"],
            operation: ["operation_id", "method", "price_rate", "setup_fee", "valid_from",
                "valid_to", "state", "revision", "change_reason", "write_uid"],
            cost: ["name", "rule_type", "method", "value", "no_discount", "condition_days",
                "condition_amount", "valid_from", "valid_to", "state", "revision",
                "change_reason", "write_uid"],
            profit: ["target_markup", "min_markup", "valid_from", "valid_to", "state",
                "revision", "change_reason", "write_uid"],
            discount: ["customer_group", "default_rate", "max_rate", "valid_from", "valid_to",
                "state", "revision", "change_reason", "write_uid"],
            approval: ["create_date", "request_type", "object_label", "old_value", "new_value",
                "impact", "requester_id", "requester_role", "resolved_by_id", "reason",
                "reject_comment", "is_self_approval", "state"],
            apprset: ["request_type", "approver_role", "approver_user_id"],
            complexity: ["name", "factor", "note", "active", "sequence"],
            opcat: ["name", "code", "active", "sequence"],
        }[section];
    }
    _order(section) {
        if (section === "approval") return "create_date desc";
        if (section === "complexity" || section === "opcat") return "sequence, id";
        if (section === "apprset") return "request_type";
        return "state, valid_from desc";
    }
    async load(section) {
        const model = M[section];
        try {
            this.state.rows[section] = await this.orm.searchRead(
                model, [], this._fields(section), { order: this._order(section) }
            );
        } catch (e) {
            // Vai trò không có quyền đọc nhóm này → để trống, không làm vỡ cả màn.
            this.state.rows[section] = [];
        }
    }

    // --- Helpers hiển thị ---------------------------------------------------
    setTab(k) { this.state.tab = k; }
    m2oName(v) { return Array.isArray(v) ? v[1] : ""; }
    m2oId(v) { return Array.isArray(v) ? v[0] : false; }
    stLabel(s) { return STATE_LABEL[s] || s; }
    stCls(s) { return STATE_CLS[s] || ""; }
    lab(group, key) { return (L[group] && L[group][key]) || key || ""; }
    fmtDate(s) { return s ? s.split(" ")[0].split("-").reverse().join("/") : ""; }
    num(v) { return v == null ? "" : v; }

    flash(msg) {
        this.state.toast = msg;
        clearTimeout(this._t);
        this._t = setTimeout(() => (this.state.toast = null), 3200);
    }
    showError(e) {
        const msg = (e && e.data && e.data.message) || (e && e.message) || "Có lỗi xảy ra.";
        this.state.dialog = { kind: "block", title: "Không thực hiện được", msg };
    }
    canEdit(section) {
        const map = { profit: "profit", discount: "discount", approval: "approval" };
        if (section === "waste" || section === "operation") return this.state.perms.waste;
        if (section === "cost") return this.state.perms.cost;
        if (section === "master" || section === "complexity" || section === "opcat" || section === "apprset")
            return this.state.perms.master;
        return this.state.perms[map[section]] || false;
    }

    // --- Modal form: mở tạo mới / sửa ---------------------------------------
    openCreate(section) {
        this.state.form = { section, id: null, ...this._blank(section) };
    }
    openEdit(section, row) {
        const f = { section, id: row.id };
        for (const k of this._formKeys(section)) {
            f[k] = ["category_id", "product_id", "scrap_product_id", "operation_id", "approver_user_id"].includes(k)
                ? this.m2oId(row[k]) : row[k];
        }
        this.state.form = f;
    }
    closeForm() { this.state.form = null; }
    _formKeys(section) {
        return {
            waste: ["target_type", "category_id", "product_id", "waste_rate", "has_recovery",
                "recovery_rate", "scrap_product_id", "valid_from", "change_reason"],
            operation: ["operation_id", "method", "price_rate", "setup_fee", "valid_from", "change_reason"],
            cost: ["name", "rule_type", "method", "value", "no_discount", "condition_days",
                "condition_amount", "valid_from", "change_reason"],
            profit: ["target_markup", "min_markup", "valid_from", "change_reason"],
            discount: ["customer_group", "default_rate", "max_rate", "valid_from", "change_reason"],
        }[section];
    }
    _blank(section) {
        const base = { valid_from: today(), change_reason: "" };
        const d = {
            waste: { target_type: "category", category_id: false, product_id: false, waste_rate: 0,
                has_recovery: false, recovery_rate: 0, scrap_product_id: false },
            operation: { operation_id: false, method: "percent_material", price_rate: 0, setup_fee: 0 },
            cost: { name: "", rule_type: "workshop_overhead", method: "percent_direct", value: 0,
                no_discount: false, condition_days: 0, condition_amount: 0 },
            profit: { target_markup: 0, min_markup: 0 },
            discount: { customer_group: "new", default_rate: 0, max_rate: 0 },
        }[section];
        return { ...d, ...base };
    }
    _payload(f) {
        const keys = this._formKeys(f.section);
        const vals = {};
        for (const k of keys) {
            vals[k] = f[k] === undefined ? false : f[k];
        }
        return vals;
    }
    async saveForm() {
        const f = this.state.form;
        const model = M[f.section];
        try {
            const vals = this._payload(f);
            if (f.id) {
                await this.orm.write(model, [f.id], vals);
            } else {
                await this.orm.create(model, [vals]);
            }
            this.closeForm();
            await this.load(f.section);
            this.flash("Đã lưu.");
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Hành động vòng đời --------------------------------------------------
    async runAction(section, id, method, reloadExtra) {
        try {
            await this.orm.call(M[section], method, [[id]]);
            await this.load(section);
            if (reloadExtra) { await this.load(reloadExtra); }
            this.flash("Đã cập nhật.");
        } catch (e) {
            this.showError(e);
        }
    }
    apply(section, id) { this.runAction(section, id, "action_apply"); }
    expire(section, id) {
        this.state.dialog = {
            kind: "confirm", title: "Ngừng áp dụng",
            msg: "Ngừng áp dụng quy tắc này? Báo giá cũ không bị ảnh hưởng.",
            okLabel: "Ngừng áp dụng",
            onOk: () => this.runAction(section, id, "action_expire"),
        };
    }
    revise(section, id) { this.runAction(section, id, "action_create_revision"); }
    submit(section, id) { this.runAction(section, id, "action_submit_approval", "approval"); }
    remove(section, id) {
        this.state.dialog = {
            kind: "confirm", danger: true, title: "Xóa quy tắc",
            msg: "Xóa quy tắc nháp này? Thao tác không thể hoàn tác.",
            okLabel: "Xóa",
            onOk: async () => {
                try {
                    await this.orm.unlink(M[section], [id]);
                    await this.load(section);
                    this.flash("Đã xóa.");
                } catch (e) { this.showError(e); }
            },
        };
    }

    // --- Phê duyệt ----------------------------------------------------------
    async approve(id) {
        try {
            await this.orm.call(M.approval, "action_approve", [[id]]);
            await Promise.all([this.load("approval"), this.load("profit"), this.load("discount")]);
            this.flash("Đã duyệt.");
        } catch (e) { this.showError(e); }
    }
    openReject(id) { this.state.reject = { id, comment: "" }; }
    closeReject() { this.state.reject = null; }
    async confirmReject() {
        const r = this.state.reject;
        if (!r.comment.trim()) { return; }
        try {
            await this.orm.write(M.approval, [r.id], { reject_comment: r.comment.trim() });
            await this.orm.call(M.approval, "action_reject", [[r.id]]);
            this.state.reject = null;
            await Promise.all([this.load("approval"), this.load("profit"), this.load("discount")]);
            this.flash("Đã từ chối.");
        } catch (e) { this.closeReject(); this.showError(e); }
    }

    // --- Danh mục (inline) --------------------------------------------------
    async inlineWrite(section, row, field, value) {
        try {
            await this.orm.write(M[section], [row.id], { [field]: value });
            row[field] = value;
        } catch (e) { this.showError(e); await this.load(section); }
    }
    async addComplexity() {
        try {
            await this.orm.create(M.complexity, [{ name: "Mức mới", factor: 1.0, sequence: 99 }]);
            await this.load("complexity");
        } catch (e) { this.showError(e); }
    }
    async addOperation() {
        const code = "OP" + Date.now().toString().slice(-5);
        try {
            await this.orm.create(M.opcat, [{ name: "Công đoạn mới", code, sequence: 99 }]);
            await this.load("opcat");
        } catch (e) { this.showError(e); }
    }
    async delMaster(section, id) {
        try { await this.orm.unlink(M[section], [id]); await this.load(section); }
        catch (e) { this.showError(e); }
    }

    // --- Dialog -------------------------------------------------------------
    async dialogOk() {
        const d = this.state.dialog;
        this.state.dialog = null;
        if (d && d.onOk) { try { await d.onOk(); } catch (e) { this.showError(e); } }
    }
    dialogClose() { this.state.dialog = null; }
}

registry.category("actions").add("dl_config.DlPricingConfig", DlPricingConfig);
