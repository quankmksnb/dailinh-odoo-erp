# -*- coding: utf-8 -*-
# Dòng công đoạn (cắt/hàn/sơn/thuê ngoài) trên tab "Công đoạn" của form BOM — Kỹ thuật chỉ chọn
# công đoạn + nhập định mức, đơn giá thật do Kế toán cấu hình riêng (dl.pricing.operation.rule).

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.dl_config.models.pricing_operation import (
    OPERATION_METHOD_SELECTION,
)

# Nhóm được xem cấu phần giá thành — đối xứng ``_COST_GROUPS`` bên dl_sale
# (quotation_price_component). Kỹ thuật KHÔNG thấy đơn giá/ước tính công đoạn,
# chỉ dựng dòng công đoạn.
_COST_GROUPS = (
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
    "dl_base.dl_group_accountant,"
    "dl_base.dl_group_sales_manager"
)


class DlBomOperationLine(models.Model):
    _name = "dl.bom.operation.line"
    _description = "Công đoạn của định mức (BOM)"
    _order = "sequence, id"

    bom_id = fields.Many2one(
        "dl.bom", string="Định mức", required=True, ondelete="cascade",
        index=True)
    sequence = fields.Integer("Thứ tự", default=10)

    operation_id = fields.Many2one(
        "dl.pricing.operation", string="Công đoạn", required=True,
        ondelete="restrict")

    # method = cách tính của rule cấu hình đang hiệu lực (mỗi công đoạn một
    # phương pháp). Chỉ hiển thị lại cho KTV biết cần nhập cơ sở gì; non-stored
    # vì rule có thể lên revision (đơn giá thay đổi theo thời gian).
    method = fields.Selection(
        OPERATION_METHOD_SELECTION, string="Cách tính",
        compute="_compute_active_rule", readonly=True)
    has_active_rule = fields.Boolean(
        string="Đã có đơn giá", compute="_compute_active_rule")
    needs_base_qty = fields.Boolean(
        string="Cần định mức cơ sở", compute="_compute_active_rule",
        help="Cách tính theo kg/mét/m² cần nhập định mức cơ sở.")

    # Định mức cơ sở cho MỘT đơn vị đầu ra của BOM này. Chỉ cần cho
    # per_kg/per_meter/per_sqm (kg/m/m² đi qua công đoạn cho 1 sản phẩm).
    # per_unit dùng 1; per_batch/percent_material bỏ qua.
    base_qty = fields.Float(
        string="Định mức cơ sở/đơn vị", digits="Product Unit of Measure",
        help="Khối lượng/chiều dài/diện tích đi qua công đoạn cho MỘT sản phẩm. "
             "Chỉ nhập khi cách tính theo kg / mét / m².")

    # percent_material: cơ sở là chi phí vật tư của BOM. 'all' = toàn bộ;
    # 'selected' = chỉ các dòng vật tư đánh dấu đi qua công đoạn (V3 §5.5).
    material_scope = fields.Selection(
        [("all", "Toàn bộ vật tư"), ("selected", "Chỉ vật tư đã chọn")],
        default="all", required=True, string="Cơ sở % vật liệu")
    # Domain lọc theo BOM cha đặt ở VIEW (parent.id) — không để ở field vì Odoo
    # 17 bắt field tham chiếu trong domain-python phải có mặt trong view.
    material_line_ids = fields.Many2many(
        "dl.bom.line", string="Vật tư đi qua công đoạn",
        help="Dùng khi cơ sở % vật liệu = 'Chỉ vật tư đã chọn'.")

    # Thuê ngoài (RV-04): công đoạn do NCC gia công ngoài thực hiện. Để truy
    # vết + hiện trên phân tích; đơn giá vẫn lấy từ rule công đoạn. Không đổi
    # công thức tính.
    is_outsourced = fields.Boolean(string="Thuê ngoài")
    partner_id = fields.Many2one(
        "res.partner", string="Nhà cung cấp gia công",
        domain=[("partner_role", "in", ("supplier", "both"))])

    note = fields.Char("Ghi chú")

    # --- Ước tính THAM KHẢO cho nhóm giá (gated) --------------------------
    # Dùng rule đang hiệu lực HÔM NAY để sanity-check; KHÔNG phải giá chốt (giá
    # chốt tính tại thời điểm tạo báo giá theo pricing_date, pha B2). Ẩn với
    # Kỹ thuật. Chỉ phần BIẾN ĐỔI/đơn vị — setup/lô không quy về đơn vị được.
    estimated_unit_cost = fields.Float(
        string="Ước tính biến đổi/đơn vị (tham khảo)", digits="Product Price",
        compute="_compute_estimate", groups=_COST_GROUPS)

    # Tìm đơn giá công đoạn đang hiệu lực hôm nay (dùng cho ô ước tính tham khảo trên form BOM).
    def _get_active_rule(self):
        self.ensure_one()
        if not self.operation_id:
            return self.env["dl.pricing.operation.rule"].browse()
        company = self.env.company
        date = fields.Date.context_today(self)
        return self.env["dl.pricing.operation.rule"].sudo()._get_active(
            self.operation_id, company, date)

    # Tự điền lại ô "Cách tính"/"Đã có đơn giá" khi đổi công đoạn trên dòng.
    @api.depends("operation_id")
    def _compute_active_rule(self):
        for line in self:
            rule = line._get_active_rule()
            line.method = rule.method if rule else False
            line.has_active_rule = bool(rule)
            line.needs_base_qty = bool(
                rule and rule.method in ("per_kg", "per_meter", "per_sqm"))

    # Tính lại ô "Ước tính biến đổi/đơn vị" (chỉ Kế toán/CEO/Admin thấy) mỗi khi định mức/BOM đổi.
    @api.depends("operation_id", "base_qty", "material_scope",
                 "material_line_ids", "bom_id.total_material_cost",
                 "bom_id.product_qty")
    def _compute_estimate(self):
        for line in self:
            rule = line._get_active_rule()
            if not rule:
                line.estimated_unit_cost = 0.0
                continue
            line.estimated_unit_cost = rule.variable_unit_amount(
                line.base_qty, line._material_unit_base())

    # Chi phí vật tư/đơn vị dùng làm cơ sở khi công đoạn tính theo % vật liệu.
    def _material_unit_base(self):
        self.ensure_one()
        bom = self.bom_id
        qty_out = bom.product_qty or 1.0
        if self.material_scope == "selected" and self.material_line_ids:
            base = sum(self.material_line_ids.mapped("subtotal"))
        else:
            base = bom.total_material_cost
        return base / qty_out

    # Validate lúc lưu dòng công đoạn: định mức cơ sở không được âm.
    @api.constrains("base_qty")
    def _check_base_qty(self):
        for line in self:
            if line.base_qty < 0:
                raise ValidationError(
                    _("Định mức cơ sở công đoạn không được âm."))

    # Validate lúc lưu dòng công đoạn: đã chọn NCC gia công thì bắt buộc tick "Thuê ngoài".
    @api.constrains("is_outsourced", "partner_id")
    def _check_outsource_partner(self):
        for line in self:
            if line.partner_id and not line.is_outsourced:
                raise ValidationError(_(
                    "Đã chọn nhà cung cấp gia công cho công đoạn '%s' thì phải đánh dấu "
                    "'Thuê ngoài'.") % line.operation_id.display_name)
