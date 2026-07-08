/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ============================================================================
//  Phân quyền Vai trò (RBAC) — màn RIÊNG, tách khỏi Quản lý User.
//  Ma trận Vai trò × Chức năng: tick Xem/Thêm/Sửa/Xóa (ir.model.access) +
//  thao tác đặc biệt (implied_ids op-group). Mọi thao tác gọi service server
//  của dl.rbac.feature (guard Admin + sudo) — nối DB THẬT, không mock.
// ============================================================================

const CATEGORIES = [
    { key: "master", label: "Dữ liệu danh mục" },
    { key: "sales", label: "Kinh doanh & Báo giá" },
    { key: "approval", label: "Phê duyệt" },
    { key: "system", label: "Hệ thống & phân quyền" },
];
const CRUD = [
    { key: "read", label: "Xem" },
    { key: "create", label: "Thêm" },
    { key: "write", label: "Sửa" },
    { key: "unlink", label: "Xóa" },
];
const MODEL = "dl.rbac.feature";

export class DlRolePerm extends Component {
    static template = "dl_config.DlRolePerm";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.crudCols = CRUD;
        this.state = useState({
            roles: [],
            selectedRoleId: null,
            matrix: [],
            loading: true,
            saving: false,
            toast: null,
            dialog: null, // { kind:'confirm'|'block', title, msg, danger, okLabel, onOk }
            createOpen: false,
            form: { name: "", comment: "" },
        });

        onWillStart(async () => {
            await this.loadRoles();
            if (this.state.roles.length) {
                await this.selectRole(this.state.roles[0].id);
            }
            this.state.loading = false;
        });
    }

    // --- Nạp dữ liệu --------------------------------------------------------
    async loadRoles() {
        this.state.roles = await this.orm.call(MODEL, "list_roles", []);
    }
    async selectRole(id) {
        this.state.selectedRoleId = id;
        this.state.matrix = await this.orm.call(MODEL, "get_role_matrix", [id]);
    }

    get selectedRole() {
        return this.state.roles.find((r) => r.id === this.state.selectedRoleId) || null;
    }
    get sections() {
        return CATEGORIES.map((c) => ({
            ...c,
            items: this.state.matrix.filter((f) => f.category === c.key),
        })).filter((s) => s.items.length);
    }

    flash(msg) {
        this.state.toast = msg;
        clearTimeout(this._t);
        this._t = setTimeout(() => (this.state.toast = null), 2600);
    }

    // --- Tick quyền CRUD ----------------------------------------------------
    async toggleCrud(feature, key) {
        if (!feature.has_model || this.state.saving) {
            return;
        }
        const perms = { ...feature.crud, [key]: !feature.crud[key] };
        this.state.saving = true;
        try {
            await this.orm.call(MODEL, "set_crud", [
                this.state.selectedRoleId,
                feature.id,
                perms,
            ]);
            feature.crud = perms;
        } catch (e) {
            this.showError(e);
        } finally {
            this.state.saving = false;
        }
    }

    // --- Tick thao tác đặc biệt --------------------------------------------
    async toggleOp(feature, op) {
        if (this.state.saving) {
            return;
        }
        const next = !op.enabled;
        this.state.saving = true;
        try {
            await this.orm.call(MODEL, "set_operation", [
                this.state.selectedRoleId,
                op.group_id,
                next,
            ]);
            op.enabled = next;
        } catch (e) {
            this.showError(e);
        } finally {
            this.state.saving = false;
        }
    }

    // --- Tạo / xóa vai trò --------------------------------------------------
    openCreate() {
        this.state.form = { name: "", comment: "" };
        this.state.createOpen = true;
    }
    closeCreate() {
        this.state.createOpen = false;
    }
    get createValid() {
        return this.state.form.name.trim().length > 1;
    }
    async submitCreate() {
        if (!this.createValid) {
            return;
        }
        const name = this.state.form.name.trim();
        const comment = this.state.form.comment.trim();
        this.state.createOpen = false;
        try {
            const id = await this.orm.call(MODEL, "create_role", [name, comment]);
            await this.loadRoles();
            await this.selectRole(id);
            this.flash(`Đã tạo vai trò "${name}".`);
        } catch (e) {
            this.showError(e);
        }
    }

    confirmDelete() {
        const r = this.selectedRole;
        if (!r) {
            return;
        }
        if (r.system) {
            this.state.dialog = {
                kind: "block",
                title: "Không thể xóa",
                msg: `"${r.name}" là vai trò hệ thống mặc định, không thể xóa.`,
            };
            return;
        }
        this.state.dialog = {
            kind: "confirm",
            danger: true,
            title: "Xóa vai trò",
            msg: `Xóa vai trò "${r.name}"? ${r.user_count} user đang gán sẽ mất vai trò này. Thao tác không thể hoàn tác.`,
            okLabel: "Xóa vai trò",
            onOk: async () => {
                await this.orm.call(MODEL, "delete_role", [r.id]);
                await this.loadRoles();
                const first = this.state.roles[0];
                if (first) {
                    await this.selectRole(first.id);
                } else {
                    this.state.selectedRoleId = null;
                    this.state.matrix = [];
                }
                this.flash("Đã xóa vai trò.");
            },
        };
    }

    // --- Dialog / lỗi -------------------------------------------------------
    showError(e) {
        const msg =
            (e && e.data && e.data.message) || (e && e.message) || "Có lỗi xảy ra.";
        this.state.dialog = { kind: "block", title: "Không thực hiện được", msg };
    }
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

registry.category("actions").add("dl_config.DlRolePerm", DlRolePerm);
