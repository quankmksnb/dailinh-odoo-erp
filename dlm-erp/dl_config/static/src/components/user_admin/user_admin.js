/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ============================================================================
// S01 — Quản lý User & Phân quyền (mock UI)
// Quản trị tài khoản, gán vai trò, khóa/mở khóa, reset mật khẩu, Backup Approver.
// Chỉ Admin truy cập. Đây là bản mock: dữ liệu in-memory, chưa gắn backend.
// ============================================================================

// --- Vai trò & phòng ban ----------------------------------------------------
const ROLES = [
    { key: "admin", label: "Admin", dept: "Ban giám đốc", approver: false },
    { key: "ceo", label: "CEO", dept: "Ban giám đốc", approver: true },
    { key: "sales_manager", label: "Trưởng KD", dept: "Kinh doanh", approver: true },
    { key: "sales", label: "Sales", dept: "Kinh doanh", approver: false },
    { key: "tech", label: "Kỹ thuật", dept: "Kỹ thuật", approver: false },
    { key: "accountant", label: "Kế toán", dept: "Kế toán", approver: false },
];
const ROLE_MAP = Object.fromEntries(ROLES.map((r) => [r.key, r]));

// --- Quyền theo màn hình (trích ma trận đặc tả) — hiển thị ở chi tiết user ---
const SCREENS = [
    { code: "S01", name: "User & Phân quyền" },
    { code: "S02", name: "Cấu hình Hệ thống" },
    { code: "S03", name: "Khách hàng" },
    { code: "S04", name: "Nhà cung cấp" },
    { code: "S05", name: "Sản phẩm" },
    { code: "S06", name: "Bảng giá Vật tư" },
    { code: "S07", name: "RFQ" },
    { code: "S08", name: "BOM & BOM Mẫu" },
    { code: "S09", name: "Báo giá" },
    { code: "S10", name: "Phê duyệt Báo giá" },
    { code: "S11", name: "Dashboard CEO" },
];
const ROLE_PERMS = {
    admin: { S01: "Full", S02: "Full", S03: "Full", S04: "Full", S05: "Full", S06: "Full", S07: "Full", S08: "Full", S09: "Full", S10: "View", S11: "Full" },
    ceo: { S02: "Full", S03: "View", S04: "View", S05: "View", S06: "View", S07: "View", S08: "View", S09: "View", S10: "Full", S11: "Full" },
    sales_manager: { S02: "View", S03: "Full", S04: "View", S05: "Full", S06: "View", S07: "Full", S08: "View", S09: "Full", S10: "L1", S11: "Limited" },
    sales: { S03: "Full", S05: "View", S07: "Full", S09: "Full" },
    tech: { S05: "View", S06: "View", S07: "View", S08: "Full" },
    accountant: { S04: "Full", S06: "Full" },
};

// --- Nhãn quyền → mô tả ngắn ------------------------------------------------
const PERM_HINT = {
    Full: "Xem + Tạo + Sửa + Xóa/Vô hiệu",
    View: "Chỉ xem (read-only)",
    L1: "Duyệt cấp 1 (Trưởng KD)",
    Limited: "Xem một phần số liệu",
};

// --- Dữ liệu user mẫu -------------------------------------------------------
let _uid = 100;
const nextUid = () => `u${++_uid}`;

