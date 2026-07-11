from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    category_kind = fields.Selection(
        [
            ("product", "Nhóm sản phẩm"),
            ("semi", "Nhóm bán thành phẩm"),
            ("material", "Nhóm vật tư"),
        ],
        string="Loại nhóm",
        required=True,
        default="product",
    )