/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { onMoneyInput, parseMoney, formatMoney } from "@dl_base/js/money_format";

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
    matrix: "dl.pricing.approval.matrix",
    complexity: "dl.pricing.complexity.level",
    opcat: "dl.pricing.operation",
};

const STATE_LABEL = {
    draft: "Nháp", active: "Đang áp dụng", expired: "Ngừng áp dụng",
    pending: "Chờ duyệt", rejected: "Từ chối", approved: "Đã duyệt",
    cancelled: "Đã hủy do báo giá thay đổi",
};
const STATE_CLS = {
    draft: "is-draft", active: "is-active", expired: "is-expired",
    pending: "is-pending", rejected: "is-rejected", approved: "is-active",
    cancelled: "is-expired",
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
    customerGroup: { new: "Khách mới", existing: "Khách cũ", loyal: "Khách thân thiết" },
    approvalType: {
        profit_config: "Cấu hình lợi nhuận mới", discount_config: "Cấu hình chiết khấu mới",
        quote_discount: "Chiết khấu báo giá vượt mặc định",
        quote_below_floor: "Báo giá dưới giá sàn/vượt trần",
        quote_over_threshold: "Báo giá vượt ngưỡng giá trị",
    },
    approverRole: { sales_manager: "Trưởng kinh doanh", ceo: "Giám đốc" },
    approvalLevel: { none: "Không cần duyệt", sales_manager: "Trưởng kinh doanh", ceo: "Giám đốc" },
};

const asOptions = (map) => Object.keys(map).map((k) => ({ v: k, label: map[k] }));
const today = () => new Date().toISOString().slice(0, 10);

export class DlPricingConfig extends Component {
    static template = "dl_config.DlPricingConfig";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        // Helper tiền dùng chung — group hàng nghìn LIVE cho các ô NHẬP số tiền.
        // (fmtMoney sẵn có ở dưới dùng cho HIỂN THỊ, có hậu tố ₫ — giữ nguyên.)
        this.onMoneyInput = onMoneyInput;
        this.parseMoney = parseMoney;
        this.fmtMoneyInput = formatMoney;
        this.tabs = TABS;
        this.L = L;
        this.opt = {
            wasteTarget: asOptions(L.wasteTarget),
            opMethod: asOptions(L.opMethod),
            costType: asOptions(L.costType),
            costMethod: asOptions(L.costMethod),
            customerGroup: asOptions(L.customerGroup),
            approverRole: asOptions(L.approverRole),
            approvalLevel: asOptions(L.approvalLevel),
        };
        this.state = useState({
            tab: "waste",
            approvalSub: "matrix", // matrix | pending | history
            matrixShowHistory: false, // hiện các dòng "Ngừng áp dụng" trong ma trận
            discountShowHistory: false, // hiện các dòng "Ngừng áp dụng" trong bảng chiết khấu
            loading: true,
            perms: {},
            options: { categories: [], products: [], operations: [], complexity: [], approvers: [] },
            rows: {
                waste: [], operation: [], cost: [], profit: [], discount: [],
                approval: [], apprset: [], matrix: [], complexity: [], opcat: [],
                materials: [],
            },
            form: null, // { section, id, ...fields }
            // Bộ lọc màn Hao hụt: tìm nhanh + nhóm vật tư + chế độ lọc.
            wasteFilter: { q: "", categ: 0, mode: "all" }, // mode: all | recovery | missing
            wasteCollapsed: {}, // { [categId]: true } — nhóm đang thu gọn
            reject: null, // { id, comment }
            toast: null,
            dialog: null,
            // Phân loại khách hàng tự động (ngưỡng lên Khách thân thiết).
            classification: { threshold: 0, canEdit: false },
        });

