# -*- coding: utf-8 -*-
# ============================================================================
#  res.users — Backup Approver + service quản lý User cho màn "Quản lý User".
#
#  dl_group_admin KHÔNG phải nhóm Settings của Odoo, nên không thể tạo user /
#  ghi groups_id trực tiếp. Vì vậy mọi thao tác quản trị user đi qua service
#  có guard Admin DLM + sudo() — an toàn, không cho user thường leo thang.
# ============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

RBAC_CATEGORY_XMLID = "dl_base.module_category_dl_rbac"


class ResUsers(models.Model):
    _inherit = "res.users"

    dl_backup_approver_id = fields.Many2one(
        "res.users",
        string="Người duyệt dự phòng",
        help="Dùng khi user vắng / quá SLA — ảnh hưởng Escalation phê duyệt (IP-02).",
    )

    # ------------------------------------------------------------------ Guard
    @api.model
    def _check_dlm_admin(self):
        if not self.env.user.has_group("dl_base.dl_group_admin"):
            raise AccessError(_("Chỉ Admin/IT mới được quản lý tài khoản người dùng."))

    @api.model
    def _dlm_role_group_ids(self):
        cat = self.env.ref(RBAC_CATEGORY_XMLID)
        return set(
            self.env["res.groups"].sudo().search([("category_id", "=", cat.id)]).ids
        )

    # ------------------------------------------------------------------- Đọc
    @api.model
    def dlm_list_users(self):
        """Danh sách user nội bộ + vai trò DLM của họ (kèm user đã khóa)."""
        self._check_dlm_admin()
        role_ids = self._dlm_role_group_ids()
        # Ẩn các tài khoản kỹ thuật (OdooBot, template) — chỉ hiện user nghiệp vụ.
        excluded = []
        for xmlid in ("base.user_root", "base.default_user"):
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec:
                excluded.append(rec.id)
        users = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [("share", "=", False), ("id", "not in", excluded)], order="name"
            )
        )
        result = []
        for u in users:
            roles = [
                {"id": g.id, "name": g.name}
                for g in u.groups_id
                if g.id in role_ids
            ]
            result.append(
                {
                    "id": u.id,
                    "name": u.name,
                    "login": u.login,
                    "email": u.email or "",
                    "phone": u.phone or "",
                    "active": u.active,
                    "is_self": u.id == self.env.user.id,
                    "login_date": (
                        fields.Datetime.to_string(u.login_date) if u.login_date else ""
                    ),
                    "roles": roles,
                    "backup_id": u.dl_backup_approver_id.id or False,
                    "backup_name": u.dl_backup_approver_id.name or "",
                }
            )
        return result

    # ------------------------------------------------------------------- Ghi
    @api.model
    def dlm_create_user(self, vals):
        self._check_dlm_admin()
        name = (vals.get("name") or "").strip()
        login = (vals.get("login") or vals.get("email") or "").strip()
        if not name or not login:
            raise ValidationError(_("Họ tên và Email/Username là bắt buộc."))
        if self.sudo().with_context(active_test=False).search_count([("login", "=", login)]):
            raise ValidationError(_("Login/email '%s' đã tồn tại.") % login)
        role_ids = [gid for gid in (vals.get("role_ids") or []) if gid in self._dlm_role_group_ids()]
        user = self.sudo().create(
            {
                "name": name,
                "login": login,
                "email": vals.get("email") or login,
                "phone": vals.get("phone") or False,
                "groups_id": [(4, gid) for gid in role_ids],
            }
        )
        # Gửi email mời đặt mật khẩu (bỏ qua nếu chưa cấu hình mail server).
        try:
            user.sudo().action_reset_password()
        except Exception:
            pass
        return user.id

    @api.model
    def dlm_set_active(self, user_id, active):
        self._check_dlm_admin()
        user = self.sudo().browse(user_id)
        if not active and user.id == self.env.user.id:
            raise ValidationError(_("Không thể tự khóa tài khoản đang đăng nhập."))
        user.write({"active": active})
        return True

    @api.model
    def dlm_set_roles(self, user_id, role_ids):
        """Gán lại toàn bộ vai trò DLM cho user (thay thế, không cộng dồn)."""
        self._check_dlm_admin()
        role_group_ids = self._dlm_role_group_ids()
        keep = [gid for gid in role_ids if gid in role_group_ids]
        user = self.sudo().browse(user_id)
        cmds = [(3, gid) for gid in user.groups_id.ids if gid in role_group_ids]
        cmds += [(4, gid) for gid in keep]
        user.write({"groups_id": cmds})
        return True

    @api.model
    def dlm_reset_password(self, user_id):
        self._check_dlm_admin()
        self.sudo().browse(user_id).action_reset_password()
        return True

    @api.model
    def dlm_set_backup(self, user_id, backup_id):
        self._check_dlm_admin()
        self.sudo().browse(user_id).write(
            {"dl_backup_approver_id": backup_id or False}
        )
        return True
