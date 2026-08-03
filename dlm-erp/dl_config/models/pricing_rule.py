# -*- coding: utf-8 -*-
"""Nền tảng dùng chung cho các quy tắc cấu hình báo giá (đặc tả V3).

Mỗi nhóm quy tắc là một model riêng, có vòng đời độc lập, phiên bản tự động và
snapshot bảo toàn báo giá cũ. Mixin này gom phần lặp lại:

* Trường chung: hiệu lực, phiên bản, lý do thay đổi, cờ đã dùng trong snapshot.
* Hành động chuẩn: Áp dụng, Ngừng áp dụng, Tạo bản sửa đổi (revision).
* Chặn hai quy tắc cùng đối tượng có khoảng hiệu lực chồng lấn.

Người dùng không phải hiểu khái niệm "phiên bản" để thao tác đúng: bấm Áp dụng
là hệ thống tự đóng bản cũ và mở bản mới; bấm Tạo bản sửa đổi là hệ thống nhân
bản sang bản Nháp mới, giữ nguyên bản đang chạy.
"""

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# Trạng thái cho cấu hình KỸ THUẬT/KẾ TOÁN — không cần phê duyệt.
TECH_STATE_SELECTION = [
    ("draft", "Nháp"),
    ("active", "Đang áp dụng"),
    ("expired", "Hết hiệu lực"),
]

# Trạng thái cho cấu hình THƯƠNG MẠI — bắt buộc phê duyệt trước khi hiệu lực.
COMMERCIAL_STATE_SELECTION = [
    ("draft", "Nháp"),
    ("pending", "Chờ duyệt"),
    ("active", "Đang áp dụng"),
    ("rejected", "Từ chối"),
    ("expired", "Ngừng áp dụng"),
]

_OPEN_DATE = fields.Date.to_date("9999-12-31")


