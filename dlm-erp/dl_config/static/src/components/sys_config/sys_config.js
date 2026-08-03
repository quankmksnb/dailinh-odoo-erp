/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { onMoneyInput, parseMoney, formatMoney } from "@dl_base/js/money_format";

// ============================================================================
// S02 — Cấu hình Hệ thống
// Tab 1: Tham số báo giá | Tab 2: Ma trận phê duyệt | Tab 3: SLA & Escalation
// Tab 4: Tham số Parametric | Tab 5: Lịch sử thay đổi (audit)
// Admin/CEO được sửa, Trưởng KD chỉ xem.
// Tab 1 (cost), Tab 2 (matrix) & Tab 3 (SLA) đã nối backend thật (dl.pricing.config
// + dl.approval.level + audit DB); Tab 4 hiện còn mock in-memory. Tab 5 audit thật.
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

// Người duyệt (dropdown) được nạp THẬT từ server: res.users thuộc nhóm
// CEO / Trưởng KD / Admin qua get_tab2 → state.approverUsers (không hardcode).

const MODES = [
  { key: "sequential", label: "Tuần tự" },
  { key: "parallel", label: "Song song" },
  { key: "direct", label: "Trực tiếp" },
  { key: "none", label: "—" },
];

// Cơ cấu giá: 5 thành phần dưới đây CỘNG LẠI = 100% tổng báo giá (giá bán).
// Vật tư ~55% (tham khảo, không phải công thức cứng). Thứ tự = thứ tự trên thanh cơ cấu & bảng.
const COST_STRUCTURE = [
  {
    key: "material",
    label: "Vật tư",
    color: "#0a6ee0",
    hint: "Tham khảo 55% ",
  },
  {
    key: "labor",
    label: "Nhân công",
    color: "#0e9384",
    hint: "Tham khảo 30–35%",
  },
  {
    key: "overhead",
    label: "Vận hành (overhead)",
    color: "#b8730a",
    hint: "Cấu hình theo thực tế DN",
  },
  {
    key: "risk",
    label: "Rủi ro / phát sinh",
    color: "#c0392b",
    hint: "0–5% (mặc định 3%)",
  },
  {
    key: "margin",
    label: "Lợi nhuận mục tiêu",
    color: "#1b7a3d",
    hint: "Target margin — mặc định 12%",
  },
];

// Nhãn field phục vụ ghi audit "cũ → mới". Tab 1 & Tab 3 nay diff ở server;
// còn lại đây là nhãn cho Tab 4 (Parametric) vẫn diff phía client.
const PARAM_LABELS = {
  steelDensity: "Tỉ trọng thép (kg/m³)",
};

const now = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const clone = (o) => JSON.parse(JSON.stringify(o));

// Id tạm cho cấp duyệt MỚI thêm ở client (chưa lưu DB). save_tab2 phân biệt
// cấp cũ (id là số > 0 từ server) với cấp mới (id "tmp-*") để ghi đúng audit.
let _tmpSeq = 0;
const nextTmpId = () => `tmp-${++_tmpSeq}`;

export class DlSysConfig extends Component {
  static template = "dl_config.DlSysConfig";
  static props = { ...standardActionServiceProps };

