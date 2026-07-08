/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ============================================================================
// S02 — Cấu hình Hệ thống (mock UI)
// Tab 1: Tham số báo giá | Tab 2: Ma trận phê duyệt | Tab 3: SLA & Escalation
// Tab 4: Tham số Parametric | Tab 5: Lịch sử thay đổi (audit)
// Admin/CEO được sửa, Trưởng KD chỉ xem. Bản mock: dữ liệu in-memory.
// Nguyên tắc: thay đổi có hiệu lực với báo giá MỚI; báo giá cũ giữ snapshot (BR-28).
// ============================================================================

const TABS = [
    { key: "cost", label: "Tham số báo giá", icon: "fa-sliders" },
    { key: "matrix", label: "Ma trận phê duyệt", icon: "fa-sitemap" },
    { key: "sla", label: "SLA & Escalation", icon: "fa-clock-o" },
    { key: "param", label: "Tham số Parametric", icon: "fa-flask" },
    { key: "audit", label: "Lịch sử thay đổi", icon: "fa-history" },
];

const ROUNDING = [
    { v: 1000, label: "Làm tròn đến 1.000đ" },
    { v: 10000, label: "Làm tròn đến 10.000đ" },
    { v: 0, label: "Không làm tròn" },
];

const APPROVER_ROLES = [
    { key: "none", label: "Không cần duyệt" },
    { key: "sales_manager", label: "Trưởng KD" },
    { key: "ceo", label: "CEO" },
    { key: "custom", label: "Custom role" },
];

const APPROVER_USERS = [
    { key: "", label: "(Theo vai trò)" },
    { key: "ceo1", label: "Trần Thị Bích (CEO)" },
    { key: "skd1", label: "Lê Văn Cường (Trưởng KD)" },
];

const MODES = ["Tuần tự", "Song song", "Trực tiếp", "—"];

// Nhãn field phục vụ ghi audit "cũ → mới".
const COST_LABELS = {
    material: "Tỷ lệ chi phí vật tư (%)",
    labor: "Tỷ lệ chi phí nhân công (%)",
    risk: "Tỷ lệ rủi ro / phát sinh (%)",
    margin: "Lợi nhuận mục tiêu (%)",
    overhead: "Chi phí vận hành / overhead (%)",
    maxDiscount: "Chiết khấu tối đa (%)",
    vat: "VAT mặc định (%)",
    priceValidity: "Hiệu lực giá vật tư (ngày)",
    rounding: "Làm tròn giá bán",
};
const SLA_LABELS = {
    salesManager: "SLA Trưởng KD (giờ)",
    ceo: "SLA CEO (giờ)",
    reminderEvery: "Tần suất nhắc (giờ)",
    requireLateReason: "Bắt buộc lý do khi duyệt trễ",
};
const PARAM_LABELS = {
    steelDensity: "Tỉ trọng thép (kg/m³)",
};

const now = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const clone = (o) => JSON.parse(JSON.stringify(o));

let _lid = 10;
const nextLid = () => `L${++_lid}`;

export class DlSysConfig extends Component {
    static template = "dl_config.DlSysConfig";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.tabs = TABS;
        this.rounding = ROUNDING;
        this.approverRoles = APPROVER_ROLES;
        this.approverUsers = APPROVER_USERS;
        this.modes = MODES;

