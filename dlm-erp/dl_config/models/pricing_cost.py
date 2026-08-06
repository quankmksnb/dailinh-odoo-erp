# -*- coding: utf-8 -*-
"""Màn hình 3 — Chi phí chung và hệ số điều chỉnh (đặc tả V3 mục 6).

Gộp chi phí chung, phụ phí và hệ số điều chỉnh vào MỘT danh sách; phân biệt bằng
trường "Loại quy tắc". Mỗi khoản hiển thị thành một dòng trong bảng phân tích giá
nội bộ để người dùng biết giá tăng từ đâu.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .pricing_rule import TECH_STATE_SELECTION

# Các loại quy tắc nên có — mục 6.2.
COST_RULE_TYPE_SELECTION = [
    ("workshop_overhead", "Chi phí chung xưởng"),
    ("packing", "Đóng gói"),
    ("shipping", "Vận chuyển"),
    ("small_order", "Đơn hàng nhỏ"),
    ("urgent", "Giao gấp"),
    ("complexity", "Độ phức tạp gia công"),
    ("contingency", "Dự phòng/rủi ro"),
    ("other", "Chi phí khác"),
]

# Cách tính — mục 6.3.
COST_METHOD_SELECTION = [
    ("percent_direct", "% chi phí trực tiếp"),
    ("percent_cost", "% giá thành"),
    ("per_unit", "đồng/sản phẩm"),
    ("per_batch", "đồng/lô"),
    ("fixed", "Tiền cố định"),
    ("factor", "Hệ số nhân"),
]

_PERCENT_METHODS = ("percent_direct", "percent_cost")


class DlPricingCostAdjustmentRule(models.Model):
    _name = "dl.pricing.cost.adjustment.rule"
    _description = "Chi phí chung và hệ số điều chỉnh"
    _inherit = ["dl.pricing.rule.mixin"]

    name = fields.Char("Tên khoản", required=True, tracking=True)
    rule_type = fields.Selection(
        COST_RULE_TYPE_SELECTION, string="Loại quy tắc", required=True,
        default="workshop_overhead", tracking=True,
    )
    method = fields.Selection(
        COST_METHOD_SELECTION, string="Cách tính", required=True,
        default="percent_direct", tracking=True,
    )
    value = fields.Float(
        "Giá trị", required=True, digits=(16, 2), tracking=True,
        help="Tỷ lệ %, đơn giá, số tiền hoặc hệ số tùy theo cách tính.",
    )
    condition_days = fields.Integer(
        "Số ngày giao tối đa", tracking=True,
        help="Chỉ dùng cho Giao gấp: áp dụng khi thời gian giao ≤ số ngày này.",
    )
    condition_amount = fields.Float(
        "Giá trị đơn tối đa", digits=(16, 2), tracking=True,
        help="Chỉ dùng cho Đơn hàng nhỏ: áp dụng khi giá trị đơn ≤ mức này.",
    )
    no_discount = fields.Boolean(
        "Không chịu chiết khấu", tracking=True,
        help="Bật cho vận chuyển, chứng chỉ hoặc khoản thu hộ — tách khỏi cơ sở chiết khấu.",
    )
    state = fields.Selection(
        TECH_STATE_SELECTION, string="Trạng thái", required=True,
        default="draft", readonly=True, copy=False, tracking=True, index=True,
    )

    def _target_domain(self):
        self.ensure_one()
        return [("rule_type", "=", self.rule_type), ("name", "=ilike", self.name)]

    # ------------------------------------------------------------------
    # Tra & tính khoản điều chỉnh — NGUỒN DUY NHẤT dùng cho engine tính giá
    # báo giá (quotation_pricing_service, Lớp D). Đặt công thức 6 cách tính ở
    # một chỗ (đối xứng dl.pricing.operation.rule.variable_unit_amount).
    # ------------------------------------------------------------------
    @api.model
    def _get_active_rules(self, company, date):
        """Các khoản điều chỉnh đang áp dụng, đúng công ty và còn hiệu lực tại
        ``date``. Sắp theo ``id`` (thứ tự tạo) để áp dụng tuần tự ổn định —
        cách tính % giá thành / hệ số nhân cộng dồn trên ``running`` nên thứ tự
        có ý nghĩa (V3 §6.1)."""
        return self.search(
            [
                ("state", "=", "active"),
                ("company_id", "=", company.id),
                ("valid_from", "<=", date),
                "|", ("valid_to", "=", False), ("valid_to", ">=", date),
            ],
            order="id",
        )

    def adjustment_unit_amount(self, direct_unit, running_unit, qty):
        """Khoản điều chỉnh cộng lên giá thành cho MỘT đơn vị đầu ra theo cách
        tính (v1.1 §6.3). ``direct_unit`` = chi phí trực tiếp/đơn vị (vật tư +
        công đoạn); ``running_unit`` = giá thành lũy kế/đơn vị (đã cộng các
        khoản trước). Phí theo lô/cố định phân bổ đều trên số lượng (Decision B3)."""
        self.ensure_one()
        value = self.value
        method = self.method
        if method == "percent_direct":
            return direct_unit * value / 100.0
        if method == "percent_cost":
            return running_unit * value / 100.0
        if method == "per_unit":
            return value
        if method in ("per_batch", "fixed"):
            return value / qty if qty else 0.0
        if method == "factor":
            return running_unit * (value - 1.0)
        return 0.0

    def applies(self, order_value, delivery_days):
        """Điều kiện áp dụng (V3 §6.2). Khoản 'Giao gấp' chỉ áp khi thời gian
        giao ≤ ``condition_days``; khoản 'Đơn hàng nhỏ' chỉ áp khi giá trị đơn ≤
        ``condition_amount``. Các loại khác luôn áp dụng."""
        self.ensure_one()
        if self.rule_type == "urgent":
            if delivery_days is None or not self.condition_days:
                return False
            return delivery_days <= self.condition_days
        if self.rule_type == "small_order":
            if not self.condition_amount:
                return False
            return order_value <= self.condition_amount
        return True

    @api.constrains("method", "value")
    def _check_value(self):
        for rule in self:
            if rule.method in _PERCENT_METHODS and not (0 <= rule.value <= 100):
                raise ValidationError(_("Tỷ lệ %% phải trong khoảng 0–100%%."))
            if rule.method == "factor" and rule.value <= 0:
                raise ValidationError(_("Hệ số nhân phải lớn hơn 0."))
            if rule.method not in ("factor",) and rule.value < 0:
                raise ValidationError(_("Giá trị không được âm."))
