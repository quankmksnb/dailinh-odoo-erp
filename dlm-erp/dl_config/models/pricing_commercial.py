# -*- coding: utf-8 -*-
"""Màn hình 4 — Lợi nhuận và chiết khấu (đặc tả V3 mục 7).

Đây là nhóm cấu hình THƯƠNG MẠI duy nhất và BẮT BUỘC phê duyệt trước khi có hiệu
lực. Cố định phương pháp "Markup trên giá thành"; chiết khấu chỉ theo 3 nhóm
khách hàng: Khách mới, Khách cũ, Khách thân thiết.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .pricing_rule import COMMERCIAL_STATE_SELECTION

# Đúng 3 nhóm khách hàng — mục 7.3.
CUSTOMER_GROUP_SELECTION = [
    ("new", "Khách mới"),
    ("existing", "Khách cũ"),
    ("loyal", "Khách thân thiết"),
]

# Thứ bậc gắn bó tăng dần: khách gắn bó lâu hơn phải được chiết khấu KHÔNG THẤP
# hơn khách mới hơn (mới ≤ cũ ≤ thân thiết). Dùng để so bậc khi kiểm tra thang
# chiết khấu — tương tự _LEVEL_RANK của ma trận phê duyệt.
GROUP_RANK = {"new": 0, "existing": 1, "loyal": 2}


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
    _order = "group_rank asc, state, valid_from desc, id desc"
    _rec_name = "name"

    name = fields.Char("Tên", compute="_compute_name", store=True)
    customer_group = fields.Selection(
        CUSTOMER_GROUP_SELECTION, string="Nhóm khách hàng", required=True,
        default="new", tracking=True,
    )
    group_rank = fields.Integer(
        "Bậc gắn bó", compute="_compute_group_rank", store=True,
        help="Dùng nội bộ để sắp xếp và so bậc thang chiết khấu (mới→cũ→thân thiết).",
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

    @api.depends("customer_group")
    def _compute_group_rank(self):
        for rule in self:
            rule.group_rank = GROUP_RANK.get(rule.customer_group, 0)

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

    # ------------------------------------------------------------------
    # Thang chiết khấu theo độ gắn bó (yêu cầu chính): mới ≤ cũ ≤ thân thiết
    # ------------------------------------------------------------------
    def _assert_fits_group_ladder(self):
        """Bản ghi này (coi như sẽ áp dụng) phải khớp thang chiết khấu hiện tại:
        khách gắn bó lâu hơn KHÔNG được chiết khấu thấp hơn khách mới hơn — cả
        mức mặc định lẫn mức tối đa. So từng cặp với các chính sách ĐANG ÁP DỤNG
        của nhóm khác (tương tự _assert_fits_ladder của ma trận phê duyệt).

        Dùng cho constraint lúc kích hoạt và kiểm tra SỚM lúc Gửi duyệt — đề
        xuất đảo bậc bị chặn ngay, không làm loãng hàng chờ của Giám đốc.
        """
        self.ensure_one()
        labels = dict(CUSTOMER_GROUP_SELECTION)
        my_rank = GROUP_RANK[self.customer_group]
        others = self.search([
            ("id", "not in", self.ids),
            ("state", "=", "active"),
            ("company_id", "=", self.company_id.id),
            ("customer_group", "!=", self.customer_group),
        ])
        for other in others:
            # lower = nhóm ít gắn bó hơn, higher = nhóm gắn bó hơn.
            lower, higher = ((self, other)
                             if my_rank < GROUP_RANK[other.customer_group]
                             else (other, self))
            for field, metric in (
                ("default_rate", _("chiết khấu mặc định")),
                ("max_rate", _("chiết khấu tối đa")),
            ):
                if lower[field] > higher[field] + 1e-9:
                    raise ValidationError(_(
                        "Bậc chiết khấu bị đảo: %(low)s đang có %(metric)s "
                        "%(low_rate)s%% nhưng %(high)s (gắn bó hơn) chỉ "
                        "%(high_rate)s%%. Khách gắn bó lâu hơn không được chiết "
                        "khấu thấp hơn khách mới hơn — hãy chỉnh để %(low)s "
                        "≤ %(high)s."
                    ) % {
                        "low": labels.get(lower.customer_group, ""),
                        "high": labels.get(higher.customer_group, ""),
                        "metric": metric,
                        "low_rate": lower[field],
                        "high_rate": higher[field],
                    })

    @api.constrains("customer_group", "default_rate", "max_rate", "state", "company_id")
    def _check_group_ladder(self):
        """Chỉ xét các chính sách đang áp dụng vì chúng mới thực sự áp lên báo giá."""
        for rule in self:
            if rule.state == "active":
                rule._assert_fits_group_ladder()

    def action_submit_approval(self):
        """Chặn SỚM đề xuất đảo bậc chiết khấu ngay khi Gửi duyệt."""
        self.ensure_one()
        self._assert_fits_group_ladder()
        return super().action_submit_approval()

# NB: Field res.partner.dlm_customer_group (nhóm khách của từng đối tác) được
# định nghĩa ở dl_sale/models/res_partner.py — nơi có sẵn dl.quotation để tự
# động phân loại. CUSTOMER_GROUP_SELECTION ở trên chỉ dùng cho chính sách chiết
# khấu (dl.pricing.discount.rule); phải giữ đồng bộ key với bản ở dl_sale.
