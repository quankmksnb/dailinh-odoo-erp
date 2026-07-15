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
    )
    def _compute_price_snapshot(self):
        """Snapshot đơn giá tại thời điểm tạo BOM.

        - Vật tư thô (material): lấy giá product.supplierinfo bản ĐÃ DUYỆT
          (approval_state='approved') còn hiệu lực, mới nhất (PROD-03).
        - Vật tư đã gia công (material_processed): chi phí đệ quy =
          total_material_cost của BOM confirmed/locked của chính nó.
        """
        today = fields.Date.context_today(self)
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
                sellers = component.seller_ids.filtered(
                    lambda s: s.approval_state == "approved"
                    and (not s.date_start or s.date_start <= today)
                    and (not s.date_end or s.date_end >= today)
                ).sorted(key=lambda s: s.date_start or fields.Date.today(), reverse=True)
                if sellers:
                    price = sellers[0].price

            rec.price_snapshot = price

    @api.depends("effective_qty", "price_snapshot")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.effective_qty * rec.price_snapshot
