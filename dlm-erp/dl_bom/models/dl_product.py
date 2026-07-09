from odoo import fields, models


class DlProductCategory(models.Model):
    _inherit = "dl.product.category"

    template_bom_id = fields.Many2one(
        "dl.bom",
        string="BOM mẫu",
    )


class DlProduct(models.Model):
    _inherit = "dl.product"

    supply_type = fields.Selection(
        [
            ("manufactured", "Gia công"),
            ("trading", "Thương mại"),
        ],
        string="Loại cung ứng",
        default="manufactured",
    )

    purchase_cost = fields.Float(
        string="Giá vốn nhập",
        digits="Product Price",
    )

    default_supplier_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp mặc định",
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị tính",
    )

    bom_ids = fields.One2many(
        "dl.bom",
        "product_id",
        string="Danh sách BOM",
    )