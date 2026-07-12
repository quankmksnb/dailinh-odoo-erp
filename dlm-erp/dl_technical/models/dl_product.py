from odoo import fields, models


class ProductCategoryTechnical(models.Model):
    _inherit = "product.category"

    template_bom_id = fields.Many2one(
        "dl.bom",
        string="BOM mẫu",
    )


class DlProductTechnical(models.Model):
    _inherit = "dl.product"

    bom_ids = fields.One2many(
        "dl.bom",
        "product_id",
        string="Danh sách BOM",
    )
