# -*- coding: utf-8 -*-
"""K4 — Màn Tồn kho đọc thẳng nguồn gốc lô. K7 — bán phế liệu.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §11.2, §7.3, §11.8.

Hai field related để thủ kho trả lời được "thép đang nằm kho này của ai, về ngày
nào" mà KHÔNG phải mở từng lô. Không lưu (`store=False`): dữ liệu đã nằm ở
stock.lot, nhân bản sang quant chỉ tạo thêm chỗ lệch.
"""

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # ── K8 — Cho Thủ kho áp kiểm kê mà KHÔNG cấp group_stock_manager ──────────
    def _apply_inventory(self):
        """Áp số kiểm kê ⇒ sinh phiếu điều chỉnh, tồn khớp số đếm.

        🔴 Native `stock.quant._apply_inventory` chốt cứng: chỉ
        `stock.group_stock_manager` mới validate được. Nhưng §8.3 CẤM cấp
        manager cho Thủ kho — manager mở kèm cả xoá quant, sửa vị trí, cấu hình
        tồn kho. Thay vì nới group (rủi ro rộng), kiểm vai trò Thủ kho tường
        minh rồi chạy phần thân native dưới quyền superuser — đúng khuôn "kiểm
        vai trò rồi nâng quyền" đã dùng ở K6 (`action_dlm_create_delivery`).

        `base.user_root` là thành viên `stock.group_stock_manager`
        (stock/security/stock_security.xml) nên `with_user(SUPERUSER_ID)` vượt
        được chốt native mà không phải chép logic sinh move.

        Một chốt này vá cho CẢ màn Kiểm kê (K8) lẫn màn Phế liệu (K7): mọi lối
        áp kiểm kê của Thủ kho đều đi qua đây. Vai trò khác giữ nguyên luật
        native (admin/CEO có manager thì rẽ thẳng super).
        """
        if (not self.user_has_groups("stock.group_stock_manager")
                and self.user_has_groups("dl_base.dl_group_warehouse")):
            return super(StockQuant, self.with_user(SUPERUSER_ID))._apply_inventory()
        return super()._apply_inventory()

    dlm_supplier_id = fields.Many2one(
        related="lot_id.dlm_supplier_id", string="Nhà cung cấp", readonly=True)
    dlm_receipt_date = fields.Date(
        related="lot_id.dlm_receipt_date", string="Ngày nhập", readonly=True)

    # ── K7 — Phế liệu ────────────────────────────────────────────────────────
    # Đơn giá ở đây là GIÁ BÁN phế liệu (`list_price`), KHÔNG phải giá vốn — nên
    # không vi phạm §8.3 ("Thủ kho không thấy giá"). Thủ kho là người cân và
    # giao phế liệu cho bên thu mua, phải biết lô vụn này đáng bao nhiêu tiền.
    dlm_scrap_unit_price = fields.Float(
        related="product_id.list_price", string="Đơn giá", readonly=True,
        digits="Product Price")
    dlm_scrap_value = fields.Float(
        string="Thành tiền", compute="_compute_dlm_scrap_value",
        digits="Product Price")

    @api.depends("quantity", "product_id.list_price")
    def _compute_dlm_scrap_value(self):
        for quant in self:
            quant.dlm_scrap_value = quant.quantity * quant.product_id.list_price

    def action_dlm_sell_scrap(self):
        """Tạo phiếu Bán phế liệu (nháp) từ các dòng tồn đang chọn.

        Để NHÁP và chưa gán khách: bán phế liệu là thoả thuận với bên thu mua
        (giá theo ngày, ai chở, cân ở đâu). Hệ thống dựng sẵn dòng hàng đúng số
        đang tồn; người dùng điền khách rồi mới xác nhận.
        """
        quants = self.filtered(
            lambda q: not float_is_zero(
                q.quantity, precision_rounding=q.product_uom_id.rounding or 0.01)
            and q.quantity > 0)
        if not quants:
            raise UserError(_(
                "Chọn ít nhất một dòng phế liệu còn tồn để lập phiếu bán."))

        picking_type = self.env.ref(
            "dl_inventory.picking_type_scrap_sale", raise_if_not_found=False)
        if not picking_type:
            raise UserError(_(
                "Chưa cấu hình loại hoạt động Bán phế liệu. "
                "Chạy lại: -u dl_inventory"))
        source = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_xuong_pl")
        destination = picking_type.default_location_dest_id

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "move_ids": [(0, 0, {
                "name": quant.product_id.display_name,
                "product_id": quant.product_id.id,
                "product_uom": quant.product_uom_id.id,
                "product_uom_qty": quant.quantity,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }) for quant in quants],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "name": _("Bán phế liệu %s") % picking.name,
            "views": [(self.env.ref(
                "dl_inventory.view_dl_scrap_sale_form").id, "form")],
        }
