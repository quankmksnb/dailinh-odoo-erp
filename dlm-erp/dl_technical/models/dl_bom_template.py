from odoo import api, fields, models


class DlBomTemplate(models.Model):
    """BOM Template — dùng cho Product Group (product_category_id). Một
    Product Group có thể có nhiều BOM Template (nhiều version). Cấu trúc đầu
    BOM giống Product BOM (dl.bom): version/status/Output Quantity, cùng
    workflow xác nhận/khóa/lưu trữ/tạo phiên bản mới — dùng chung qua
    dl.bom.header.mixin. Độc lập với BOM thật, KHÔNG gắn 1 product cụ thể."""

    _name = "dl.bom.template"
    _description = "BOM mẫu"
    _inherit = ["mail.thread", "mail.activity.mixin", "dl.bom.header.mixin"]
    _order = "name"

    _sql_constraints = [
        (
            "category_version_uniq",
            "unique(product_category_id,version)",
            "Phiên bản BOM mẫu của nhóm sản phẩm đã tồn tại.",
        ),
    ]

    name = fields.Char(string="Tên BOM mẫu", required=True, tracking=True)
    # Chỉ nhóm thuộc 2 nhánh chuẩn (Thành phẩm cho SP gia công, Vật tư cho
    # nhóm Bán thành phẩm — BTP cũng có BOM); loại nhóm hệ thống/mồ côi.
    product_category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm",
        required=True,
        ondelete="restrict",
        tracking=True,
        domain=[("dl_branch", "in", ("finished", "material"))],
    )
    line_ids = fields.One2many(
        "dl.bom.template.line", "bom_template_id", string="Dòng mẫu"
    )

    def _version_domain(self):
        self.ensure_one()
        return [("product_category_id", "=", self.product_category_id.id)]

    @api.onchange("product_category_id")
    def _onchange_category_version(self):
        if self.product_category_id:
            self.version = self._compute_next_version()


class DlBomTemplateLine(models.Model):
    _name = "dl.bom.template.line"
    _description = "Dòng BOM mẫu"
    _inherit = ["dl.bom.line.mixin"]
    _order = "id"

    bom_template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu",
        required=True,
        ondelete="cascade",
    )

    note = fields.Char(string="Ghi chú")
