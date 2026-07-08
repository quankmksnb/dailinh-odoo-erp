/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ============================================================================
//  Quản lý User — nối DB THẬT (res.users) qua service dlm_* (guard Admin+sudo).
//  Phần PHÂN QUYỀN đã tách sang màn riêng "Phân quyền Vai trò" (DlRolePerm).
//  Màn này chỉ: tạo tài khoản, gán vai trò, khóa/mở, reset mật khẩu, Backup.
// ============================================================================

const USER_MODEL = "res.users";
const RBAC_MODEL = "dl.rbac.feature";

export class DlUserAdmin extends Component {
    static template = "dl_config.DlUserAdmin";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            users: [],
            roles: [], // vai trò DLM khả dụng: [{id, name}]
            search: "",
            roleFilter: "", // group id (string) hoặc ""
            statusFilter: "",
            selectedId: null,
            loading: true,
            saving: false,
            toast: null,
            dialog: null,
            createOpen: false,
            form: this._blankForm(),
        });

        onWillStart(async () => {
            await this._reload();
            this.state.loading = false;
        });
    }

    _blankForm() {
        return { name: "", email: "", phone: "", roleIds: [] };
    }

    async _reload(keepSelection = true) {
        const [users, roles] = await Promise.all([
            this.orm.call(USER_MODEL, "dlm_list_users", []),
            this.orm.call(RBAC_MODEL, "list_roles", []),
        ]);
        this.state.users = users;
        this.state.roles = roles;
        if (!keepSelection || !this.userById(this.state.selectedId)) {
            this.state.selectedId = users.length ? users[0].id : null;
        }
    }

    // --- Helpers ------------------------------------------------------------
    userById(id) {
        return this.state.users.find((u) => u.id === id) || null;
    }
    get selectedUser() {
        return this.userById(this.state.selectedId);
    }
    roleNames(u) {
        return u.roles.length ? u.roles.map((r) => r.name).join(", ") : "—";
    }
    hasRole(u, roleId) {
        return u.roles.some((r) => r.id === roleId);
    }
    get backupCandidates() {
        const u = this.selectedUser;
        return this.state.users.filter((c) => c.active && (!u || c.id !== u.id));
    }

    get filteredUsers() {
        const q = this.state.search.trim().toLowerCase();
        const rf = this.state.roleFilter ? parseInt(this.state.roleFilter, 10) : null;
        return this.state.users.filter((u) => {
            if (q && !`${u.name} ${u.login} ${u.email}`.toLowerCase().includes(q)) {
                return false;
            }
            if (rf && !this.hasRole(u, rf)) {
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

    selectUser(id) {
        this.state.selectedId = id;
    }

    flash(msg) {
        this.state.toast = msg;
        clearTimeout(this._t);
        this._t = setTimeout(() => (this.state.toast = null), 3000);
    }
    showError(e) {
        const msg =
            (e && e.data && e.data.message) || (e && e.message) || "Có lỗi xảy ra.";
        this.state.dialog = { kind: "block", title: "Không thực hiện được", msg };
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
        return f.name.trim().length > 1 && emailOk;
    }
    toggleFormRole(roleId) {
        const set = new Set(this.state.form.roleIds);
        set.has(roleId) ? set.delete(roleId) : set.add(roleId);
        this.state.form.roleIds = [...set];
    }
    async submitCreate() {
        if (!this.createValid) {
            return;
        }
        const f = this.state.form;
        this.state.createOpen = false;
        try {
            const id = await this.orm.call(USER_MODEL, "dlm_create_user", [
                {
                    name: f.name.trim(),
                    email: f.email.trim(),
                    phone: f.phone.trim(),
                    role_ids: f.roleIds,
                },
            ]);
            await this._reload(false);
            this.state.selectedId = id;
            this.flash(`Đã tạo user "${f.name.trim()}". Hệ thống đã gửi email mời đặt mật khẩu.`);
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Gán / gỡ vai trò ---------------------------------------------------
    async toggleRole(roleId) {
        const u = this.selectedUser;
        if (!u || this.state.saving) {
            return;
        }
        const next = this.hasRole(u, roleId)
            ? u.roles.filter((r) => r.id !== roleId).map((r) => r.id)
            : [...u.roles.map((r) => r.id), roleId];
        this.state.saving = true;
        try {
            await this.orm.call(USER_MODEL, "dlm_set_roles", [u.id, next]);
            u.roles = this.state.roles
                .filter((r) => next.includes(r.id))
                .map((r) => ({ id: r.id, name: r.name }));
            this.flash(`Đã cập nhật vai trò cho ${u.name}.`);
        } catch (e) {
            this.showError(e);
        } finally {
            this.state.saving = false;
        }
    }

    // --- Khóa / Mở khóa -----------------------------------------------------
    toggleLock() {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        if (!u.active) {
            this._setActive(u, true);
            return;
        }
        if (u.is_self) {
            this.state.dialog = {
                kind: "block",
                title: "Không thể khóa",
                msg: "Bạn không thể tự khóa tài khoản đang đăng nhập.",
            };
            return;
        }
        this.state.dialog = {
            kind: "confirm",
            danger: true,
            title: "Khóa tài khoản",
            msg: `Khóa tài khoản ${u.name}? User sẽ không đăng nhập được, dữ liệu vẫn giữ nguyên.`,
            okLabel: "Khóa",
            onOk: () => this._setActive(u, false),
        };
    }
    async _setActive(u, active) {
        try {
            await this.orm.call(USER_MODEL, "dlm_set_active", [u.id, active]);
            u.active = active;
            this.flash(active ? `Đã mở khóa ${u.name}.` : `Đã khóa ${u.name}.`);
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Reset mật khẩu -----------------------------------------------------
    async resetPassword() {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        try {
            await this.orm.call(USER_MODEL, "dlm_reset_password", [u.id]);
            this.flash(`Đã gửi email đặt lại mật khẩu cho ${u.email || u.login}.`);
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Backup Approver ----------------------------------------------------
    async onChangeBackup(ev) {
        const u = this.selectedUser;
        if (!u) {
            return;
        }
        const id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        try {
            await this.orm.call(USER_MODEL, "dlm_set_backup", [u.id, id]);
            u.backup_id = id || false;
            u.backup_name = id ? this.userById(id)?.name || "" : "";
            this.flash(`Đã cập nhật Backup Approver cho ${u.name}.`);
        } catch (e) {
            this.showError(e);
        }
    }

    // --- Dialog -------------------------------------------------------------
    async dialogOk() {
        const d = this.state.dialog;
        this.state.dialog = null;
        if (d && d.onOk) {
            try {
                await d.onOk();
            } catch (e) {
                this.showError(e);
            }
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
