from odoo import api, fields, models, _


class DlSemiProduct(models.Model):
    _name = "dl.semi.product"
    _description = "Bán thành phẩm"
    _inherits = {"product.product": "product_id"}
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "semi_code"

    _sql_constraints = [
        ("semi_code_uniq", "unique(semi_code)", "Mã bán thành phẩm đã tồn tại."),
        (
            "product_id_uniq",
            "unique(product_id)",
            "Sản phẩm Odoo này được liên kết với một bán thành phẩm khác",
        ),
    ]

    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        ondelete="cascade",
        index=True,
    )

    semi_code = fields.Char(
        string="Mã bán thành phẩm",
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    active = fields.Boolean(
        string="Hoạt động",
        default=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("semi_code", _("New")) == _("New"):
                vals["semi_code"] = self.env["ir.sequence"].next_by_code(
                    "dl.semi.product"
                ) or _("New")
            vals.setdefault("detailed_type", "product")
        return super().create(vals_list)
