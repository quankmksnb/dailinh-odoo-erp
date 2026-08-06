# -*- coding: utf-8 -*-
"""Màn hình 2 — Chi phí công đoạn (đặc tả V3 mục 5).

Người dùng chọn công đoạn, chọn một trong 6 phương pháp tính và nhập một giá
trị. Không dùng biểu thức điều kiện, không cấu hình nhiều phạm vi, không bắt
buộc phê duyệt.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .pricing_rule import TECH_STATE_SELECTION

# 6 phương pháp phổ biến — mục 5.2.
OPERATION_METHOD_SELECTION = [
    ("percent_material", "% vật liệu liên quan"),
    ("per_kg", "Theo kg"),
    ("per_meter", "Theo mét"),
    ("per_sqm", "Theo m²"),
    ("per_unit", "Theo sản phẩm"),
    ("per_batch", "Cố định theo lô"),
]


class DlPricingOperation(models.Model):
    _name = "dl.pricing.operation"
    _description = "Danh mục công đoạn dùng chung"
    _order = "sequence, name"

    name = fields.Char("Tên công đoạn", required=True)
    code = fields.Char("Mã", required=True)
    sequence = fields.Integer("Thứ tự", default=10)
    active = fields.Boolean("Đang dùng", default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Mã công đoạn đã tồn tại."),
    ]


class DlPricingOperationRule(models.Model):
    _name = "dl.pricing.operation.rule"
    _description = "Đơn giá/tỷ lệ công đoạn"
    _inherit = ["dl.pricing.rule.mixin"]
    _rec_name = "operation_id"

    operation_id = fields.Many2one(
        "dl.pricing.operation", string="Công đoạn", required=True,
        ondelete="restrict", tracking=True,
    )
    method = fields.Selection(
        OPERATION_METHOD_SELECTION, string="Phương pháp tính", required=True,
        default="percent_material", tracking=True,
    )
    price_rate = fields.Float(
        "Đơn giá / Tỷ lệ", required=True, digits=(16, 2), tracking=True,
        help="% khi tính theo vật liệu; đơn giá theo kg/mét/m²/sản phẩm/lô.",
    )
    setup_fee = fields.Float(
        "Phí setup/lô", digits=(16, 2), tracking=True,
        help="Chỉ dùng với công đoạn cần chuẩn bị máy; cộng một lần cho lô.",
    )
    state = fields.Selection(
        TECH_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )

    def _target_domain(self):
        self.ensure_one()
        return [("operation_id", "=", self.operation_id.id)]

    # ------------------------------------------------------------------
    # Tra & tính đơn giá công đoạn — NGUỒN DUY NHẤT dùng chung cho ước tính
    # tham khảo trên form BOM (dl.bom.operation.line, pha B1) và engine tính
    # giá báo giá (quotation_pricing_service, pha B2). Để công thức 6 phương
    # pháp ở một chỗ, hai đường không bao giờ lệch nhau (đối xứng cách BOM &
    # engine cùng gọi _standard_child_bom cho giá vốn BTP).
    # ------------------------------------------------------------------
    @api.model
    def _get_active(self, operation, company, date):
        """Đơn giá công đoạn đang áp dụng cho ``operation``, đúng công ty và còn
        hiệu lực tại ``date``. Trả về recordset rỗng nếu không có (đối xứng
        _active_material_seller / _active_profit_rule)."""
        if not operation:
            return self.browse()
        return self.search(
            [
                ("operation_id", "=", operation.id),
                ("state", "=", "active"),
                ("company_id", "=", company.id),
                ("valid_from", "<=", date),
                "|", ("valid_to", "=", False), ("valid_to", ">=", date),
            ],
            order="valid_from desc, revision desc", limit=1,
        )

    def variable_unit_amount(self, base_qty, material_unit_base):
        """Chi phí công đoạn BIẾN ĐỔI cho MỘT đơn vị đầu ra theo phương pháp của
        rule (bảng §3.1 Thiet_ke_chi_phi_cong_doan_bom_operation.md).

        KHÔNG bao gồm phí setup / per_batch — đó là chi phí theo LÔ, phân bổ /qty
        ở tầng engine (§3.2). ``material_unit_base`` = chi phí vật tư/đơn vị làm
        cơ sở cho phương pháp % vật liệu.
        """
        self.ensure_one()
        if self.method == "percent_material":
            return material_unit_base * self.price_rate / 100.0
        if self.method in ("per_kg", "per_meter", "per_sqm"):
            return base_qty * self.price_rate
        if self.method == "per_unit":
            return self.price_rate
        # per_batch: toàn bộ nằm ở chi phí lô (setup/per_batch) — không có phần
        # biến đổi trên mỗi đơn vị.
        return 0.0

    @api.constrains("method", "price_rate", "setup_fee")
    def _check_values(self):
        for rule in self:
            if rule.method == "percent_material" and not (0 <= rule.price_rate <= 100):
                raise ValidationError(
                    _("Tỷ lệ %% vật liệu phải trong khoảng 0–100%%.")
                )
            if rule.price_rate < 0:
                raise ValidationError(_("Đơn giá công đoạn không được âm."))
            if rule.setup_fee < 0:
                raise ValidationError(_("Phí setup không được âm."))
