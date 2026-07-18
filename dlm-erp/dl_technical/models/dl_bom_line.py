from odoo import api, fields, models, _


class DlBomLine(models.Model):
    _name = "dl.bom.line"
    _description = "Dòng BOM"
    _inherit = ["dl.bom.line.mixin"]
    _order = "id"

    bom_id = fields.Many2one(
        "dl.bom",
        string="BOM",
        required=True,
        ondelete="cascade",
    )

    price_snapshot = fields.Float(
        string="Đơn giá snapshot",
        compute="_compute_price_snapshot",
        store=True,
        readonly=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    recovery_value = fields.Float(
        string="Giá trị thu hồi",
        compute="_compute_recovery_value",
        store=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    subtotal = fields.Float(
        string="Thành tiền",
        compute="_compute_subtotal",
        store=True,
        digits="Product Price",
        groups="dl_base.dl_group_ceo,"
               "dl_base.dl_group_admin,"
               "dl_base.dl_group_accountant,"
               "dl_base.dl_group_sales_manager",
    )

    @api.depends(
        "material_id",
        "material_id.seller_ids.price",
        "material_id.seller_ids.approval_state",
        "material_id.seller_ids.is_applied",
    )
    def _compute_price_snapshot(self):
        """Snapshot đơn giá tại thời điểm tạo BOM.

        - Vật tư (material): lấy giá product.supplierinfo đang được đánh dấu
          "đang áp dụng" (is_applied=True, kéo theo approval_state='approved'
          — PROD-03). Kế toán chọn rõ 1 bảng giá áp dụng cho mỗi vật tư thay
          vì suy đoán "mới nhất theo ngày" (không phân biệt được khi 1 vật tư
          có nhiều bảng giá đã duyệt từ nhiều NCC).
        - Vật tư đã gia công / BTP: chi phí đệ quy = total_material_cost của
          BOM confirmed/locked của chính nó.
        """
        for rec in self:
            price = 0.0
            component = rec.material_id

            if component and component.product_kind == "material_processed":
                bom = self.env["dl.bom"].search(
                    [
                        ("product_id", "=", component.id),
                        ("status", "in", ("confirmed", "locked")),
                    ],
                    order="version desc",
                    limit=1,
                )
                if bom:
                    price = bom.total_material_cost
            elif component:
                seller = component.seller_ids.filtered("is_applied")
                if seller:
                    price = seller[0].price

            rec.price_snapshot = price

    @api.depends("effective_qty", "quantity", "material_id.dlm_has_recovery",
                 "material_id.dlm_recovery_rate",
                 "material_id.dlm_scrap_product_id.list_price")
    def _compute_recovery_value(self):
        for rec in self:
            rec.recovery_value = rec._dlm_recovery_value()

    @api.depends("effective_qty", "price_snapshot", "recovery_value")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.effective_qty * rec.price_snapshot - rec.recovery_value
