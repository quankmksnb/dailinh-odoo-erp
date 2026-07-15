from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Công thức HARD-CODE theo shape.code (thay dl.parametric.formula đã bỏ).
# Đọc giá trị kích thước (mm) theo param.code + hệ số (coef) → ra định mức.
# Thêm shape mới = thêm 1 nhánh ở đây. ⚠ Hằng số/công thức cần đội kỹ thuật
# xác nhận (vd khối lượng riêng thép 7850 kg/m³).
# ---------------------------------------------------------------------------
def _formula_flat_plate(d, coef):
    """Tấm phẳng: KL = dài(m) × rộng(m) × dày(m) × khối lượng riêng."""
    return (d.get("length", 0.0) / 1000.0) * (d.get("width", 0.0) / 1000.0) \
        * (d.get("thickness", 0.0) / 1000.0) * coef


def _formula_hollow_square_tube(d, coef):
    """Ống vuông rỗng: KL = (cạnh² − (cạnh−2·dày)²)(m²) × dài(m) × KLR."""
    side = d.get("side", 0.0) / 1000.0
    thickness = d.get("thickness", 0.0) / 1000.0
    length = d.get("length", 0.0) / 1000.0
    inner = max(side - 2 * thickness, 0.0)
    area = side ** 2 - inner ** 2
    return area * length * coef


MEASUREMENT_FORMULAS = {
    "flat_plate": _formula_flat_plate,
    "hollow_square_tube": _formula_hollow_square_tube,
}