class DlPricingRuleMixin(models.AbstractModel):
    _name = "dl.pricing.rule.mixin"
    _description = "Thuộc tính chung của quy tắc cấu hình báo giá"
    _inherit = ["mail.thread"]
    _order = "valid_from desc, id desc"

    company_id = fields.Many2one(
        "res.company", string="Công ty", required=True, index=True,
        default=lambda self: self.env.company,
    )
    revision = fields.Integer(
        "Phiên bản", default=1, readonly=True, copy=False, tracking=True,
    )
    valid_from = fields.Date(
        "Hiệu lực từ", required=True, tracking=True,
        default=fields.Date.context_today,
    )
    valid_to = fields.Date(
        "Hiệu lực đến", readonly=True, copy=False, tracking=True,
        help="Hệ thống tự đóng khi có bản mới bắt đầu hiệu lực.",
    )
    change_reason = fields.Char("Lý do thay đổi", tracking=True)
    used_in_snapshot = fields.Boolean(
        "Đã dùng trong báo giá", default=False, readonly=True, copy=False,
        help="Quy tắc đã được một báo giá chốt snapshot; không được sửa/xóa.",
    )

    # ------------------------------------------------------------------
    # Hooks mà từng model cụ thể phải/nên định nghĩa
    # ------------------------------------------------------------------
    def _target_domain(self):
        """Domain nhận diện các quy tắc CÙNG đối tượng với bản ghi này.

        Dùng để đóng bản cũ khi áp dụng bản mới và để chặn chồng lấn hiệu lực.
        Model cụ thể ghi đè để trả về điều kiện theo category/vật tư/công đoạn...
        """
        self.ensure_one()
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Bảo vệ dữ liệu đã dùng và ràng buộc hiệu lực
    # ------------------------------------------------------------------
    @api.constrains("valid_from", "valid_to")
    def _check_valid_range(self):
        for rec in self:
            if rec.valid_to and rec.valid_from and rec.valid_from > rec.valid_to:
                raise ValidationError(
                    _("Ngày hiệu lực từ không được sau ngày hiệu lực đến.")
                )

    def write(self, vals):
        protected = self.filtered("used_in_snapshot")
        if protected and not self.env.context.get("pricing_system_write"):
            # Cho phép hệ thống đóng valid_to/state khi có bản mới; chặn sửa nghiệp vụ.
            business_keys = set(vals) - {"valid_to", "state", "used_in_snapshot"}
            if business_keys:
                raise ValidationError(
                    _("Quy tắc '%s' đã dùng trong báo giá nên không thể sửa. "
                      "Hãy tạo bản sửa đổi mới.") % protected[0].display_name
                )
        return super().write(vals)

    def unlink(self):
        if self.filtered("used_in_snapshot"):
            raise ValidationError(
                _("Không thể xóa quy tắc đã dùng trong báo giá. "
                  "Hãy dùng Ngừng áp dụng để đóng hiệu lực.")
            )
        if self.filtered(lambda r: r.state == "active"):
            raise ValidationError(
                _("Không thể xóa quy tắc đang áp dụng. Hãy Ngừng áp dụng trước.")
            )
        return super().unlink()

    # ------------------------------------------------------------------
    # Chống chồng lấn hiệu lực (EX PRC-RULE-001)
    # ------------------------------------------------------------------
    @staticmethod
    def _dates_overlap(a_from, a_to, b_from, b_to):
        a_to = a_to or _OPEN_DATE
        b_to = b_to or _OPEN_DATE
        return max(a_from, b_from) <= min(a_to, b_to)

    def _assert_no_active_overlap(self):
        """Chặn hai quy tắc cùng đối tượng đang áp dụng mà chồng khoảng hiệu lực."""
        for rec in self:
            if rec.state != "active":
                continue
            others = rec.search(
                rec._target_domain()
                + [
                    ("id", "!=", rec.id),
                    ("state", "=", "active"),
                    ("company_id", "=", rec.company_id.id),
                ]
            )
            for other in others:
                if self._dates_overlap(
                    rec.valid_from, rec.valid_to, other.valid_from, other.valid_to
                ):
                    raise ValidationError(
                        _("Đã có quy tắc '%s' cùng đối tượng và khoảng hiệu lực "
                          "chồng lấn. Hãy đổi ngày hiệu lực hoặc ngừng bản cũ.")
                        % other.display_name
                    )

    # ------------------------------------------------------------------
    # Hành động chuẩn: Áp dụng / Ngừng áp dụng / Tạo bản sửa đổi
    # ------------------------------------------------------------------
    def action_apply(self):
        """Kích hoạt bản Nháp; tự đóng bản cũ cùng đối tượng."""
        for rec in self:
            if rec.state not in ("draft",):
                raise UserError(
                    _("Chỉ áp dụng được quy tắc ở trạng thái Nháp.")
                )
            rec._activate_rule()
        return True

    def _activate_rule(self):
        """Đóng bản cũ, đưa bản này sang Đang áp dụng và kiểm tra chồng lấn."""
        self.ensure_one()
        self._close_previous_active()
        self.with_context(pricing_system_write=True).write({"state": "active"})
        self._assert_no_active_overlap()

    def _close_previous_active(self):
        self.ensure_one()
        previous = self.search(
            self._target_domain()
            + [
                ("id", "!=", self.id),
                ("state", "=", "active"),
                ("company_id", "=", self.company_id.id),
            ]
        )
        for old in previous:
            # Bản cũ hết hiệu lực ngay trước ngày bản mới bắt đầu, nhưng không
            # được lùi trước ngày bản cũ bắt đầu (trường hợp sửa/áp dụng cùng ngày).
            close_date = max(self.valid_from - timedelta(days=1), old.valid_from)
            old.with_context(pricing_system_write=True).write({
                "state": "expired",
                "valid_to": close_date,
            })

    def action_expire(self):
        """Ngừng áp dụng — đóng hiệu lực, giữ lịch sử."""
        for rec in self:
            if rec.state not in ("active", "pending"):
                raise UserError(
                    _("Chỉ ngừng được quy tắc đang áp dụng hoặc chờ duyệt.")
                )
            rec.with_context(pricing_system_write=True).write({
                "state": "expired",
                "valid_to": rec.valid_to or fields.Date.context_today(rec),
            })
        return True

    def action_create_revision(self):
        """Tạo bản sửa đổi: nhân bản sang Nháp mới, giữ nguyên bản đang chạy."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(
                _("Chỉ tạo bản sửa đổi từ quy tắc đang áp dụng.")
            )
        new = self.copy({
            "revision": self.revision + 1,
            "valid_from": fields.Date.context_today(self),
            "change_reason": False,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Bản sửa đổi mới"),
            "res_model": self._name,
            "res_id": new.id,
            "view_mode": "form",
            "target": "current",
        }
