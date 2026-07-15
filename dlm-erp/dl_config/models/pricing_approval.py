# -*- coding: utf-8 -*-
"""Màn hình 5 — Phê duyệt và lịch sử (đặc tả V3 mục 8).

Hệ thống có 4 loại yêu cầu cố định, mỗi yêu cầu có một cấp duyệt cuối. Không SLA,
không kênh email, không ủy quyền phức tạp, không biểu thức điều kiện tự do.
Người quản trị chỉ chọn vai trò/người duyệt tương ứng ở màn Cấu hình người duyệt.
"""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

# 4 loại yêu cầu cố định — mục 8.1.
APPROVAL_TYPE_SELECTION = [
    ("profit_config", "Cấu hình lợi nhuận mới"),
    ("discount_config", "Cấu hình chiết khấu mới"),
    ("quote_discount", "Chiết khấu báo giá vượt mặc định"),
    ("quote_below_floor", "Báo giá dưới giá sàn hoặc vượt trần"),
]

# Vai trò duyệt gợi ý — ánh xạ sang group trong dl_base.
APPROVER_ROLE_SELECTION = [
    ("sales_manager", "Trưởng kinh doanh"),
    ("ceo", "Giám đốc"),
]
_ROLE_GROUP = {
    "sales_manager": "dl_base.dl_group_sales_manager",
    "ceo": "dl_base.dl_group_ceo",
}


class DlPricingApprovalSetting(models.Model):
    _name = "dl.pricing.approval.setting"
    _description = "Cấu hình người duyệt theo loại yêu cầu"
    _order = "request_type"

    request_type = fields.Selection(
        APPROVAL_TYPE_SELECTION, string="Loại yêu cầu", required=True,
    )
    approver_role = fields.Selection(
        APPROVER_ROLE_SELECTION, string="Vai trò duyệt", required=True,
        default="ceo",
    )
    approver_user_id = fields.Many2one(
        "res.users", string="Người duyệt cụ thể",
        help="Để trống thì mọi người thuộc vai trò duyệt đều có thể duyệt.",
    )
    company_id = fields.Many2one(
        "res.company", string="Công ty", required=True, index=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "type_company_uniq",
            "unique(request_type, company_id)",
            "Mỗi loại yêu cầu chỉ có một cấu hình người duyệt trong công ty.",
        ),
    ]

    def _allowed_user_ids(self):
        """Tập user được phép duyệt loại yêu cầu này."""
        self.ensure_one()
        if self.approver_user_id:
            return self.approver_user_id.ids
        group = self.env.ref(_ROLE_GROUP[self.approver_role], raise_if_not_found=False)
        return group.users.ids if group else []


