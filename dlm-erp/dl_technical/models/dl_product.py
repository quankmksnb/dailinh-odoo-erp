from odoo import api, fields, models

BOM_ELIGIBLE_KINDS = ("manufactured", "material_processed")


class ProductCategoryTechnical(models.Model):
    _inherit = "product.category"

    # PROD-01: FK category → BOM mẫu (TECH-04). Khai ở dl_technical (layer trên)
    # vì dl_product không depends dl_technical. Thay field cũ template_bom_id→dl.bom.
    bom_template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu mặc định",
        ondelete="set null",
    )


class DlProductTechnical(models.Model):
    # Data Model refactor: dl.product = product.product (mở rộng thuần).
    _inherit = "product.product"

    bom_ids = fields.One2many(
        "dl.bom",
        "product_id",
        string="Danh sách BOM",
        compute="_compute_bom_ids",
    )

    @api.depends("product_kind")
    def _compute_bom_ids(self):
        # SP thương mại / vật tư thô không bao giờ có BOM — bỏ qua tìm kiếm
        # trên dl.bom để các role không có quyền dl.bom (VD: Kế toán) không
        # bị chặn quyền truy cập khi mở SP thương mại/vật tư.
        eligible = self.filtered(lambda p: p.product_kind in BOM_ELIGIBLE_KINDS)
        boms = (
            self.env["dl.bom"].search([
                "|",
                ("product_id", "in", eligible.ids),
                ("semi_product_id", "in", eligible.ids),
            ])
            if eligible
            else self.env["dl.bom"]
        )
        for product in self:
            product.bom_ids = boms.filtered(
                lambda b: product.id in (b.product_id.id, b.semi_product_id.id)
            )

    def action_create_bom(self):
        # bom_ids là computed field (chỉ đọc) vì dùng chung cho cả 2 loại liên
        # kết (product_id/semi_product_id) nên không hỗ trợ "Add a line" trực
        # tiếp — nút này mở form dl.bom mới, tự set đúng field liên kết theo
        # product_kind của sản phẩm đang xem.
        self.ensure_one()
        ctx = {"default_bom_type": "quotation"}
        if self.product_kind == "manufactured":
            ctx["default_product_id"] = self.id
        elif self.product_kind == "material_processed":
            ctx["default_semi_product_id"] = self.id
        return {
            "type": "ir.actions.act_window",
            "name": "Tạo BOM",
            "res_model": "dl.bom",
            "view_mode": "form",
            "view_id": self.env.ref("dl_technical.view_dl_bom_form").id,
            "target": "current",
            "context": ctx,
        }
