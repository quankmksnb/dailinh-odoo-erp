# -*- coding: utf-8 -*-
# ============================================================================
#  RBAC DLM-ERP — Danh mục chức năng + Service phân quyền (native Odoo).
#
#  Triết lý bảo mật: KHÔNG dựng hệ quyền song song. Tầng thực thi thật sự là
#  ORM của Odoo:
#    • Xem/Thêm/Sửa/Xóa  → ir.model.access (perm_read/create/write/unlink).
#    • Thao tác đặc biệt   → mỗi thao tác gắn 1 res.groups kỹ thuật; nút/field
#                            trong view gán groups="..."; tick = thêm vào
#                            implied_ids của vai trò.
#    • Vai trò             → res.groups nằm trong category module_category_dl_rbac.
#
#  Model dl.rbac.feature/operation chỉ là DANH MỤC tham chiếu (khai báo bởi
#  từng module). Mọi thao tác GHI đi qua service method có guard Admin + sudo,
#  nên user thường không thể tự sửa ACL kể cả gọi thẳng qua RPC.
# ============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Category (ir.module.category) đánh dấu "nhóm nào là vai trò DLM".
RBAC_CATEGORY_XMLID = "dl_base.module_category_dl_rbac"
# Tiền tố tên khi màn phân quyền TỰ tạo dòng ir.model.access mới cho (model, role).
MANAGED_ACCESS_PREFIX = "dl_rbac_"