class DlPricingApprovalRequest(models.Model):
    _name = "dl.pricing.approval.request"
    _description = "Yêu cầu phê duyệt cấu hình thương mại / báo giá"
    _inherit = ["mail.thread"]
    _order = "create_date desc, id desc"
    _rec_name = "title"

    title = fields.Char("Tiêu đề", compute="_compute_title", store=True)
    request_type = fields.Selection(
        APPROVAL_TYPE_SELECTION, string="Loại yêu cầu", required=True, tracking=True,
    )
    res_model = fields.Char("Model đối tượng", readonly=True)
    res_id = fields.Integer("ID đối tượng", readonly=True)
    object_label = fields.Char("Đối tượng", readonly=True)
    old_value = fields.Char("Giá trị cũ", readonly=True)
    new_value = fields.Char("Giá trị mới", readonly=True)
    impact = fields.Char("Tác động", readonly=True)
    requester_id = fields.Many2one(
        "res.users", string="Người yêu cầu", readonly=True,
        default=lambda self: self.env.user,
    )
    requester_role = fields.Char("Vai trò khi gửi", readonly=True)
    reason = fields.Text("Lý do", required=True, tracking=True)
    resolved_by_id = fields.Many2one("res.users", string="Người duyệt", readonly=True)
    resolved_at = fields.Datetime("Thời điểm xử lý", readonly=True)
    reject_comment = fields.Text(
        "Lý do từ chối",
        help="Nhập trước khi bấm Từ chối.",
    )
    is_self_approval = fields.Boolean("Tự duyệt", readonly=True)
    state = fields.Selection(
        [("pending", "Chờ duyệt"), ("approved", "Đã duyệt"), ("rejected", "Từ chối")],
        string="Trạng thái", default="pending", required=True, readonly=True,
        tracking=True, index=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Công ty", required=True, index=True,
        default=lambda self: self.env.company,
    )

    @api.depends("request_type", "object_label")
    def _compute_title(self):
        labels = dict(APPROVAL_TYPE_SELECTION)
        for req in self:
            head = labels.get(req.request_type, req.request_type or "")
            req.title = "%s — %s" % (head, req.object_label) if req.object_label else head

    # ------------------------------------------------------------------
    # Tạo yêu cầu từ các model rule thương mại
    # ------------------------------------------------------------------
    @api.model
    def _open_for(self, request_type, record, old_value, new_value, impact, reason):
        """Tạo (hoặc tái sử dụng) một yêu cầu duyệt cho record thương mại."""
        existing = self.search([
            ("res_model", "=", record._name),
            ("res_id", "=", record.id),
            ("state", "=", "pending"),
        ], limit=1)
        if existing:
            return existing
        return self.create({
            "request_type": request_type,
            "res_model": record._name,
            "res_id": record.id,
            "object_label": record.display_name,
            "old_value": old_value,
            "new_value": new_value,
            "impact": impact,
            "reason": reason,
            "requester_id": self.env.user.id,
            "requester_role": self._current_role_label(),
            "company_id": record.company_id.id,
        })

    @api.model
    def _current_role_label(self):
        user = self.env.user
        for role, xmlid in _ROLE_GROUP.items():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group and user in group.users:
                return dict(APPROVER_ROLE_SELECTION)[role]
        return user.name

    def _setting(self):
        self.ensure_one()
        return self.env["dl.pricing.approval.setting"].search([
            ("request_type", "=", self.request_type),
            ("company_id", "=", self.company_id.id),
        ], limit=1)

    def _check_can_resolve(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group("dl_base.dl_group_admin"):
            return
        setting = self._setting()
        allowed = setting._allowed_user_ids() if setting else []
        if not allowed:
            # Không cấu hình được người duyệt: chỉ Giám đốc mới xử lý.
            ceo = self.env.ref("dl_base.dl_group_ceo", raise_if_not_found=False)
            allowed = ceo.users.ids if ceo else []
        if user.id not in allowed:
            raise AccessError(
                _("Bạn không có vai trò duyệt cho loại yêu cầu này.")
            )

    def _target_record(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].browse(self.res_id).exists()
        return self.env["dl.pricing.approval.request"].browse()  # empty

    def action_approve(self):
        for req in self:
            if req.state != "pending":
                raise UserError(_("Yêu cầu đã được xử lý."))
            req._check_can_resolve()
            self_approval = req.requester_id == self.env.user
            req.write({
                "state": "approved",
                "resolved_by_id": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
                "is_self_approval": self_approval,
            })
            if self_approval:
                req.message_post(body=_(
                    "⚠️ Người đề xuất tự duyệt yêu cầu của mình. "
                    "Đã ghi nhận vì lý do: %s"
                ) % (req.reason or ""))
            target = req._target_record()
            if target and hasattr(target, "_on_approval_approved"):
                target._on_approval_approved(req)
        return True

    def action_reject(self):
        for req in self:
            if req.state != "pending":
                raise UserError(_("Yêu cầu đã được xử lý."))
            req._check_can_resolve()
            if not req.reject_comment:
                raise ValidationError(_("Bắt buộc nhập lý do khi từ chối."))
            req.write({
                "state": "rejected",
                "resolved_by_id": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
            })
            target = req._target_record()
            if target and hasattr(target, "_on_approval_rejected"):
                target._on_approval_rejected(req)
        return True
