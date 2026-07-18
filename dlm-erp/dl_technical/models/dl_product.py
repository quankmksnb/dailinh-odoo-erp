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
            self.env["dl.bom"].search([("product_id", "in", eligible.ids)])
            if eligible
            else self.env["dl.bom"]
        )
        for product in self:
            product.bom_ids = boms.filtered(lambda b: b.product_id.id == product.id)

    # ── Hao hụt: tự điền mặc định theo nhóm (field ở dl_product; logic đọc
    # dl.pricing.waste.rule phải ở đây vì dl_technical mới depends dl_config) ──
    @api.onchange("categ_id", "product_kind")
    def _onchange_dlm_waste_default(self):
        """Khi chọn nhóm cho vật tư mà chưa nhập hao hụt: điền mặc định từ quy
        tắc hao hụt theo NHÓM đang áp dụng (dl.pricing.waste.rule)."""
        if self.product_kind not in ("material", "material_processed"):
            return
        if self.dlm_waste_rate:
            return
        rule = self._dlm_category_waste_rule()
        if rule:
            self.dlm_waste_rate = rule.waste_rate
            self.dlm_has_recovery = rule.has_recovery
            self.dlm_recovery_rate = rule.recovery_rate
            self.dlm_scrap_product_id = rule.scrap_product_id

    def _dlm_category_waste_rule(self):
        self.ensure_one()
        if not self.categ_id:
            return self.env["dl.pricing.waste.rule"].browse()
        return self.env["dl.pricing.waste.rule"].sudo().search([
            ("state", "=", "active"),
            ("target_type", "=", "category"),
            ("category_id", "=", self.categ_id.id),
        ], order="valid_from desc, revision desc", limit=1)

    def action_create_bom(self):
        # bom_ids là computed field (chỉ đọc) — nút này mở form dl.bom mới,
        # tự set product_id theo sản phẩm đang xem (dl.bom.product_id đã gộp
        # chung cho cả manufactured lẫn material_processed).
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tạo BOM",
            "res_model": "dl.bom",
            "view_mode": "form",
            "view_id": self.env.ref("dl_technical.view_dl_bom_form").id,
            "target": "current",
            "context": {"default_bom_type": "quotation", "default_product_id": self.id},
        }
