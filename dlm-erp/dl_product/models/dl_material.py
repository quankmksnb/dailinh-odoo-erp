from odoo import api, fields, models


class DlMaterial(models.Model):
    _name = "dl.material"
    _inherits = {"product.product": "product_id"}
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Vật tư"
    _order = "default_code"

    _sql_constraints = [
        (
            "product_id_uniq",
            "unique(product_id)",
            "Sản phẩm Odoo này đã được liên kết với một vật tư khác.",
        )
    ]

    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm gốc",
        required=True,
        ondelete="cascade",
        index=True,
    )

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

    @api.depends("price_ids", "price_ids.is_active")
    def _compute_active_price(self):
        for rec in self:
            rec.active_price_id = rec.price_ids.filtered("is_active")[:1]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("default_code"):
                vals["default_code"] = (
                    self.env["ir.sequence"].next_by_code("dl.material") or "/"
                )
            vals.setdefault("type", "product")
        return super().create(vals_list)


class DlMaterialPrice(models.Model):
    _name = "dl.material.price"
    _description = "Giá vật tư"
    _order = "create_date desc"

    material_id = fields.Many2one(
        "dl.material",
        string="Vật tư",
        required=True,
        ondelete="cascade",
    )

    unit_price = fields.Float(
        string="Đơn giá",
        digits="Product Price",
        required=True,
    )

    is_active = fields.Boolean(
        string="Đang áp dụng",
        default=True,
    )

    note = fields.Text(string="Ghi chú")