class DlBomLine(models.Model):
    _name = "dl.bom.line"
    _description = "Dòng BOM"
    _order = "id"

    bom_id = fields.Many2one(
        "dl.bom",
        string="BOM",
        required=True,
        ondelete="cascade",
    )

    component_type = fields.Selection(
        [
            ("raw_material", "Vật tư"),
            ("semi_finished", "Bán thành phẩm"),
        ],
        string="Loại thành phần",
        required=True,
        default="raw_material",
    )

    # Data Model refactor: dl.material/dl.semi.product hợp nhất vào
    # product.product (phân biệt bằng product_kind).
    material_id = fields.Many2one(
        "product.product",
        string="Vật tư",
        domain=[("product_kind", "in", ("material", "material_processed"))],
    )

    semi_finished_id = fields.Many2one(
        "product.product",
        string="Bán thành phẩm",
        domain=[("product_kind", "=", "material_processed")],
    )

    # ── Đo lường (thay input_length/width/thickness + dl.parametric.formula) ──
    measurement_shape_id = fields.Many2one(
        "dl.measurement.shape",
        string="Hình dạng đo",
        help="Chọn hình dạng để nhập kích thước và tự tính định mức theo công thức.",
    )
    measurement_coefficient = fields.Float(
        string="Hệ số",
        digits=(16, 4),
        help="Hệ số tính (vd khối lượng riêng). Mặc định theo hình dạng, sửa được.",
    )
    dimension_ids = fields.One2many(
        "dl.bom.line.dimension", "bom_line_id", string="Kích thước",
    )

    quantity = fields.Float(
        string="Số lượng",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )

    waste_rate = fields.Float(
        string="Tỷ lệ hao hụt (%)",
        default=0.0,
        digits=(5, 2),
    )

    effective_qty = fields.Float(
        string="Số lượng thực tế",
        compute="_compute_effective_qty",
        store=True,
        digits="Product Unit of Measure",
    )

    price_snapshot = fields.Float(
        string="Đơn giá snapshot",
        compute="_compute_price_snapshot",
        store=True,
        readonly=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    subtotal = fields.Float(
        string="Thành tiền",
        compute="_compute_subtotal",
        store=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    is_override = fields.Boolean(
        string="Ghi đè số lượng",
        default=False,
    )

    override_reason = fields.Text(
        string="Lý do ghi đè",
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị tính",
        compute="_compute_uom",
        store=True,
    )

    # ==========================================================
    # COMPUTE
    # ==========================================================

    @api.depends("quantity", "waste_rate")
    def _compute_effective_qty(self):
        for rec in self:
            rec.effective_qty = rec.quantity * (1 + rec.waste_rate / 100)

    @api.depends("material_id", "semi_finished_id")
    def _compute_uom(self):
        for rec in self:
            if rec.material_id:
                rec.uom_id = rec.material_id.uom_id
            elif rec.semi_finished_id:
                rec.uom_id = rec.semi_finished_id.uom_id
            else:
                rec.uom_id = False

    @api.depends(
        "material_id", "semi_finished_id",
        "material_id.seller_ids.price",
        "material_id.seller_ids.approval_state",
    )
    def _compute_price_snapshot(self):
        """Snapshot đơn giá tại thời điểm tạo BOM.

        - Vật tư (material): lấy giá product.supplierinfo bản ĐÃ DUYỆT
          (approval_state='approved') còn hiệu lực, mới nhất (PROD-03).
        - Vật tư đã gia công / BTP: chi phí đệ quy = total_material_cost của
          BOM confirmed/locked của chính nó.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            price = 0.0
            component = rec.material_id or rec.semi_finished_id

            if component and component.product_kind == "material_processed":
                bom = self.env["dl.bom"].search(
                    [
                        ("semi_product_id", "=", component.id),
                        ("status", "in", ("confirmed", "locked")),
                    ],
                    order="version desc",
                    limit=1,
                )
                if bom:
                    price = bom.total_material_cost
            elif component:
                sellers = component.seller_ids.filtered(
                    lambda s: s.approval_state == "approved"
                    and (not s.date_start or s.date_start <= today)
                    and (not s.date_end or s.date_end >= today)
                ).sorted(key=lambda s: s.date_start or fields.Date.today(), reverse=True)
                if sellers:
                    price = sellers[0].price

            rec.price_snapshot = price

    @api.depends("effective_qty", "price_snapshot")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.effective_qty * rec.price_snapshot

    # ==========================================================
    # ĐO LƯỜNG — công thức hard-code theo shape
    # ==========================================================

    def _measurement_quantity(self):
        """Tính định mức từ kích thước + hệ số theo công thức hard-code của shape.

        Trả về None nếu không đủ dữ liệu / shape chưa có công thức (giữ nguyên
        quantity đang có)."""
        self.ensure_one()
        shape = self.measurement_shape_id
        if not shape or not shape.code:
            return None
        formula = MEASUREMENT_FORMULAS.get(shape.code)
        if not formula:
            return None
        values = {}
        for dim in self.dimension_ids:
            if dim.param_id and dim.param_id.code:
                values[dim.param_id.code] = dim.value
        return formula(values, self.measurement_coefficient or 0.0)

    @api.onchange("measurement_shape_id")
    def _onchange_measurement_shape(self):
        shape = self.measurement_shape_id
        if not shape:
            self.dimension_ids = [(5, 0, 0)]
            return
        self.measurement_coefficient = shape.default_coefficient
        self.dimension_ids = [(5, 0, 0)] + [
            (0, 0, {"param_id": p.id}) for p in shape.param_ids.filtered("active")
        ]

    @api.onchange("dimension_ids", "measurement_coefficient", "measurement_shape_id")
    def _onchange_measurement_values(self):
        if self.is_override:
            return
        qty = self._measurement_quantity()
        if qty is not None and qty > 0:
            self.quantity = qty

    # ==========================================================
    # ONCHANGE component
    # ==========================================================

    @api.onchange("material_id")
    def _onchange_material(self):
        if self.material_id:
            self.component_type = "raw_material"
            self.semi_finished_id = False

    @api.onchange("semi_finished_id")
    def _onchange_semi_finished(self):
        if self.semi_finished_id:
            self.component_type = "semi_finished"
            self.material_id = False

    # ==========================================================
    # CONSTRAINT
    # ==========================================================

    @api.constrains("component_type", "material_id", "semi_finished_id")
    def _check_component(self):
        for rec in self:

            if rec.component_type == "raw_material":
                if not rec.material_id:
                    raise ValidationError(
                        _("Bạn phải chọn vật tư.")
                    )
                if rec.semi_finished_id:
                    raise ValidationError(
                        _("Loại 'Vật tư' không được chọn bán thành phẩm.")
                    )

            if rec.component_type == "semi_finished":
                if not rec.semi_finished_id:
                    raise ValidationError(
                        _("Bạn phải chọn bán thành phẩm.")
                    )
                if rec.material_id:
                    raise ValidationError(
                        _("Loại 'Bán thành phẩm' không được chọn vật tư.")
                    )

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(
                    _("Số lượng phải lớn hơn 0.")
                )

    @api.constrains("waste_rate")
    def _check_waste_rate(self):
        for rec in self:
            if rec.waste_rate < 0:
                raise ValidationError(
                    _("Tỷ lệ hao hụt không được nhỏ hơn 0.")
                )

    @api.constrains("is_override", "override_reason")
    def _check_override_reason(self):
        for rec in self:
            if rec.is_override and not rec.override_reason:
                raise ValidationError(
                    _("Vui lòng nhập lý do khi ghi đè số lượng.")
                )


class DlBomLineDimension(models.Model):
    """Giá trị kích thước cụ thể của 1 dòng BOM theo tham số của shape.

    Lưu số 5m/2m… nhập lúc dựng BOM. Công thức hard-code (theo shape.code) đọc
    các giá trị này (map theo param.code) để tính định mức vật tư."""

    _name = "dl.bom.line.dimension"
    _description = "Kích thước dòng BOM"
    _order = "id"

    bom_line_id = fields.Many2one(
        "dl.bom.line",
        string="Dòng BOM",
        required=True,
        ondelete="cascade",
    )
    param_id = fields.Many2one(
        "dl.measurement.shape.param",
        string="Tham số",
        required=True,
        ondelete="restrict",
    )
    value = fields.Float(string="Giá trị (mm)", digits=(16, 3))

    @api.constrains("value")
    def _check_value(self):
        for rec in self:
            if rec.value < 0:
                raise ValidationError(_("Giá trị kích thước không được âm."))
