from odoo import api, fields, models, _


class DlSemiProduct(models.Model):
    _name = "dl.semi.product"
    _description = "Bán thành phẩm"
    _inherits = {"product.product": "product_id"}
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "semi_code"

    _sql_constraints = [
        (
            "semi_code_uniq",
            "unique(semi_code)",
            "Mã bán thành phẩm đã tồn tại.",
        ),
    ]

    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        ondelete="cascade",
    )

    semi_code = fields.Char(
        string="Mã bán thành phẩm",
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    technical_note = fields.Text(
        string="Ghi chú kỹ thuật",
    )

    bom_ids = fields.One2many(
        "dl.bom",
        "semi_product_id",
        string="Danh sách BOM",
    )

    active = fields.Boolean(
        string="Hoạt động",
        default=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("semi_code", _("New")) == _("New"):
                vals["semi_code"] = (
                    self.env["ir.sequence"].next_by_code("dl.semi.product")
                    or _("New")
                )

            vals.setdefault("type", "consu")

        return super().create(vals_list)