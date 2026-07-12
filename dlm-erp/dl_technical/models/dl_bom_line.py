from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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

    material_id = fields.Many2one(
        "dl.material",
        string="Vật tư",
        domain=[("status", "=", "active")],
    )

    semi_finished_id = fields.Many2one(
        "dl.semi.product",
        string="Bán thành phẩm",
        domain=[("active", "=", True)],
    )

    input_length_mm = fields.Float(
        string="Chiều dài đầu vào (mm)",
        digits=(12, 3),
    )

    input_width_mm = fields.Float(
        string="Chiều rộng đầu vào (mm)",
        digits=(12, 3),
    )

    input_thickness_mm = fields.Float(
        string="Độ dày đầu vào (mm)",
        digits=(12, 3),
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

    @api.depends("material_id", "semi_finished_id")
    def _compute_price_snapshot(self):
        for rec in self:
            price = 0.0

            if (
                rec.material_id
                and hasattr(rec.material_id, "active_price_id")
                and rec.material_id.active_price_id
            ):
                price = rec.material_id.active_price_id.unit_price

            elif rec.semi_finished_id:
                bom = self.env["dl.bom"].search(
                    [
                        ("semi_product_id", "=", rec.semi_finished_id.id),
                        ("status", "in", ("confirmed", "locked")),
                    ],
                    order="version desc",
                    limit=1,
                )
                if bom:
                    price = bom.total_material_cost

            rec.price_snapshot = price

    @api.depends("effective_qty", "price_snapshot")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.effective_qty * rec.price_snapshot

    # ==========================================================
    # ONCHANGE
    # ==========================================================

    @api.onchange("material_id")
    def _onchange_material(self):
        if self.material_id:
            self.component_type = "raw_material"
            self.semi_finished_id = False
            # TDS C3: quantity "tự sinh từ C3 hoặc nhập tay" — direct_count
            # không cần kích thước nên tính ngay khi chọn vật tư.
            formula = self.env["dl.parametric.formula"].search(
                [("material_id", "=", self.material_id.id)], limit=1)
            if formula and formula.formula_type == "direct_count" and not self.is_override:
                self.quantity = formula._evaluate()

    @api.onchange("semi_finished_id")
    def _onchange_semi_finished(self):
        if self.semi_finished_id:
            self.component_type = "semi_finished"
            self.material_id = False

    @api.onchange("input_length_mm", "input_width_mm", "input_thickness_mm")
    def _onchange_dimensions(self):
        # TDS C3: các formula_type còn lại cần kích thước nhập vào. KTV vẫn
        # có thể ghi đè qua is_override.
        if self.component_type == "raw_material" and self.material_id and not self.is_override:
            formula = self.env["dl.parametric.formula"].search(
                [("material_id", "=", self.material_id.id)], limit=1)
            if formula and formula.formula_type in (
                    "volume_density", "linear_density", "area_based", "custom_expression"):
                self.quantity = formula._evaluate(
                    self.input_length_mm, self.input_width_mm, self.input_thickness_mm)

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

    @api.constrains(
        "input_length_mm",
        "input_width_mm",
        "input_thickness_mm",
    )
    def _check_dimension(self):
        for rec in self:

            if rec.input_length_mm < 0:
                raise ValidationError(
                    _("Chiều dài không được nhỏ hơn 0.")
                )

            if rec.input_width_mm < 0:
                raise ValidationError(
                    _("Chiều rộng không được nhỏ hơn 0.")
                )

            if rec.input_thickness_mm < 0:
                raise ValidationError(
                    _("Độ dày không được nhỏ hơn 0.")
                )