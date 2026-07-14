from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductSupplierinfo(models.Model):
    """PROD-03 — dl.product.supplierinfo [kế thừa product.supplierinfo].

    Bảng giá vật tư / SP thương mại theo NHÀ CUNG CẤP + THỜI ĐIỂM. Dùng native
    ``product.supplierinfo`` (đã có sẵn partner_id, price, date_start, date_end,
    min_qty, currency_id, product_tmpl_id) thay vì bảng tự chế — thay thế hoàn
    toàn model cũ ``dl.material.price``.

    Field mở rộng DUY NHẤT theo Data Model: ``approval_state`` — Kế toán duyệt
    giá NCC (draft → approved) trước khi KTV dùng để tính price_snapshot trong
    BOM (TECH-03).
    """

    _inherit = "product.supplierinfo"

    approval_state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("approved", "Đã duyệt"),
        ],
        string="Trạng thái duyệt",
        default="draft",
        required=True,
        copy=False,
        help="Kế toán duyệt giá NCC trước khi áp dụng cho báo giá / BOM.",
    )

    def action_approve(self):
        """Kế toán/Admin duyệt bảng giá NCC."""
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được duyệt giá NCC."))
        self.write({"approval_state": "approved"})

    def action_reset_draft(self):
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được đổi trạng thái giá NCC."))
        self.write({"approval_state": "draft"})