        onWillStart(async () => {
            const boot = await this.orm.call("dl.pricing.ui", "get_bootstrap", []);
            this.state.perms = boot.perms;
            this.state.options = boot.options;
            await Promise.all([
                this.load("waste"), this.load("operation"), this.load("cost"),
                this.load("profit"), this.load("discount"), this.load("approval"),
                this.load("apprset"), this.load("matrix"), this.load("complexity"),
                this.load("opcat"), this.loadClassification(), this.loadMaterials(),
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
            discount: ["customer_group", "group_rank", "default_rate", "max_rate", "valid_from",
                "valid_to", "state", "revision", "change_reason", "write_uid"],
            approval: ["create_date", "request_type", "object_label", "old_value", "new_value",
                "impact", "requester_id", "requester_role", "resolved_by_id", "resolved_at",
                "reason", "reject_comment", "is_self_approval", "state", "approval_level",
                "matrix_revision", "trigger_reasons", "res_model", "res_id", "can_resolve"],
            apprset: ["request_type", "approver_role", "approver_user_id"],
            matrix: ["value_from", "approval_level", "approver_user_id", "note", "valid_from",
                "valid_to", "state", "revision", "change_reason", "used_in_snapshot", "write_uid",
                "has_pending_request"],
            complexity: ["name", "factor", "note", "active", "sequence"],
            opcat: ["name", "code", "active", "sequence"],
        }[section];
    }
    _order(section) {
        if (section === "approval") return "create_date desc";
        if (section === "complexity" || section === "opcat") return "sequence, id";
        if (section === "apprset") return "request_type";
        if (section === "matrix") return "value_from asc, revision desc";
        // Chiết khấu xếp theo bậc gắn bó (mới→cũ→thân thiết) để đọc thành thang.
        if (section === "discount") return "group_rank asc, state, valid_from desc";
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

    // --- Phân loại khách hàng tự động (ngưỡng lên Khách thân thiết) ---------
    async loadClassification() {
        try {
            this.state.classification = await this.orm.call(
                "res.partner", "get_customer_classification_config", []);
        } catch (e) {
            this.state.classification = { threshold: 0, canEdit: false };
        }
    }
    async saveClassification() {
        try {
            const val = Number(this.state.classification.threshold) || 0;
            const saved = await this.orm.call(
                "res.partner", "set_loyal_threshold", [val]);
            this.state.classification.threshold = saved;
            this.flash("Đã lưu ngưỡng phân loại khách hàng.");
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Hao hụt theo VẬT TƯ (nguồn thật dùng cho BOM/báo giá) --------------
    async loadMaterials() {
        try {
            this.state.rows.materials = await this.orm.searchRead(
                "product.product",
                [["product_kind", "in", ["material", "material_processed"]]],
                ["display_name", "default_code", "categ_id", "dlm_waste_rate",
                    "dlm_has_recovery", "dlm_recovery_rate", "dlm_scrap_product_id"],
                { order: "default_code, id" }
            );
        } catch (e) {
            this.state.rows.materials = [];
        }
    }
    async toggleRecovery(row, checked) {
        row.dlm_has_recovery = checked;
        if (!checked) { row.dlm_recovery_rate = 0; }
        await this.saveMaterial(row);
    }
    async saveMaterial(row) {
        try {
            await this.orm.call("product.product", "set_dlm_waste", [[row.id], {
                dlm_waste_rate: Number(row.dlm_waste_rate) || 0,
                dlm_has_recovery: !!row.dlm_has_recovery,
                dlm_recovery_rate: row.dlm_has_recovery ? (Number(row.dlm_recovery_rate) || 0) : 0,
            }]);
            this.flash("Đã lưu hao hụt vật tư.");
        } catch (e) {
            this.showError(e);
            await this.loadMaterials();
        }
    }

    // --- Lọc & gom nhóm bảng hao hụt (UX khi danh sách vật tư dài) ----------
    get wasteCategories() {
        const seen = new Map();
        for (const m of this.state.rows.materials) {
            const id = this.m2oId(m.categ_id);
            if (id && !seen.has(id)) { seen.set(id, this.m2oName(m.categ_id)); }
        }
        return [...seen].map(([v, label]) => ({ v, label }))
            .sort((a, b) => a.label.localeCompare(b.label, "vi"));
    }
    get wasteRecoveryCount() {
        return this.state.rows.materials.filter((m) => m.dlm_has_recovery).length;
    }
    get wasteMissingCount() {
        return this.state.rows.materials.filter((m) => !(Number(m.dlm_waste_rate) > 0)).length;
    }
    get filteredMaterials() {
        const f = this.state.wasteFilter;
        const q = f.q.trim().toLowerCase();
        return this.state.rows.materials.filter((m) => {
            if (f.categ && this.m2oId(m.categ_id) !== f.categ) { return false; }
            if (f.mode === "recovery" && !m.dlm_has_recovery) { return false; }
            if (f.mode === "missing" && Number(m.dlm_waste_rate) > 0) { return false; }
            if (q) {
                const hay = `${m.default_code || ""} ${m.display_name || ""}`.toLowerCase();
                if (!hay.includes(q)) { return false; }
            }
            return true;
        });
    }
    get materialGroups() {
        const groups = new Map();
        for (const m of this.filteredMaterials) {
            const id = this.m2oId(m.categ_id) || 0;
            if (!groups.has(id)) {
                groups.set(id, { id, name: this.m2oName(m.categ_id) || "Chưa phân nhóm", rows: [] });
            }
            groups.get(id).rows.push(m);
        }
        return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, "vi"));
    }
    toggleWasteGroup(id) {
        this.state.wasteCollapsed[id] = !this.state.wasteCollapsed[id];
    }
    // Đổi bộ lọc/tìm kiếm → mở lại mọi nhóm để kết quả không bị giấu;
    // sau đó vẫn thu gọn từng nhóm bằng tay bình thường.
    expandWasteGroups() { this.state.wasteCollapsed = {}; }
    setWasteCateg(v) {
        this.state.wasteFilter.categ = v ? Number(v) : 0;
        this.expandWasteGroups();
    }
    setWasteMode(m) {
        this.state.wasteFilter.mode = m;
        this.expandWasteGroups();
    }
    clearWasteFilter() {
        this.state.wasteFilter = { q: "", categ: 0, mode: "all" };
        this.expandWasteGroups();
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
    // Trưởng KD được đề xuất trên ma trận (tạo/sửa/xóa bản Nháp, tạo Sửa đổi);
    // kích hoạt/ngừng vẫn theo canEdit('matrix') = Giám đốc/Admin.
    // Fallback về quyền matrix khi bootstrap cũ chưa có key này (server chưa
    // nạp lại Python) — tránh mất nút "Thêm mức duyệt" với CEO/Admin.
    canPropose() {
        const p = this.state.perms.matrix_propose;
        return p === undefined ? this.canEdit("matrix") : p;
    }
    canEdit(section) {
        const map = { profit: "profit", discount: "discount", approval: "approval", matrix: "matrix" };
        if (section === "waste" || section === "operation") return this.state.perms.waste;
        if (section === "cost") return this.state.perms.cost;
        if (section === "master" || section === "complexity" || section === "opcat" || section === "apprset")
            return this.state.perms.master;
        return this.state.perms[map[section]] || false;
    }

    // --- Sub-tab của màn Phê duyệt (Ma trận / Chờ duyệt / Lịch sử) -----------
    setApprovalSub(k) { this.state.approvalSub = k; }
    get pendingRequests() {
        return this.state.rows.approval.filter((r) => r.state === "pending");
    }
    get historyRequests() {
        return this.state.rows.approval.filter((r) => r.state !== "pending");
    }
    // Mặc định ẩn các dòng "Ngừng áp dụng" cho đỡ rối — bấm "Lịch sử" để xem.
    get matrixRows() {
        const rows = this.state.rows.matrix;
        return this.state.matrixShowHistory
            ? rows : rows.filter((r) => r.state !== "expired");
    }
    get matrixHistoryCount() {
        return this.state.rows.matrix.filter((r) => r.state === "expired").length;
    }
    toggleMatrixHistory() {
        this.state.matrixShowHistory = !this.state.matrixShowHistory;
    }
    // Cảnh báo mềm: thang đang áp dụng không kết thúc bằng Giám đốc — báo giá
    // giá trị rất lớn sẽ chỉ cần cấp thấp hơn duyệt (hoặc không cần duyệt).
    get matrixLadderWarning() {
        const actives = this.state.rows.matrix.filter((r) => r.state === "active");
        if (!actives.length) return "";
        const top = actives.reduce((a, b) => (b.value_from > a.value_from ? b : a));
        if (top.approval_level === "ceo") return "";
        const topLabel = this.lab("approvalLevel", top.approval_level);
        return top.approval_level === "none"
            ? "Thang chưa có mức duyệt nào ngoài \"Không cần duyệt\" — mọi báo giá sẽ không cần phê duyệt theo giá trị."
            : `Thang chưa có mức Giám đốc: báo giá vượt ${this.fmtMoney(top.value_from)} sẽ chỉ cần ${topLabel} duyệt. Cân nhắc thêm ngưỡng cao nhất cho Giám đốc.`;
    }
    fmtMoney(v) {
        if (v == null || v === "") return "";
        return new Intl.NumberFormat("vi-VN").format(v) + " ₫";
    }
    // Mặc định ẩn các dòng "Ngừng áp dụng" cho đỡ rối — bấm "Lịch sử" để xem
    // (đồng bộ với cách làm của bảng ma trận phê duyệt).
    get discountRows() {
        const rows = this.state.rows.discount;
        return this.state.discountShowHistory
            ? rows : rows.filter((r) => r.state !== "expired");
    }
    get discountHistoryCount() {
        return this.state.rows.discount.filter((r) => r.state === "expired").length;
    }
    toggleDiscountHistory() {
        this.state.discountShowHistory = !this.state.discountShowHistory;
    }
    // Cảnh báo mềm cho thang chiết khấu (tương tự matrixLadderWarning):
    // (1) bậc bị đảo — nhóm gắn bó hơn lại chiết khấu thấp hơn (hàng rào cứng
    //     đã chặn, đây là lưới an toàn cho dữ liệu cũ); (2) thiếu nhóm đang áp
    //     dụng — báo giá nhóm đó sẽ mặc định 0% chiết khấu.
    get discountLadderWarning() {
        const order = ["new", "existing", "loyal"];
        const byGroup = {};
        for (const r of this.state.rows.discount) {
            if (r.state === "active") { byGroup[r.customer_group] = r; }
        }
        const present = order.filter((g) => byGroup[g]);
        for (let i = 1; i < present.length; i++) {
            const prev = byGroup[present[i - 1]];
            const cur = byGroup[present[i]];
            if (cur.default_rate < prev.default_rate || cur.max_rate < prev.max_rate) {
                return `${this.lab("customerGroup", cur.customer_group)} đang được chiết khấu thấp hơn ${this.lab("customerGroup", prev.customer_group)}. Khách gắn bó hơn phải được ưu đãi ≥ khách mới hơn — hãy chỉnh lại.`;
            }
        }
        if (present.length && present.length < order.length) {
            const missing = order.filter((g) => !byGroup[g])
                .map((g) => this.lab("customerGroup", g)).join(", ");
            return `Chưa có chính sách đang áp dụng cho: ${missing}. Báo giá cho nhóm này sẽ mặc định 0% chiết khấu.`;
        }
        return "";
    }
    // Tập id dòng chiết khấu tham gia một cặp đảo bậc — để tô đỏ đúng dòng vi
    // phạm ngay trên bảng (review UX config #f3), thay vì chỉ một câu cảnh báo.
    get discountViolationIds() {
        const order = ["new", "existing", "loyal"];
        const byGroup = {};
        for (const r of this.state.rows.discount) {
            if (r.state === "active") { byGroup[r.customer_group] = r; }
        }
        const present = order.filter((g) => byGroup[g]);
        const ids = new Set();
        for (let i = 1; i < present.length; i++) {
            const prev = byGroup[present[i - 1]];
            const cur = byGroup[present[i]];
            if (cur.default_rate < prev.default_rate || cur.max_rate < prev.max_rate) {
                ids.add(cur.id);
                ids.add(prev.id);
            }
        }
        return ids;
    }
    reasonLines(txt) {
        return (txt || "").split("\n").map((s) => s.trim()).filter(Boolean);
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
            matrix: ["value_from", "approval_level", "approver_user_id", "note", "valid_from",
                "change_reason"],
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
            matrix: { value_from: 0, approval_level: "sales_manager", approver_user_id: false, note: "" },
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
        // Ma trận: lý do thay đổi bắt buộc khi sửa (mục 3, 9).
        if (f.section === "matrix" && f.id && !(f.change_reason || "").trim()) {
            this.showError({ message: "Bắt buộc nhập lý do thay đổi khi sửa dòng ma trận." });
            return;
        }
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
    async revise(section, id) {
        try {
            const res = await this.orm.call(M[section], "action_create_revision", [[id]]);
            await this.load(section);
            // Ma trận: mở luôn form của bản Nháp mới cho đỡ phải đi tìm dòng.
            const newId = res && res.res_id;
            const row = newId && this.state.rows[section].find((r) => r.id === newId);
            if (section === "matrix" && row) {
                this.openEdit(section, row);
            } else {
                this.flash("Đã tạo bản sửa đổi (Nháp).");
            }
        } catch (e) {
            this.showError(e);
        }
    }
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
    // Mở đối tượng của yêu cầu (báo giá / cấu hình) để xem chi tiết đầy đủ trước
    // khi quyết định duyệt. Báo giá mở kèm tab "Phân tích giá thành".
    openTarget(row) {
        if (!row.res_model || !row.res_id) {
            this.flash("Yêu cầu này không gắn với đối tượng cụ thể.");
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.res_model,
            res_id: row.res_id,
            views: [[false, "form"]],
            target: "new",
        });
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
    // Chọn người duyệt cụ thể (m2o): "" → false (theo vai trò), else → id số.
    async setApprover(row, value) {
        return this.inlineWrite("apprset", row, "approver_user_id", value ? Number(value) : false);
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