const SEED_USERS = [
    {
        id: "u1", name: "Nguyễn Quốc An", email: "admin@dailinh.vn", phone: "0901 000 001",
        role: "admin", active: true, createdAt: "01/01/2026", lastLogin: "06/07/2026 08:12",
        backup: null, pending: 0,
        audit: [
            { time: "01/01/2026 09:00", action: "Tạo tài khoản", detail: "Khởi tạo hệ thống" },
        ],
    },
    {
        id: "u2", name: "Trần Thị Bích", email: "ceo@dailinh.vn", phone: "0901 000 002",
        role: "ceo", active: true, createdAt: "01/01/2026", lastLogin: "06/07/2026 07:40",
        backup: "u3", pending: 2,
        audit: [
            { time: "01/01/2026 09:05", action: "Tạo tài khoản", detail: "Vai trò: CEO" },
            { time: "12/03/2026 14:20", action: "Gán Backup Approver", detail: "→ Lê Văn Cường (Trưởng KD)" },
        ],
    },
    {
        id: "u3", name: "Lê Văn Cường", email: "truongkd@dailinh.vn", phone: "0901 000 003",
        role: "sales_manager", active: true, createdAt: "02/01/2026", lastLogin: "06/07/2026 08:55",
        backup: "u2", pending: 3,
        audit: [
            { time: "02/01/2026 10:00", action: "Tạo tài khoản", detail: "Vai trò: Trưởng KD" },
        ],
    },
    {
        id: "u4", name: "Phạm Minh Dũng", email: "sales1@dailinh.vn", phone: "0901 000 004",
        role: "sales", active: true, createdAt: "05/01/2026", lastLogin: "05/07/2026 17:30",
        backup: null, pending: 0,
        audit: [
            { time: "05/01/2026 11:00", action: "Tạo tài khoản", detail: "Vai trò: Sales" },
        ],
    },
    {
        id: "u5", name: "Hoàng Thị Em", email: "sales2@dailinh.vn", phone: "0901 000 005",
        role: "sales", active: false, createdAt: "05/01/2026", lastLogin: "20/05/2026 09:10",
        backup: null, pending: 0,
        audit: [
            { time: "05/01/2026 11:05", action: "Tạo tài khoản", detail: "Vai trò: Sales" },
            { time: "01/06/2026 16:00", action: "Khóa tài khoản", detail: "Nghỉ thai sản" },
        ],
    },
    {
        id: "u6", name: "Vũ Đức Giang", email: "kythuat@dailinh.vn", phone: "0901 000 006",
        role: "tech", active: true, createdAt: "06/01/2026", lastLogin: "06/07/2026 08:00",
        backup: null, pending: 0,
        audit: [
            { time: "06/01/2026 09:30", action: "Tạo tài khoản", detail: "Vai trò: Kỹ thuật" },
        ],
    },
    {
        id: "u7", name: "Đỗ Thị Hoa", email: "ketoan@dailinh.vn", phone: "0901 000 007",
        role: "accountant", active: true, createdAt: "06/01/2026", lastLogin: "06/07/2026 07:58",
        backup: null, pending: 0,
        audit: [
            { time: "06/01/2026 09:35", action: "Tạo tài khoản", detail: "Vai trò: Kế toán" },
        ],
    },
];

const now = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

export class DlUserAdmin extends Component {
    static template = "dl_config.DlUserAdmin";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.roles = ROLES;
        this.screens = SCREENS;
        this.permHint = PERM_HINT;

