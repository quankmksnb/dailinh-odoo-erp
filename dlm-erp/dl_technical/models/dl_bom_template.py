from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlBomTemplate(models.Model):
    """TECH-04 — dl.bom.template [Model mới].

    Mẫu BOM tái sử dụng theo nhóm sản phẩm (category). KTV chọn mẫu phù hợp khi
    tạo BOM (dl.bom) mới cho SP cùng category để pre-fill nhanh danh sách
    component, sau đó chỉnh lại. Độc lập với BOM thật.
    """

    _name = "dl.bom.template"
    _description = "BOM mẫu"
    _order = "name"

    name = fields.Char(string="Tên BOM mẫu", required=True)
    product_category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm",
        required=True,
        ondelete="restrict",
    )
    active = fields.Boolean(string="Đang sử dụng", default=True)
    line_ids = fields.One2many(
        "dl.bom.template.line", "bom_template_id", string="Dòng mẫu"
    )

    def action_apply_to_bom(self, bom):
        """Sinh các dòng dl.bom.line từ mẫu này vào 1 BOM thật (bom)."""
        self.ensure_one()
        if not bom:
            raise UserError(_("Không xác định được BOM đích để áp mẫu."))
        Line = self.env["dl.bom.line"]
        for tline in self.line_ids:
            Line.create({
                "bom_id": bom.id,
                "component_type": "raw_material",
                "material_id": tline.suggested_product_id.id,
                "quantity": tline.default_qty,
            })
        return True


class DlBomTemplateLine(models.Model):
    """TECH-05 — dl.bom.template.line [Model mới]."""

    _name = "dl.bom.template.line"
    _description = "Dòng BOM mẫu"
    _order = "id"

    bom_template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu",
        required=True,
        ondelete="cascade",
    )
    suggested_product_id = fields.Many2one(
        "product.product",
        string="Vật tư gợi ý",
        required=True,
        domain=[("product_kind", "in", ("material", "material_processed"))],
        ondelete="restrict",
    )
    default_qty = fields.Float(string="Số lượng mặc định", default=1.0)
    note = fields.Char(string="Ghi chú")