class DlRbacFeature(models.Model):
    """Một 'chức năng/màn hình' có thể phân quyền. Mỗi module khai báo record
    của mình trong data/rbac_features.xml ⇒ chức năng mới TỰ hiện trong ma trận."""

    _name = "dl.rbac.feature"
    _description = "RBAC — Chức năng phân quyền"
    _order = "sequence, category, name"

    name = fields.Char("Tên chức năng", required=True)
    code = fields.Char("Mã", required=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Model dữ liệu",
        ondelete="cascade",
        help="Model backing cho quyền Xem/Thêm/Sửa/Xóa. Để trống với màn thuần "
        "action (chưa có model) — khi đó chỉ cấu hình thao tác đặc biệt.",
    )
    model_name = fields.Char(related="model_id.model", store=True, string="Tên kỹ thuật")
    category = fields.Selection(
        [
            ("master", "Dữ liệu danh mục"),
            ("sales", "Kinh doanh & Báo giá"),
            ("approval", "Phê duyệt"),
            ("system", "Hệ thống & phân quyền"),
        ],
        string="Nhóm",
        default="system",
        required=True,
    )
    sequence = fields.Integer("Thứ tự", default=10)
    active = fields.Boolean("Đang dùng", default=True)
    operation_ids = fields.One2many(
        "dl.rbac.operation", "feature_id", string="Thao tác đặc biệt"
    )

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Mã chức năng phải là duy nhất."),
    ]

    # ------------------------------------------------------------------ Guard
    @api.model
    def _check_rbac_admin(self):
        """Chỉ Admin/IT được cấu hình phân quyền. Gọi ĐẦU mọi service ghi."""
        if not self.env.user.has_group("dl_base.dl_group_admin"):
            raise AccessError(_("Chỉ Admin/IT mới được cấu hình phân quyền."))

    @api.model
    def _rbac_category(self):
        return self.env.ref(RBAC_CATEGORY_XMLID)

    # ------------------------------------------------------- Vai trò (res.groups)
    @api.model
    def list_roles(self):
        """Danh sách vai trò DLM (res.groups trong category RBAC)."""
        self._check_rbac_admin()
        cat = self._rbac_category()
        groups = (
            self.env["res.groups"]
            .sudo()
            .search([("category_id", "=", cat.id)], order="name")
        )
        return [
            {
                "id": g.id,
                "name": g.name,
                "comment": g.comment or "",
                "user_count": len(g.users),
                "system": bool(self.sudo()._role_xmlid(g)),
            }
            for g in groups
        ]

    @api.model
    def _role_xmlid(self, group):
        """External id của group nếu do module cài đặt (⇒ vai trò 'hệ thống',
        không cho xóa để tránh vỡ menu/tham chiếu)."""
        data = self.env["ir.model.data"].sudo().search(
            [("model", "=", "res.groups"), ("res_id", "=", group.id)], limit=1
        )
        return data.complete_name if data else False

    @api.model
    def create_role(self, name, comment=False):
        self._check_rbac_admin()
        name = (name or "").strip()
        if not name:
            raise ValidationError(_("Tên vai trò không được để trống."))
        cat = self._rbac_category()
        exists = self.env["res.groups"].sudo().search_count(
            [("category_id", "=", cat.id), ("name", "=ilike", name)]
        )
        if exists:
            raise ValidationError(_("Đã tồn tại vai trò tên '%s'.") % name)
        group = self.env["res.groups"].sudo().create(
            {
                "name": name,
                "comment": comment or False,
                "category_id": cat.id,
                # Mọi vai trò đều kế thừa quyền đăng nhập nội bộ.
                "implied_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        return group.id

    @api.model
    def rename_role(self, group_id, name, comment=False):
        self._check_rbac_admin()
        name = (name or "").strip()
        if not name:
            raise ValidationError(_("Tên vai trò không được để trống."))
        self.env["res.groups"].sudo().browse(group_id).write(
            {"name": name, "comment": comment or False}
        )
        return True

    @api.model
    def delete_role(self, group_id):
        """Chỉ cho xóa vai trò do Admin tạo (không có external id)."""
        self._check_rbac_admin()
        group = self.env["res.groups"].sudo().browse(group_id)
        if self._role_xmlid(group):
            raise ValidationError(
                _("Không thể xóa vai trò hệ thống '%s'. Chỉ xóa được vai trò do "
                  "Admin tự tạo.") % group.name
            )
        group.unlink()
        return True

    # --------------------------------------------------- Ma trận quyền (đọc)
    @api.model
    def get_role_matrix(self, group_id):
        """Trả về toàn bộ feature + trạng thái CRUD/operation của 1 vai trò."""
        self._check_rbac_admin()
        group = self.env["res.groups"].sudo().browse(group_id)
        implied = set(group.implied_ids.ids)
        features = self.sudo().search([])
        result = []
        for f in features:
            crud = {"read": False, "create": False, "write": False, "unlink": False}
            if f.model_id:
                acc = self._access_row(f.model_id.id, group_id)
                if acc:
                    crud = {
                        "read": acc.perm_read,
                        "create": acc.perm_create,
                        "write": acc.perm_write,
                        "unlink": acc.perm_unlink,
                    }
            ops = [
                {
                    "id": op.id,
                    "name": op.name,
                    "code": op.code,
                    "group_id": op.group_id.id,
                    "enabled": op.group_id.id in implied,
                }
                for op in f.operation_ids
                if op.group_id
            ]
            result.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "code": f.code,
                    "category": f.category,
                    "has_model": bool(f.model_id),
                    "crud": crud,
                    "operations": ops,
                }
            )
        return result

    # --------------------------------------------------- Ma trận quyền (ghi)
    @api.model
    def _access_row(self, model_id, group_id):
        """Dòng ir.model.access THẬT của (model, vai trò) — chính là dòng mà
        matrix đọc/ghi để phản ánh & thu hồi quyền thật sự. Ưu tiên dòng do
        matrix tạo (tiền tố dl_rbac_), nếu chưa có thì lấy dòng ACL bất kỳ đang
        có cho (model, group) để chỉnh trực tiếp."""
        rows = self.env["ir.model.access"].sudo().search(
            [("model_id", "=", model_id), ("group_id", "=", group_id)]
        )
        if not rows:
            return rows
        managed = rows.filtered(lambda r: (r.name or "").startswith(MANAGED_ACCESS_PREFIX))
        return (managed or rows)[:1]

    @api.model
    def set_crud(self, group_id, feature_id, perms):
        """Bật/tắt quyền Xem/Thêm/Sửa/Xóa của 1 vai trò trên 1 chức năng.
        Ghi thẳng vào dòng ir.model.access của (model, vai trò) — nên bỏ tick
        là THU HỒI thật ở tầng ORM (không chỉ ẩn nút)."""
        self._check_rbac_admin()
        feature = self.browse(feature_id)
        if not feature.model_id:
            raise ValidationError(
                _("Chức năng '%s' chưa gắn model dữ liệu nên không thể cấu hình "
                  "quyền Xem/Thêm/Sửa/Xóa.") % feature.name
            )
        vals = {
            "perm_read": bool(perms.get("read")),
            "perm_create": bool(perms.get("create")),
            "perm_write": bool(perms.get("write")),
            "perm_unlink": bool(perms.get("unlink")),
        }
        acc = self._access_row(feature.model_id.id, group_id)
        if acc:
            acc.write(vals)
        else:
            name = "%s%s_%s" % (
                MANAGED_ACCESS_PREFIX,
                feature.model_id.model.replace(".", "_"),
                group_id,
            )
            self.env["ir.model.access"].sudo().create(
                {
                    "name": name,
                    "model_id": feature.model_id.id,
                    "group_id": group_id,
                    **vals,
                }
            )
        return True

    @api.model
    def set_operation(self, group_id, op_group_id, enabled):
        """Bật/tắt 1 thao tác đặc biệt cho vai trò (qua implied_ids)."""
        self._check_rbac_admin()
        group = self.env["res.groups"].sudo().browse(group_id)
        if enabled:
            group.write({"implied_ids": [(4, op_group_id)]})
        else:
            group.write({"implied_ids": [(3, op_group_id)]})
        # Đồng bộ lại thành viên của op-group: gỡ implied KHÔNG tự thu hồi
        # membership đã lan xuống user, nên phải resync để thu hồi thật sự.
        self._resync_operation_membership(op_group_id)
        return True

    @api.model
    def _resync_operation_membership(self, op_group_id):
        """Op-group chỉ được cấp GIÁN TIẾP qua vai trò. Đồng bộ lại users của
        op-group = union users của mọi vai trò đang implied nó — bảo đảm thu
        hồi đúng khi tắt quyền."""
        op_group = self.env["res.groups"].sudo().browse(op_group_id)
        roles = self.env["res.groups"].sudo().search(
            [("implied_ids", "in", op_group_id)]
        )
        should_have = roles.mapped("users")
        current = op_group.users
        to_remove = current - should_have
        to_add = should_have - current
        cmds = [(3, u.id) for u in to_remove] + [(4, u.id) for u in to_add]
        if cmds:
            op_group.write({"users": cmds})


class DlRbacOperation(models.Model):
    """Một thao tác đặc biệt (duyệt / xuất file / khóa...) của 1 chức năng,
    được backing bởi 1 res.groups kỹ thuật để gate nút/field trong view."""

    _name = "dl.rbac.operation"
    _description = "RBAC — Thao tác đặc biệt"
    _order = "feature_id, sequence, name"

    feature_id = fields.Many2one(
        "dl.rbac.feature", string="Chức năng", required=True, ondelete="cascade"
    )
    name = fields.Char("Tên thao tác", required=True)
    code = fields.Char("Mã", required=True)
    sequence = fields.Integer("Thứ tự", default=10)
    group_id = fields.Many2one(
        "res.groups",
        string="Nhóm kỹ thuật",
        required=True,
        ondelete="cascade",
        help="res.groups gate nút/field cho thao tác này (view gán groups=...).",
    )