        this.state = useState({
            tab: "cost",
            cost: {
                material: 55, labor: 32, risk: 3, margin: 12,
                overhead: 8, maxDiscount: 15, vat: 0, priceValidity: 30, rounding: 1000,
            },
            waste: [
                { group: "Thép tấm", pct: 3 },
                { group: "Thép hộp", pct: 5 },
                { group: "Thép ống", pct: 5 },
                { group: "Sơn", pct: 8 },
                { group: "Vật tư phụ", pct: 2 },
                { group: "Gia công ngoài", pct: 0 },
            ],
            levels: [
                { id: "L1", name: "Tự động", vMin: 0, vMax: 20, dMin: 0, dMax: 5, marginMin: null, role: "none", user: "", backup: "", mode: "—", sla: 0, note: "Không cần duyệt → Ready to Send", active: true, pending: 0, priority: false },
                { id: "L2", name: "Cấp 1 – Trưởng KD", vMin: 20, vMax: 100, dMin: 5, dMax: 15, marginMin: 8, role: "sales_manager", user: "", backup: "ceo1", mode: "Tuần tự", sla: 4, note: "", active: true, pending: 2, priority: false },
                { id: "L3", name: "Cấp 2 – CEO", vMin: 100, vMax: null, dMin: 15, dMax: 100, marginMin: 8, role: "ceo", user: "", backup: "", mode: "Tuần tự", sla: 8, note: "", active: true, pending: 1, priority: false },
                { id: "L4", name: "Cấp 2 (ưu tiên) – Margin thấp", vMin: 0, vMax: null, dMin: 0, dMax: 100, marginMin: 8, role: "ceo", user: "", backup: "", mode: "Trực tiếp", sla: 8, note: "Margin < 8% → CEO trực tiếp, bỏ qua Cấp 1", active: true, pending: 0, priority: true },
            ],
            sla: {
                salesManager: 4, ceo: 8, reminderEvery: 2, requireLateReason: true,
                onOverdue: { remind: true, escalate: true, log: true, kpi: true },
            },
            parametric: {
                steelDensity: 7850,
                kgm: [
                    { spec: "Thép hộp 25×25 dày 1.2mm", val: 0.85 },
                    { spec: "Thép hộp 30×30 dày 1.4mm", val: 1.15 },
                    { spec: "Thép ống D27 dày 1.5mm", val: 0.94 },
                ],
                paint: [
                    { type: "Sơn tĩnh điện (2 lớp)", val: 6 },
                    { type: "Mạ kẽm nhúng nóng", val: 8 },
                ],
                aux: [
                    { name: "Ốc vít M6", qty: 8, unit: "con/sp" },
                    { name: "Bản lề", qty: 2, unit: "cái/sp" },
                ],
            },
            audit: [
                { time: "01/07/2026 09:10", tab: "Tham số báo giá", param: "Lợi nhuận mục tiêu (%)", detail: "10 → 12" },
                { time: "15/06/2026 14:30", tab: "Ma trận phê duyệt", param: "Cấp 2 – CEO", detail: "Ngưỡng giá trị > 80tr → > 100tr" },
            ],
            toast: null,
            dialog: null,
        });

