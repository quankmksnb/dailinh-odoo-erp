from odoo import fields, models, _
from odoo.exceptions import UserError


class DlBomFromTemplateWizard(models.TransientModel):
    """Product BOM — "Tạo từ BOM mẫu": chọn 1 BOM mẫu rồi copy toàn bộ dòng
    (vật tư, kích thước cắt, số đoạn, số lượng, hao hụt) sang BOM đang tạo,
    vẫn chỉnh sửa tiếp được sau khi copy."""

    _name = "dl.bom.from.template.wizard"
    _description = "Tạo BOM từ BOM mẫu"

    bom_id = fields.Many2one("dl.bom", string="BOM đích", required=True, readonly=True)
    product_category_id = fields.Many2one(
        related="bom_id.product_id.categ_id",
        string="Nhóm sản phẩm",
    )
    template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu",
        required=True,
        # LK-03 — chỉ chép từ mẫu ĐÃ DUYỆT (confirmed/locked); mẫu Nháp chưa được
        # là nguồn chép. Ưu tiên bản hiện hành, mới nhất (khuyến nghị W1/W2).
        domain="[('product_category_id', '=', product_category_id),"
               " ('status', 'in', ('confirmed', 'locked'))]",
    )

    def action_confirm(self):
        self.ensure_one()
        if self.bom_id.status != "draft":
            raise UserError(_("Chỉ BOM ở trạng thái Nháp mới copy được từ BOM mẫu."))
        # LK-03 — chốt lại ở server (bịt import/API): mẫu Nháp không được chép.
        if self.template_id.status not in ("confirmed", "locked"):
            raise UserError(_(
                "BOM mẫu “%s” chưa được duyệt (còn Nháp) — không thể dùng làm "
                "nguồn chép. Hãy xác nhận BOM mẫu trước."
            ) % self.template_id.name)
        if self.template_id.product_category_id != self.bom_id.product_id.categ_id:
            raise UserError(_(
                'BOM mẫu "%s" thuộc nhóm sản phẩm khác với sản phẩm của BOM này.'
            ) % self.template_id.name)
        if not self.template_id.line_ids:
            raise UserError(_("BOM mẫu này chưa có dòng nào để copy."))

        missing = self.template_id.line_ids.filtered(lambda l: not l.material_id)
        if missing:
            positions = [
                str(i + 1) for i, line in enumerate(self.template_id.line_ids)
                if line in missing
            ]
            raise UserError(_(
                "BOM mẫu này có dòng chưa chọn Vật tư (dòng thứ %s) — "
                "vào BOM mẫu bổ sung Vật tư trước khi copy sang Product BOM."
            ) % ", ".join(positions))

        vals_list = []
        for tline in self.template_id.line_ids:
            vals = tline._mixin_copy_vals()
            vals["bom_id"] = self.bom_id.id
            vals_list.append(vals)

        self.env["dl.bom.line"].create(vals_list)

        return {"type": "ir.actions.act_window_close"}
