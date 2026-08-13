# -*- coding: utf-8 -*-
"""Màn hình 1 — Hao hụt và thu hồi (đặc tả V3 mục 4).

Quy tắc hao hụt theo category hoặc theo từng vật tư; vật tư cụ thể luôn ưu tiên
hơn category. Kèm bảng Hệ số phức tạp dùng chung (mục 4.4) — kỹ thuật chọn mức
khi lập BOM/báo giá, không cấu hình công thức riêng cho từng vật tư.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .pricing_rule import TECH_STATE_SELECTION


class DlPricingComplexityLevel(models.Model):
    _name = "dl.pricing.complexity.level"
    _description = "Hệ số phức tạp dùng chung"
    _order = "sequence, factor"

    name = fields.Char("Mức phức tạp", required=True, translate=False)
    factor = fields.Float(
        "Hệ số", required=True, default=1.0, digits=(6, 2),
        help="Nhân với tỷ lệ hao hụt cơ sở khi tính giá. Ví dụ 1,10.",
    )
    note = fields.Char("Gợi ý sử dụng")
    sequence = fields.Integer("Thứ tự", default=10)
    active = fields.Boolean(
        "Đang dùng", default=True,
        help="Tắt để ẩn mức không dùng (vd mức Đặc biệt) khỏi danh sách chọn.",
    )

    @api.constrains("factor")
    def _check_factor(self):
        for level in self:
            if level.factor <= 0:
                raise ValidationError(_("Hệ số phức tạp phải lớn hơn 0."))


class DlPricingWasteRule(models.Model):
    _name = "dl.pricing.waste.rule"
    _description = "Quy tắc hao hụt và thu hồi"
    _inherit = ["dl.pricing.rule.mixin"]
    _rec_name = "target_label"

    target_type = fields.Selection(
        [("category", "Theo category"), ("product", "Theo vật tư")],
        string="Áp dụng cho", required=True, default="category", tracking=True,
    )
    category_id = fields.Many2one(
        "product.category", string="Category", ondelete="restrict", tracking=True,
    )
    product_id = fields.Many2one(
        "product.product", string="Vật tư", ondelete="restrict", tracking=True,
    )
    target_label = fields.Char(
        "Đối tượng", compute="_compute_target_label", store=True,
    )
    waste_rate = fields.Float(
        "Tỷ lệ hao hụt cơ sở (%)", required=True, digits=(6, 2), tracking=True,
        help="Tỷ lệ cộng thêm vào lượng vật tư thuần của BOM.",
    )
    # 🔴 NGƯNG SỬ DỤNG 2026-08-13 (K16) — bỏ cách tính % thu hồi phế liệu. Giữ
    # cột (không xoá dữ liệu cấu hình), gỡ khỏi UI và khỏi mọi công thức.
    has_recovery = fields.Boolean("Có thu hồi (ngưng dùng)", tracking=True)
    recovery_rate = fields.Float(
        "Tỷ lệ khối lượng thu hồi (%) (ngưng dùng)", digits=(6, 2),
        tracking=True,
        help="NGƯNG SỬ DỤNG từ 2026-08-13: phế liệu khai theo số cân thực trên "
             "phiếu Nhập kho từ xưởng.",
    )
    scrap_product_id = fields.Many2one(
        "product.product", string="Sản phẩm phế liệu", ondelete="restrict",
        help="Nhóm vật tư này thải ra loại phế liệu nào — điền sẵn cho vật tư "
             "mới, dùng khi khai số phế liệu cân được.",
    )
    state = fields.Selection(
        TECH_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )

    @api.depends("target_type", "category_id", "product_id")
    def _compute_target_label(self):
        for rule in self:
            if rule.target_type == "product":
                rule.target_label = rule.product_id.display_name or _("(Chưa chọn vật tư)")
            else:
                rule.target_label = rule.category_id.display_name or _("(Chưa chọn category)")

    def _target_domain(self):
        self.ensure_one()
        if self.target_type == "product":
            return [("target_type", "=", "product"), ("product_id", "=", self.product_id.id)]
        return [("target_type", "=", "category"), ("category_id", "=", self.category_id.id)]

    @api.constrains("target_type", "category_id", "product_id")
    def _check_target(self):
        for rule in self:
            if rule.target_type == "category" and not rule.category_id:
                raise ValidationError(_("Hãy chọn category áp dụng cho quy tắc hao hụt."))
            if rule.target_type == "product" and not rule.product_id:
                raise ValidationError(_("Hãy chọn vật tư áp dụng cho quy tắc hao hụt."))

    @api.constrains("waste_rate")
    def _check_rates(self):
        for rule in self:
            if rule.waste_rate < 0 or rule.waste_rate > 100:
                raise ValidationError(
                    _("Tỷ lệ hao hụt phải trong khoảng 0–100%%.")
                )

    @api.onchange("target_type")
    def _onchange_target_type(self):
        if self.target_type == "category":
            self.product_id = False
        else:
            self.category_id = False

    # K16 — `_onchange_has_recovery` đã gỡ cùng cách tính % thu hồi.
