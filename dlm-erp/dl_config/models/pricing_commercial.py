# -*- coding: utf-8 -*-
"""Màn hình 4 — Lợi nhuận và chiết khấu (đặc tả V3 mục 7).

Đây là nhóm cấu hình THƯƠNG MẠI duy nhất và BẮT BUỘC phê duyệt trước khi có hiệu
lực. Cố định phương pháp "Markup trên giá thành"; chiết khấu chỉ theo 3 nhóm
khách hàng: Khách mới, Khách cũ, Khách tiềm năng.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .pricing_rule import COMMERCIAL_STATE_SELECTION

# Đúng 3 nhóm khách hàng — mục 7.3.
CUSTOMER_GROUP_SELECTION = [
    ("new", "Khách mới"),
    ("existing", "Khách cũ"),
    ("potential", "Khách tiềm năng"),
]


class DlPricingCommercialMixin(models.AbstractModel):
    """Gộp luồng phê duyệt dùng chung cho lợi nhuận và chiết khấu."""

    _name = "dl.pricing.commercial.mixin"
    _inherit = ["dl.pricing.rule.mixin"]
    _description = "Luồng phê duyệt cấu hình thương mại"

    def action_apply(self):
        raise UserError(_(
            "Cấu hình thương mại phải gửi duyệt. Hãy bấm Gửi duyệt thay vì Áp dụng."
        ))

    # Model cụ thể khai báo loại yêu cầu + mô tả thay đổi.
    def _approval_type(self):
        raise NotImplementedError

    def _approval_change_desc(self):
        self.ensure_one()
        return "", "", ""  # old, new, impact

    def action_submit_approval(self):
        self.ensure_one()
        if self.state not in ("draft", "rejected"):
            raise UserError(_("Chỉ gửi duyệt được cấu hình ở trạng thái Nháp hoặc bị từ chối."))
        if not self.change_reason:
            raise ValidationError(_("Bắt buộc nhập lý do thay đổi trước khi gửi duyệt."))
        old_value, new_value, impact = self._approval_change_desc()
        request = self.env["dl.pricing.approval.request"]._open_for(
            self._approval_type(), self, old_value, new_value, impact, self.change_reason,
        )
        self.with_context(pricing_system_write=True).write({"state": "pending"})
        return {
            "type": "ir.actions.act_window",
            "name": _("Yêu cầu phê duyệt"),
            "res_model": "dl.pricing.approval.request",
            "res_id": request.id,
            "view_mode": "form",
            "target": "current",
        }

    def _on_approval_approved(self, request):
        self.ensure_one()
        self._activate_rule()

    def _on_approval_rejected(self, request):
        self.ensure_one()
        self.with_context(pricing_system_write=True).write({"state": "rejected"})


class DlPricingProfitRule(models.Model):
    _name = "dl.pricing.profit.rule"
    _description = "Chính sách lợi nhuận và giá sàn"
    _inherit = ["dl.pricing.commercial.mixin"]
    _rec_name = "name"

    name = fields.Char("Tên", compute="_compute_name", store=True)
    target_markup = fields.Float(
        "Lợi nhuận mục tiêu (%)", required=True, digits=(6, 2), tracking=True,
        help="Tỷ lệ cộng trên giá thành để ra giá bán trước chiết khấu.",
    )
    min_markup = fields.Float(
        "Lợi nhuận tối thiểu (%)", required=True, digits=(6, 2), tracking=True,
        help="Dùng tính giá sàn; chiết khấu vượt phải duyệt ngoại lệ.",
    )
    state = fields.Selection(
        COMMERCIAL_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )

    @api.depends("target_markup", "min_markup", "revision")
    def _compute_name(self):
        for rule in self:
            rule.name = _("Markup mục tiêu %s%% / sàn %s%% (b%s)") % (
                rule.target_markup, rule.min_markup, rule.revision,
            )

    def _target_domain(self):
        self.ensure_one()
        # Chính sách lợi nhuận áp dụng toàn công ty — chỉ một bản đang chạy.
        return [("id", "!=", False)]

    def _approval_type(self):
        return "profit_config"

    def _approval_change_desc(self):
        self.ensure_one()
        current = self.search([("state", "=", "active")], limit=1)
        old = _("Mục tiêu %s%% / sàn %s%%") % (
            current.target_markup, current.min_markup) if current else _("(chưa có)")
        new = _("Mục tiêu %s%% / sàn %s%%") % (self.target_markup, self.min_markup)
        return old, new, _("Ảnh hưởng giá bán và giá sàn của báo giá mới.")

    @api.constrains("target_markup", "min_markup")
    def _check_markup(self):
        for rule in self:
            if rule.target_markup < 0 or rule.min_markup < 0:
                raise ValidationError(_("Tỷ lệ lợi nhuận không được âm."))
            if rule.min_markup > rule.target_markup:
                raise ValidationError(
                    _("Lợi nhuận tối thiểu không được vượt lợi nhuận mục tiêu.")
                )


class DlPricingDiscountRule(models.Model):
    _name = "dl.pricing.discount.rule"
    _description = "Chính sách chiết khấu theo nhóm khách hàng"
    _inherit = ["dl.pricing.commercial.mixin"]
    _rec_name = "name"

    name = fields.Char("Tên", compute="_compute_name", store=True)
    customer_group = fields.Selection(
        CUSTOMER_GROUP_SELECTION, string="Nhóm khách hàng", required=True,
        default="new", tracking=True,
    )
    default_rate = fields.Float(
        "Chiết khấu mặc định (%)", required=True, digits=(6, 2), tracking=True,
        help="Hệ thống tự điền lên báo giá.",
    )
    max_rate = fields.Float(
        "Chiết khấu tối đa (%)", required=True, digits=(6, 2), tracking=True,
        help="Vượt mức này bắt buộc quản lý duyệt ngoại lệ.",
    )
    state = fields.Selection(
        COMMERCIAL_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )

    @api.depends("customer_group", "default_rate", "max_rate", "revision")
    def _compute_name(self):
        labels = dict(CUSTOMER_GROUP_SELECTION)
        for rule in self:
            rule.name = _("%s: mặc định %s%% / tối đa %s%% (b%s)") % (
                labels.get(rule.customer_group, ""),
                rule.default_rate, rule.max_rate, rule.revision,
            )

    def _target_domain(self):
        self.ensure_one()
        return [("customer_group", "=", self.customer_group)]

    def _approval_type(self):
        return "discount_config"

    def _approval_change_desc(self):
        self.ensure_one()
        group_label = dict(CUSTOMER_GROUP_SELECTION)[self.customer_group]
        current = self.search([
            ("customer_group", "=", self.customer_group), ("state", "=", "active"),
        ], limit=1)
        old = _("Mặc định %s%% / tối đa %s%%") % (
            current.default_rate, current.max_rate) if current else _("(chưa có)")
        new = _("Mặc định %s%% / tối đa %s%%") % (self.default_rate, self.max_rate)
        return old, new, _("Nhóm %s.") % group_label

    @api.constrains("default_rate", "max_rate")
    def _check_rates(self):
        for rule in self:
            if not (0 <= rule.default_rate <= 100) or not (0 <= rule.max_rate <= 100):
                raise ValidationError(_("Chiết khấu phải trong khoảng 0–100%%."))
            if rule.default_rate > rule.max_rate:
                raise ValidationError(
                    _("Chiết khấu mặc định không được vượt mức tối đa.")
                )

# NB: Field res.partner.dlm_customer_group (nhóm khách của từng đối tác) được
# định nghĩa ở dl_sale/models/res_partner.py — nơi có sẵn dl.quotation để tự
# động phân loại. CUSTOMER_GROUP_SELECTION ở trên chỉ dùng cho chính sách chiết
# khấu (dl.pricing.discount.rule); phải giữ đồng bộ key với bản ở dl_sale.