        // Baseline (không reactive) để tính diff khi Lưu.
        this._snapshot();
    }

    _snapshot() {
        this.baseline = {
            cost: clone(this.state.cost),
            waste: clone(this.state.waste),
            sla: clone(this.state.sla),
            parametric: clone(this.state.parametric),
        };
    }

    // --- Helpers ------------------------------------------------------------
    setTab(key) {
        this.state.tab = key;
    }
    roundLabel(v) {
        const r = ROUNDING.find((x) => x.v === Number(v));
        return r ? r.label : v;
    }
    roleLabel(key) {
        const r = APPROVER_ROLES.find((x) => x.key === key);
        return r ? r.label : key;
    }
    userLabel(key) {
        const u = APPROVER_USERS.find((x) => x.key === key);
        return u ? u.label : key;
    }
    vRange(l) {
        const lo = l.vMin || 0;
        const hi = l.vMax == null ? "∞" : l.vMax;
        return `${lo} – ${hi} tr`;
    }

    flash(msg) {
        this.state.toast = msg;
        clearTimeout(this._toastT);
        this._toastT = setTimeout(() => (this.state.toast = null), 3600);
    }
    _pushAudit(tabLabel, entries) {
        const stamped = entries.map((e) => ({ time: now(), tab: tabLabel, param: e.param, detail: e.detail }));
        this.state.audit = [...stamped, ...this.state.audit];
    }
    _diffScalars(cur, base, labels) {
        const out = [];
        for (const k in labels) {
            let a = base[k];
            let b = cur[k];
            if (k === "rounding") { a = this.roundLabel(a); b = this.roundLabel(b); }
            if (typeof a === "boolean" || typeof b === "boolean") {
                a = a ? "Bật" : "Tắt"; b = b ? "Bật" : "Tắt";
            }
            if (String(a) !== String(b)) {
                out.push({ param: labels[k], detail: `${a} → ${b}` });
            }
        }
        return out;
    }

    // --- Tab 1: Tham số báo giá --------------------------------------------
    saveCost() {
        const entries = this._diffScalars(this.state.cost, this.baseline.cost, COST_LABELS);
        if (JSON.stringify(this.state.waste) !== JSON.stringify(this.baseline.waste)) {
            entries.push({ param: "Tỷ lệ hao hụt theo nhóm vật tư", detail: "Đã cập nhật bảng" });
        }
        if (!entries.length) {
            this.flash("Không có thay đổi để lưu.");
            return;
        }
        this._pushAudit("Tham số báo giá", entries);
        this.baseline.cost = clone(this.state.cost);
        this.baseline.waste = clone(this.state.waste);
        this.flash("Đã lưu. Áp dụng cho báo giá MỚI tạo; báo giá cũ giữ snapshot.");
    }
    addWaste() {
        this.state.waste = [...this.state.waste, { group: "Nhóm mới", pct: 0 }];
    }
    removeWaste(i) {
        this.state.waste = this.state.waste.filter((_, idx) => idx !== i);
    }

    // --- Tab 2: Ma trận phê duyệt ------------------------------------------
    // Cặp level có vùng giá trị giao nhau (>0) — bỏ qua level priority & inactive.
    get overlapIds() {
        const set = new Set();
        const ls = this.state.levels.filter((l) => l.active && !l.priority);
        for (let i = 0; i < ls.length; i++) {
            for (let j = i + 1; j < ls.length; j++) {
                const a = ls[i], b = ls[j];
                const aMax = a.vMax == null ? Infinity : a.vMax;
                const bMax = b.vMax == null ? Infinity : b.vMax;
                const lo = Math.max(a.vMin || 0, b.vMin || 0);
                const hi = Math.min(aMax, bMax);
                if (hi - lo > 0) { set.add(a.id); set.add(b.id); }
            }
        }
        return set;
    }
    hasOverlap(l) {
        return this.overlapIds.has(l.id);
    }
    get ceoBackupMissing() {
        return this.state.levels.some(
            (l) => l.active && l.role === "ceo" && !l.backup && !l.user
        );
    }
    addLevel() {
        const l = {
            id: nextLid(), name: "Cấp duyệt mới", vMin: 0, vMax: null, dMin: 0, dMax: 100,
            marginMin: null, role: "sales_manager", user: "", backup: "", mode: "Tuần tự",
            sla: 4, note: "", active: true, pending: 0, priority: false,
        };
        this.state.levels = [...this.state.levels, l];
        this._pushAudit("Ma trận phê duyệt", [{ param: l.name, detail: "Thêm cấp duyệt mới" }]);
    }
    toggleLevel(l) {
        l.active = !l.active;
        this._pushAudit("Ma trận phê duyệt", [{ param: l.name, detail: l.active ? "Kích hoạt" : "Vô hiệu hóa" }]);
    }
    removeLevel(l) {
        // Không xóa vĩnh viễn nếu level đang có BG chờ duyệt.
        if (l.pending > 0) {
            this.state.dialog = {
                kind: "block",
                title: "Không thể xóa cấp duyệt",
                msg: `Cấp "${l.name}" đang có ${l.pending} báo giá chờ duyệt. Chỉ được vô hiệu hóa (không xóa vĩnh viễn) cho tới khi xử lý xong.`,
            };
            return;
        }
        this.state.dialog = {
            kind: "confirm", danger: true, title: "Xóa cấp duyệt",
            msg: `Xóa cấp "${l.name}" khỏi ma trận?`, okLabel: "Xóa",
            onOk: () => {
                this.state.levels = this.state.levels.filter((x) => x.id !== l.id);
                this._pushAudit("Ma trận phê duyệt", [{ param: l.name, detail: "Xóa cấp duyệt" }]);
            },
        };
    }
    moveLevel(i, dir) {
        const arr = [...this.state.levels];
        const j = i + dir;
        if (j < 0 || j >= arr.length) {
            return;
        }
        [arr[i], arr[j]] = [arr[j], arr[i]];
        this.state.levels = arr;
    }
    saveMatrix() {
        if (this.overlapIds.size) {
            this.state.dialog = {
                kind: "block",
                title: "Ngưỡng giá trị bị chồng chéo",
                msg: "Có cấp duyệt trùng khoảng giá trị (highlight đỏ). Một khoảng giá không được thuộc 2 cấp. Hãy điều chỉnh để không chồng chéo trước khi lưu.",
            };
            return;
        }
        this._pushAudit("Ma trận phê duyệt", [{ param: "Toàn ma trận", detail: "Lưu cấu hình ma trận phê duyệt" }]);
        this.flash("Đã lưu ma trận. BG đang Pending giữ nguyên cấp cũ; BG mới định tuyến theo ma trận mới.");
    }

    // --- Tab 3: SLA & Escalation -------------------------------------------
    saveSla() {
        const s = this.state.sla;
        if (s.salesManager < 1 || s.ceo < 1 || s.reminderEvery < 1) {
            this.state.dialog = {
                kind: "block", title: "SLA không hợp lệ",
                msg: "SLA và tần suất nhắc phải ≥ 1 giờ làm việc.",
            };
            return;
        }
        const entries = this._diffScalars(s, this.baseline.sla, SLA_LABELS);
        const oldOv = JSON.stringify(this.baseline.sla.onOverdue);
        if (oldOv !== JSON.stringify(s.onOverdue)) {
            entries.push({ param: "Hành động khi quá SLA", detail: "Đã cập nhật" });
        }
        if (!entries.length) {
            this.flash("Không có thay đổi để lưu.");
            return;
        }
        this._pushAudit("SLA & Escalation", entries);
        this.baseline.sla = clone(s);
        this.flash("Đã lưu SLA. Áp dụng cho các bước duyệt MỚI bắt đầu sau thời điểm lưu.");
    }

    // --- Tab 4: Parametric --------------------------------------------------
    saveParam() {
        const entries = this._diffScalars(this.state.parametric, this.baseline.parametric, PARAM_LABELS);
        ["kgm", "paint", "aux"].forEach((k) => {
            if (JSON.stringify(this.state.parametric[k]) !== JSON.stringify(this.baseline.parametric[k])) {
                const lbl = { kgm: "Định mức kg/m theo quy cách", paint: "Định mức phủ sơn", aux: "Định mức vật tư phụ" };
                entries.push({ param: lbl[k], detail: "Đã cập nhật bảng" });
            }
        });
        if (!entries.length) {
            this.flash("Không có thay đổi để lưu.");
            return;
        }
        this._pushAudit("Tham số Parametric", entries);
        this.baseline.parametric = clone(this.state.parametric);
        this.flash("Đã lưu tham số parametric. Áp dụng cho BOM / báo giá tính MỚI.");
    }
    addRow(tableKey) {
        const p = this.state.parametric;
        if (tableKey === "kgm") { p.kgm = [...p.kgm, { spec: "Quy cách mới", val: 0 }]; }
        if (tableKey === "paint") { p.paint = [...p.paint, { type: "Loại sơn mới", val: 0 }]; }
        if (tableKey === "aux") { p.aux = [...p.aux, { name: "Vật tư phụ", qty: 0, unit: "cái/sp" }]; }
    }
    removeRow(tableKey, i) {
        const p = this.state.parametric;
        p[tableKey] = p[tableKey].filter((_, idx) => idx !== i);
    }

    // --- Dialog -------------------------------------------------------------
    dialogOk() {
        const d = this.state.dialog;
        this.state.dialog = null;
        if (d && d.onOk) {
            d.onOk();
        }
    }
    dialogClose() {
        this.state.dialog = null;
    }
}

registry.category("actions").add("dl_config.DlSysConfig", DlSysConfig);