  setup() {
    this.actionService = useService("action");
    this.orm = useService("orm");
    // Helper tiền dùng chung — group hàng nghìn LIVE cho các ô nhập số tiền.
    this.onMoneyInput = onMoneyInput;
    this.parseMoney = parseMoney;
    this.fmtMoney = formatMoney;
    this.tabs = TABS;
    this.rounding = ROUNDING;
    this.approverRoles = APPROVER_ROLES;
    this.modes = MODES;
    this.costStructure = COST_STRUCTURE;

    this.state = useState({
      tab: "cost",
      cost: {
        // 5 thành phần cơ cấu — Σ = 100% tổng báo giá (vật tư 55%)
        material: 55,
        labor: 25,
        overhead: 5,
        risk: 3,
        margin: 12,
        // tham số khác — KHÔNG nằm trong 100%
        maxDiscount: 15,
        vat: 0,
        priceValidity: 30,
        rounding: 1000,
      },
      sampleTotal: 100000000, // giá trị báo giá mẫu (đ) — chỉ để minh họa cơ cấu %
      waste: [
        { group: "Thép tấm", pct: 3 },
        { group: "Thép hộp", pct: 5 },
        { group: "Thép ống", pct: 5 },
        { group: "Sơn", pct: 8 },
        { group: "Vật tư phụ", pct: 2 },
        { group: "Gia công ngoài", pct: 0 },
      ],
      levels: [], // nạp thật từ dl.approval.level qua loadTab2
      approverUsers: [], // res.users (CEO/Trưởng KD/Admin) — nạp qua loadTab2
      sla: {
        salesManager: 4,
        ceo: 8,
        reminderEvery: 2,
        requireLateReason: true,
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
        {
          time: "01/07/2026 09:10",
          tab: "Tham số báo giá",
          param: "Lợi nhuận mục tiêu (%)",
          detail: "10 → 12",
        },
        {
          time: "15/06/2026 14:30",
          tab: "Ma trận phê duyệt",
          param: "Cấp 2 – CEO",
          detail: "Ngưỡng giá trị > 80tr → > 100tr",
        },
      ],
      canEdit: true, // server quyết định (Admin/CEO); cập nhật ở loadTab1
      toast: null,
      dialog: null,
    });

    // Baseline (không reactive) để tính diff khi Lưu.
    this._snapshot();
    // Tab 1 (cost), Tab 2 (matrix) & Tab 3 (SLA) nạp thật từ DB trước render đầu.
    onWillStart(() =>
      Promise.all([this.loadTab1(), this.loadTab2(), this.loadTab3()]),
    );
  }

  _snapshot() {
    this.baseline = {
      cost: clone(this.state.cost),
      waste: clone(this.state.waste),
      sla: clone(this.state.sla),
      parametric: clone(this.state.parametric),
    };
  }

  // Nạp cấu hình Tab 1 (cost + hao hụt + audit + quyền) từ dl.pricing.config.
  async loadTab1() {
    try {
      const res = await this.orm.call("dl.pricing.config", "get_tab1", []);
      this.state.cost = { ...this.state.cost, ...res.cost };
      this.state.waste = res.waste;
      this.state.canEdit = res.canEdit;
      this.state.audit = res.audit; // audit thật từ DB (thay seed mock Tab 1)
      this.baseline.cost = clone(this.state.cost);
      this.baseline.waste = clone(this.state.waste);
    } catch (e) {
      this.flash("Không tải được cấu hình từ máy chủ.");
    }
  }

  // Nạp cấu hình SLA (Tab 3) từ dl.pricing.config.
  async loadTab3() {
    try {
      const res = await this.orm.call("dl.pricing.config", "get_tab3", []);
      this.state.sla = { ...this.state.sla, ...res.sla };
      this.state.canEdit = res.canEdit;
      this.baseline.sla = clone(this.state.sla);
    } catch (e) {
      this.flash("Không tải được cấu hình SLA từ máy chủ.");
    }
  }