        this.state = useState({
            users: SEED_USERS.map((u) => ({ ...u })),
            search: "",
            roleFilter: "",
            statusFilter: "",
            selectedId: "u1",
            toast: null,
            // form tạo user
            createOpen: false,
            form: this._blankForm(),
            // hộp thoại xác nhận/cảnh báo: { kind, title, msg, onOk, okLabel, danger }
            dialog: null,
        });
    }

    _blankForm() {
        return { name: "", email: "", phone: "", role: "sales" };
    }

    // --- Helpers ------------------------------------------------------------
    roleLabel(key) {
        return ROLE_MAP[key] ? ROLE_MAP[key].label : key;
    }
    roleDept(key) {
        return ROLE_MAP[key] ? ROLE_MAP[key].dept : "";
    }
    isApprover(key) {
        return !!(ROLE_MAP[key] && ROLE_MAP[key].approver);
    }
    userById(id) {
        return this.state.users.find((u) => u.id === id) || null;
    }
    activeCountByRole(role) {
        return this.state.users.filter((u) => u.role === role && u.active).length;
    }

    get selectedUser() {
        return this.userById(this.state.selectedId);
    }

    get filteredUsers() {
        const q = this.state.search.trim().toLowerCase();
        return this.state.users.filter((u) => {
            if (q && !(`${u.name} ${u.email}`.toLowerCase().includes(q))) {
                return false;
            }
            if (this.state.roleFilter && u.role !== this.state.roleFilter) {
                return false;
            }
            if (this.state.statusFilter === "active" && !u.active) {
                return false;
            }
            if (this.state.statusFilter === "locked" && u.active) {
                return false;
            }
            return true;
        });
    }

    // Quyền theo màn của user đang chọn (danh sách quyền tương ứng vai trò).
    get selectedPerms() {
        const u = this.selectedUser;
        if (!u) {
            return [];
        }
        const map = ROLE_PERMS[u.role] || {};
        return SCREENS.filter((s) => map[s.code]).map((s) => ({
            code: s.code,
            name: s.name,
            level: map[s.code],
            hint: PERM_HINT[map[s.code]] || "",
        }));
    }

    // Ứng viên Backup Approver: user active có vai trò approver, khác chính user.
    get backupCandidates() {
        const u = this.selectedUser;
        return this.state.users.filter(
            (c) => c.active && this.isApprover(c.role) && (!u || c.id !== u.id)
        );
    }

    // --- Điều hướng list ----------------------------------------------------
    selectUser(id) {
        this.state.selectedId = id;
    }

    flash(msg) {
        this.state.toast = msg;
        clearTimeout(this._toastT);
        this._toastT = setTimeout(() => (this.state.toast = null), 3200);
    }

    _addAudit(user, action, detail) {
        user.audit = [{ time: now(), action, detail }, ...user.audit];
    }

    // --- Tạo user -----------------------------------------------------------
    openCreate() {
        this.state.form = this._blankForm();
        this.state.createOpen = true;
    }
    closeCreate() {
        this.state.createOpen = false;
    }
    get createValid() {
        const f = this.state.form;
        const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim());
        return f.name.trim().length > 1 && emailOk && !!f.role;
    }
    get createEmailDup() {
        const e = this.state.form.email.trim().toLowerCase();
        return !!e && this.state.users.some((u) => u.email.toLowerCase() === e);
    }
    submitCreate() {
        if (!this.createValid || this.createEmailDup) {
            return;
        }
        const f = this.state.form;
        const u = {
            id: nextUid(),
            name: f.name.trim(),
            email: f.email.trim(),
            phone: f.phone.trim(),
            role: f.role,
            active: true,
            createdAt: now().split(" ")[0],
            lastLogin: "—",
            backup: null,
            pending: 0,
            audit: [{ time: now(), action: "Tạo tài khoản", detail: `Vai trò: ${this.roleLabel(f.role)}` }],
        };
        this.state.users = [u, ...this.state.users];
        this.state.selectedId = u.id;
        this.state.createOpen = false;
        this.flash(`Đã tạo user "${u.name}". Hệ thống đã gửi email mời đặt mật khẩu.`);
    }

    // --- Đổi vai trò --------------------------------------------------------
    onChangeRole(ev) {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        const newRole = ev.target.value;
        const oldRole = u.role;
        if (newRole === oldRole) {
            return;
        }
        // EX-23: đổi role người duyệt đang có BG Pending → cảnh báo escalate.
        if (this.isApprover(oldRole) && !this.isApprover(newRole) && u.pending > 0) {
            ev.target.value = oldRole; // giữ nguyên select tới khi xác nhận
            this.state.dialog = {
                kind: "confirm",
                danger: true,
                title: "Đổi vai trò người đang duyệt",
                msg: `${u.name} đang có ${u.pending} báo giá chờ duyệt. Đổi sang "${this.roleLabel(newRole)}" sẽ Escalate các báo giá đó lên cấp trên / Backup Approver. Bạn có chắc?`,
                okLabel: "Xác nhận đổi",
                onOk: () => this._applyRole(u, oldRole, newRole, true),
            };
            return;
        }
        this._applyRole(u, oldRole, newRole, false);
    }
    _applyRole(u, oldRole, newRole, escalated) {
        u.role = newRole;
        if (!this.isApprover(newRole)) {
            u.backup = null;
        }
        this._addAudit(u, "Đổi vai trò", `${this.roleLabel(oldRole)} → ${this.roleLabel(newRole)}`);
        if (escalated) {
            this._addAudit(u, "Escalate báo giá", `${u.pending} BG chờ duyệt → chuyển Backup/cấp trên`);
            u.pending = 0;
        }
        this.flash(`Đã đổi vai trò ${u.name} thành ${this.roleLabel(newRole)}.`);
    }

    // --- Khóa / Mở khóa -----------------------------------------------------
    toggleLock() {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        if (u.active) {
            this._tryLock(u);
        } else {
            u.active = true;
            this._addAudit(u, "Mở khóa tài khoản", "Kích hoạt lại");
            this.flash(`Đã mở khóa ${u.name}.`);
        }
    }
    _tryLock(u) {
        // EX-21: admin duy nhất không được tự khóa.
        if (u.role === "admin" && this.activeCountByRole("admin") <= 1) {
            this.state.dialog = {
                kind: "block",
                title: "Không thể khóa",
                msg: "Đây là Admin duy nhất đang hoạt động. Hãy tạo Admin khác trước khi khóa tài khoản này.",
            };
            return;
        }
        // EX-28: CEO cuối cùng không được khóa.
        if (u.role === "ceo" && this.activeCountByRole("ceo") <= 1) {
            this.state.dialog = {
                kind: "block",
                title: "Không thể khóa",
                msg: "Phải còn ít nhất 1 CEO đang hoạt động trong hệ thống.",
            };
            return;
        }
        // EX-22: khóa người duyệt đang có BG Pending → cảnh báo escalate.
        if (this.isApprover(u.role) && u.pending > 0) {
            const bk = u.backup ? this.roleLabel(this.userById(u.backup)?.role) + " — " + (this.userById(u.backup)?.name || "") : "Backup Approver";
            this.state.dialog = {
                kind: "confirm",
                danger: true,
                title: "User đang có báo giá chờ duyệt",
                msg: `${u.name} đang có ${u.pending} báo giá chờ duyệt. Hệ thống sẽ tự Escalate sang ${bk}. Bạn có chắc muốn khóa?`,
                okLabel: "Khóa & Escalate",
                onOk: () => this._doLock(u, true),
            };
            return;
        }
        this.state.dialog = {
            kind: "confirm",
            danger: true,
            title: "Khóa tài khoản",
            msg: `Khóa tài khoản ${u.name}? User sẽ không thể đăng nhập, nhưng dữ liệu vẫn được giữ nguyên.`,
            okLabel: "Khóa",
            onOk: () => this._doLock(u, false),
        };
    }
    _doLock(u, escalated) {
        u.active = false;
        this._addAudit(u, "Khóa tài khoản", escalated ? "Kèm Escalate BG đang chờ duyệt" : "Vô hiệu hóa đăng nhập");
        if (escalated) {
            this._addAudit(u, "Escalate báo giá", `${u.pending} BG → Backup Approver`);
            u.pending = 0;
        }
        this.flash(`Đã khóa ${u.name}.`);
    }

    // --- Reset mật khẩu -----------------------------------------------------
    resetPassword() {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        this._addAudit(u, "Reset mật khẩu", "Gửi email đặt lại mật khẩu");
        this.flash(`Đã gửi email đặt lại mật khẩu cho ${u.email}.`);
    }

    // --- Backup Approver ----------------------------------------------------
    onChangeBackup(ev) {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        const id = ev.target.value || null;
        u.backup = id;
        const name = id ? this.userById(id)?.name : "(không có)";
        this._addAudit(u, "Gán Backup Approver", `→ ${name}`);
        this.flash(`Đã cập nhật Backup Approver cho ${u.name}.`);
    }
    backupName(id) {
        const u = this.userById(id);
        return u ? `${u.name} (${this.roleLabel(u.role)})` : "—";
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

    onFormInput(field, ev) {
        this.state.form[field] = ev.target.value;
    }
}

registry.category("actions").add("dl_config.DlUserAdmin", DlUserAdmin);
