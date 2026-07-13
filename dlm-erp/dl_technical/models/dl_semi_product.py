from odoo import fields, models


class DlSemiProductTechnical(models.Model):
    _inherit = "dl.semi.product"

    bom_ids = fields.One2many("dl.bom", "semi_product_id", string="Danh sách BOM")
