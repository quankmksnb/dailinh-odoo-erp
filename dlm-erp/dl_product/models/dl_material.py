from odoo import api, models, fields, _


class DlMaterial(models.Model):
    _name = "dl.material"
    _inherits = {"product.product": "product_id"}
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Vật tư"
    _order = "material_code"

    _sql_constraints = [
        (
            "product_id_uniq",
            "unique(product_id)",
            "Sản phẩm Odoo này đã được liên kết với một vật tư khác.",
        ),
        (
            "material_code_uniq",
            "unique(material_code)",
            "Mã vật tư đã tồn tại.",
        ),
    ]

    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm gốc",
        required=True,
        ondelete="cascade",
        index=True,
    )

    material_code = fields.Char(
        string="Mã vật tư",
        copy=False,
        readonly=True,
        index=True,
    )

    # categ_id đã có qua _inherits (product.product)
    # Chỉ cần domain trên view để lọc category_kind='material'

    spec = fields.Char(string="Quy cách")

    status = fields.Selection(
        [
            ("active", "Đang sử dụng"),
            ("inactive", "Ngừng sử dụng"),
        ],
        string="Trạng thái",
        default="active",
        required=True,
        tracking=True,
    )

    active_price_id = fields.Many2one(
        "dl.material.price",
        string="Bảng giá hiện hành",
        compute="_compute_active_price",
    )

    price_ids = fields.One2many(
        "dl.material.price",
        "material_id",
        string="Lịch sử giá",
    )

    @api.depends(
        "price_ids", "price_ids.valid_from", "price_ids.valid_to", "price_ids.is_active"
    )
    def _compute_active_price(self):
        today = fields.Date.context_today(self)
        for rec in self:
            valid_prices = rec.price_ids.filtered(
                lambda p: p.is_active
                and p.valid_from <= today
                and (not p.valid_to or p.valid_to >= today)
            )
            rec.active_price_id = valid_prices[:1]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("material_code"):
                vals["material_code"] = (
                    self.env["ir.sequence"].next_by_code("dl.material") or "/"
                )
            if not vals.get("default_code"):
                vals["default_code"] = vals.get("material_code")
            vals.setdefault("detailed_type", "product")
        return super().create(vals_list)


class DlMaterialPrice(models.Model):
    _name = "dl.material.price"
    _description = "Giá vật tư"
    _order = "valid_from desc, create_date desc"

    _sql_constraints = [
        (
            "unit_price_positive",
            "CHECK(unit_price > 0)",
            "Đơn giá phải lớn hơn 0.",
        ),
    ]

    material_id = fields.Many2one(
        "dl.material",
        string="Vật tư",
        required=True,
        ondelete="cascade",
        index=True,
    )

    unit_price = fields.Float(
        string="Đơn giá",
        digits="Product Price",
        required=True,
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị tính",
        required=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        default=lambda self: self.env.company.currency_id,
    )

    valid_from = fields.Date(
        string="Hiệu lực từ",
        required=True,
        default=fields.Date.context_today,
    )

    valid_to = fields.Date(string="Ngày hết hiệu lực")

    supplier_id = fields.Many2one(
        "res.partner",
        string="NCC tham khảo",
        domain="[('partner_role', 'in', ['supplier', 'both'])]",
    )

    is_active = fields.Boolean(
        string="Đang áp dụng",
        default=True,
    )

    price_status = fields.Selection(
        [
            ("valid", "Còn hiệu lực"),
            ("expiring", "Sắp hết hạn"),
            ("expired", "Hết hạn"),
        ],
        string="Trạng thái giá",
        compute="_compute_price_status",
        store=True,
    )

    note = fields.Text(string="Ghi chú")

    @api.depends("valid_from", "valid_to")
    def _compute_price_status(self):
        today = fields.Date.context_today(self)
        alert_days = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dl.material_price_alert_days", "7")
        )
        from datetime import timedelta

        threshold = today + timedelta(days=alert_days)
        for rec in self:
            if not rec.valid_to or rec.valid_to > threshold:
                rec.price_status = "valid"
            elif today <= rec.valid_to <= threshold:
                rec.price_status = "expiring"
            else:
                rec.price_status = "expired"

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS dl_material_price_material_valid_idx
            ON dl_material_price (material_id, valid_from, valid_to)
        """)