  // Nạp ma trận phê duyệt (Tab 2) + danh sách người duyệt thật từ server.
  async loadTab2() {
    try {
      const res = await this.orm.call("dl.pricing.config", "get_tab2", []);
      this.state.levels = res.levels;
      this.state.approverUsers = res.approvers;
      this.state.canEdit = res.canEdit;
    } catch (e) {
      this.flash("Không tải được ma trận phê duyệt từ máy chủ.");
    }
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
    const u = this.state.approverUsers.find((x) => String(x.id) === String(key));
    return u ? u.name : key ? key : "(Theo vai trò)";
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
    const stamped = entries.map((e) => ({
      time: now(),
      tab: tabLabel,
      param: e.param,
      detail: e.detail,
    }));
    this.state.audit = [...stamped, ...this.state.audit];
  }
  _diffScalars(cur, base, labels) {
    const out = [];
    for (const k in labels) {
      let a = base[k];
      let b = cur[k];
      if (k === "rounding") {
        a = this.roundLabel(a);
        b = this.roundLabel(b);
      }
      if (typeof a === "boolean" || typeof b === "boolean") {
        a = a ? "Bật" : "Tắt";
        b = b ? "Bật" : "Tắt";
      }
      if (String(a) !== String(b)) {
        out.push({ param: labels[k], detail: `${a} → ${b}` });
      }
    }
    return out;
  }

  // --- Tab 1: Tham số báo giá --------------------------------------------
  // Cơ cấu giá = 5 thành phần, cộng lại nên bằng 100% tổng báo giá.
  get costStructTotal() {
    const t = COST_STRUCTURE.reduce(
      (s, c) => s + (Number(this.state.cost[c.key]) || 0),
      0,
    );
    return Math.round(t * 100) / 100;
  }
  get costStructDelta() {
    return Math.round((this.costStructTotal - 100) * 100) / 100;
  }
  get costStructOk() {
    return this.costStructDelta === 0;
  }
  // Thanh cơ cấu: chuẩn hóa bề rộng theo max(tổng, 100) để không tràn khung.
  // Tổng < 100 → có phần "chưa phân bổ" (remainder); tổng > 100 → các đoạn co lại vừa khung, badge cảnh báo.
  get costBar() {
    const total = this.costStructTotal;
    const denom = Math.max(total, 100) || 100;
    const segs = COST_STRUCTURE.map((c) => {
      const pct = Number(this.state.cost[c.key]) || 0;
      return {
        key: c.key,
        label: c.label,
        color: c.color,
        pct,
        width: (pct / denom) * 100,
        amount: Math.round((pct / 100) * this.state.sampleTotal),
      };
    });
    return { total, segs, remainder: total < 100 ? 100 - total : 0 };
  }
  fmtVnd(n) {
    return (Math.round(Number(n)) || 0).toLocaleString("vi-VN") + "đ";
  }
  setCost(key, val) {
    const n = parseFloat(val);
    this.state.cost[key] = isNaN(n) ? 0 : n;
  }

  saveCost() {
    // Tổng cơ cấu là tỷ lệ tham khảo → không chặn cứng, chỉ xác nhận khi khác 100%.
    if (!this.costStructOk) {
      const d = this.costStructDelta;
      const lech = d > 0 ? `dư ${d}%` : `thiếu ${-d}%`;
      this.state.dialog = {
        kind: "confirm",
        title: "Tổng cơ cấu giá chưa bằng 100%",
        msg:
          `Tổng 5 thành phần cơ cấu giá đang là ${this.costStructTotal}% (${lech} so với 100%). ` +
          `Đây là tỷ lệ tham khảo, không phải công thức cứng. Bạn vẫn muốn lưu?`,
        okLabel: "Vẫn lưu",
        onOk: () => this._commitCost(),
      };
      return;
    }
    this._commitCost();
  }
  async _commitCost() {
    if (!this.state.canEdit) {
      this.flash("Bạn không có quyền sửa cấu hình (chỉ Admin/CEO).");
      return;
    }
    try {
      // Server tự diff + ghi audit; trả về giá trị đã chuẩn hóa (nguồn sự thật).
      const res = await this.orm.call("dl.pricing.config", "save_tab1", [
        this.state.cost,
        this.state.waste.map((w) => ({ group: w.group, pct: w.pct })),
      ]);
      this.state.cost = { ...this.state.cost, ...res.cost };
      this.state.waste = res.waste;
      this.baseline.cost = clone(this.state.cost);
      this.baseline.waste = clone(this.state.waste);
      if (res.audit_new && res.audit_new.length) {
        this.state.audit = [...res.audit_new, ...this.state.audit];
        this.flash(
          "Đã lưu vào hệ thống. Áp dụng cho báo giá MỚI tạo; báo giá cũ giữ snapshot.",
        );
      } else {
        this.flash("Không có thay đổi để lưu.");
      }
    } catch (e) {
      const msg =
        (e && e.data && e.data.message) || (e && e.message) || "lỗi không xác định";
      this.flash("Lưu thất bại: " + msg);
    }
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
        const a = ls[i],
          b = ls[j];
        const aMax = a.vMax == null ? Infinity : a.vMax;
        const bMax = b.vMax == null ? Infinity : b.vMax;
        const lo = Math.max(a.vMin || 0, b.vMin || 0);
        const hi = Math.min(aMax, bMax);
        if (hi - lo > 0) {
          set.add(a.id);
          set.add(b.id);
        }
      }
    }
    return set;
  }
  hasOverlap(l) {
    return this.overlapIds.has(l.id);
  }
  get ceoBackupMissing() {
    return this.state.levels.some(
      (l) => l.active && l.role === "ceo" && !l.backup && !l.user,
    );
  }
  addLevel() {
    // Cấp mới mang id tạm; audit ghi ở server khi Lưu (không audit tức thời).
    const l = {
      id: nextTmpId(),
      name: "Cấp duyệt mới",
      vMin: 0,
      vMax: null,
      dMin: 0,
      dMax: 100,
      marginMin: null,
      role: "sales_manager",
      user: "",
      backup: "",
      mode: "sequential",
      sla: 4,
      note: "",
      active: true,
      pending: 0,
      priority: false,
    };
    this.state.levels = [...this.state.levels, l];
  }
  toggleLevel(l) {
    // Chỉ đổi trạng thái ở client; ghi DB + audit khi bấm Lưu ma trận.
    l.active = !l.active;
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
      kind: "confirm",
      danger: true,
      title: "Xóa cấp duyệt",
      msg: `Xóa cấp "${l.name}" khỏi ma trận? Thay đổi được ghi khi bấm Lưu ma trận.`,
      okLabel: "Xóa",
      onOk: () => {
        this.state.levels = this.state.levels.filter((x) => x.id !== l.id);
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
  async saveMatrix() {
    if (!this.state.canEdit) {
      this.flash("Bạn không có quyền sửa cấu hình (chỉ Admin/CEO).");
      return;
    }
    // Chặn cứng chồng chéo ngay ở client (server cũng kiểm tra lần nữa — EX-06).
    if (this.overlapIds.size) {
      this.state.dialog = {
        kind: "block",
        title: "Ngưỡng giá trị bị chồng chéo",
        msg: "Có cấp duyệt trùng khoảng giá trị (highlight đỏ). Một khoảng giá không được thuộc 2 cấp. Hãy điều chỉnh để không chồng chéo trước khi lưu.",
      };
      return;
    }
    try {
      // Gửi trọn ma trận theo thứ tự hiện tại; id số = cấp cũ, "tmp-*" = cấp mới.
      const payload = this.state.levels.map((l) => ({
        id: typeof l.id === "number" ? l.id : 0,
        name: l.name,
        vMin: l.vMin,
        vMax: l.vMax,
        dMin: l.dMin,
        dMax: l.dMax,
        marginMin: l.marginMin,
        role: l.role,
        user: l.user ? Number(l.user) : 0,
        backup: l.backup ? Number(l.backup) : 0,
        mode: l.mode,
        sla: l.sla,
        note: l.note,
        active: l.active,
        priority: l.priority,
      }));
      const res = await this.orm.call("dl.pricing.config", "save_tab2", [payload]);
      this.state.levels = res.levels; // server là nguồn sự thật (id thật cho cấp mới)
      if (res.audit_new && res.audit_new.length) {
        this.state.audit = [...res.audit_new, ...this.state.audit];
        this.flash(
          "Đã lưu ma trận. BG đang Pending giữ nguyên cấp cũ; BG mới định tuyến theo ma trận mới.",
        );
      } else {
        this.flash("Không có thay đổi để lưu.");
      }
    } catch (e) {
      const msg =
        (e && e.data && e.data.message) || (e && e.message) || "lỗi không xác định";
      this.flash("Lưu thất bại: " + msg);
    }
  }

  // --- Tab 3: SLA & Escalation -------------------------------------------
  async saveSla() {
    const s = this.state.sla;
    if (s.salesManager < 1 || s.ceo < 1 || s.reminderEvery < 1) {
      this.state.dialog = {
        kind: "block",
        title: "SLA không hợp lệ",
        msg: "SLA và tần suất nhắc phải ≥ 1 giờ làm việc.",
      };
      return;
    }
    if (!this.state.canEdit) {
      this.flash("Bạn không có quyền sửa cấu hình (chỉ Admin/CEO).");
      return;
    }
    try {
      // Server tự diff + ghi audit; trả về giá trị đã chuẩn hóa (nguồn sự thật).
      const res = await this.orm.call("dl.pricing.config", "save_tab3", [
        {
          salesManager: s.salesManager,
          ceo: s.ceo,
          reminderEvery: s.reminderEvery,
          requireLateReason: s.requireLateReason,
          onOverdue: {
            remind: s.onOverdue.remind,
            escalate: s.onOverdue.escalate,
            log: s.onOverdue.log,
            kpi: s.onOverdue.kpi,
          },
        },
      ]);
      this.state.sla = { ...this.state.sla, ...res.sla };
      this.baseline.sla = clone(this.state.sla);
      if (res.audit_new && res.audit_new.length) {
        this.state.audit = [...res.audit_new, ...this.state.audit];
        this.flash(
          "Đã lưu SLA. Áp dụng cho các bước duyệt MỚI bắt đầu sau thời điểm lưu.",
        );
      } else {
        this.flash("Không có thay đổi để lưu.");
      }
    } catch (e) {
      const msg =
        (e && e.data && e.data.message) || (e && e.message) || "lỗi không xác định";
      this.flash("Lưu thất bại: " + msg);
    }
  }

  // --- Tab 4: Parametric --------------------------------------------------
  saveParam() {
    const entries = this._diffScalars(
      this.state.parametric,
      this.baseline.parametric,
      PARAM_LABELS,
    );
    ["kgm", "paint", "aux"].forEach((k) => {
      if (
        JSON.stringify(this.state.parametric[k]) !==
        JSON.stringify(this.baseline.parametric[k])
      ) {
        const lbl = {
          kgm: "Định mức kg/m theo quy cách",
          paint: "Định mức phủ sơn",
          aux: "Định mức vật tư phụ",
        };
        entries.push({ param: lbl[k], detail: "Đã cập nhật bảng" });
      }
    });
    if (!entries.length) {
      this.flash("Không có thay đổi để lưu.");
      return;
    }
    this._pushAudit("Tham số Parametric", entries);
    this.baseline.parametric = clone(this.state.parametric);
    this.flash(
      "Đã lưu tham số parametric. Áp dụng cho BOM / báo giá tính MỚI.",
    );
  }
  addRow(tableKey) {
    const p = this.state.parametric;
    if (tableKey === "kgm") {
      p.kgm = [...p.kgm, { spec: "Quy cách mới", val: 0 }];
    }
    if (tableKey === "paint") {
      p.paint = [...p.paint, { type: "Loại sơn mới", val: 0 }];
    }
    if (tableKey === "aux") {
      p.aux = [...p.aux, { name: "Vật tư phụ", qty: 0, unit: "cái/sp" }];
    }
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
