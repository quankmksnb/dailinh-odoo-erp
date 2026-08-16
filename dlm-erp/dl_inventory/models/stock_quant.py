# -*- coding: utf-8 -*-
"""Màn Tồn kho: xem nguồn gốc lô, kiểm kê, hoá/bán phế liệu."""

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _apply_inventory(self):
        """Cho Thủ kho validate kiểm kê mà không cần group manager (màn Kiểm kê + Phế liệu)."""
        self._dlm_check_inventory_allowed()
        if (not self.user_has_groups("stock.group_stock_manager")
                and self.user_has_groups("dl_base.dl_group_warehouse")):
            return super(StockQuant, self.with_user(SUPERUSER_ID))._apply_inventory()
        return super()._apply_inventory()

    def _dlm_check_inventory_allowed(self):
        """Chặn kiểm kê tay ở khu quá cảnh (Chờ kiểm hàng / Chờ trả NCC), kể cả admin."""
        blocked = self.location_id.filtered("dlm_no_inventory")
        if not blocked:
            return True
        raise UserError(_(
            "Không kiểm kê tay được ở khu quá cảnh: %s.\n\n"
            "Tồn ở đây đang gắn với chứng từ đang mở (phiếu kiểm, phiếu trả "
            "nhà cung cấp). Muốn đổi số thì xử lý bằng chính phiếu đó — đếm tay sẽ xoá "
            "mất hàng mà chứng từ còn tham chiếu."
        ) % ", ".join(blocked.mapped("display_name")))

    dlm_supplier_id = fields.Many2one(
        related="lot_id.dlm_supplier_id", string="Nhà cung cấp", readonly=True)
    dlm_receipt_date = fields.Date(
        related="lot_id.dlm_receipt_date", string="Ngày nhập", readonly=True)

    @api.model
    def _dlm_available_qty(self, product, location, own_move_lines=None):
        """Số khả dụng (tồn − đã giữ chỗ) của SP tại 1 khu — nguồn chung cho mọi cảnh báo thiếu hàng."""
        if not product or not location:
            return 0.0
        con = self.sudo()._get_available_quantity(
            product, location, strict=False)
        if own_move_lines and location.parent_path:
            giu = own_move_lines.filtered(
                lambda ml: ml.product_id == product
                and ml.state not in ("done", "cancel")
                and ml.location_id.parent_path
                and ml.location_id.parent_path.startswith(location.parent_path))
            con += sum(giu.mapped("quantity_product_uom"))
        return con

    @api.model
    def _dlm_on_hand_qty(self, product, location):
        """Tồn thực (chưa trừ chỗ giữ) — chỉ để nói đúng lý do khi thiếu (hết hàng vs bị giữ chỗ)."""
        if not product or not location:
            return 0.0
        return sum(self.sudo().search([
            ("location_id", "child_of", location.id),
            ("product_id", "=", product.id),
        ]).mapped("quantity"))

    def action_dlm_open_reservations(self):
        """Màn Tồn kho: mở danh sách phiếu đang giữ chỗ đúng dòng tồn này."""
        self.ensure_one()
        domain = [
            ("product_id", "=", self.product_id.id),
            ("location_id", "=", self.location_id.id),
            ("state", "not in", ("done", "cancel")),
        ]
        if self.product_id.tracking != "none":
            domain.append(("lot_id", "=", self.lot_id.id))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.move.line",
            "name": _("Đang giữ chỗ — %s") % self.product_id.display_name,
            "view_mode": "tree",
            "views": [(self.env.ref(
                "dl_inventory.view_dl_reservation_tree").id, "tree")],
            "domain": domain,
            "target": "new",
        }

    # Đơn giá = giá BÁN phế liệu (list_price), không phải giá vốn ⇒ Thủ kho được xem.
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

    def action_dlm_to_scrap(self):
        """Màn Tồn kho: hoá phế liệu các dòng đang chọn (vật tư hỏng không đòi được NCC)."""
        quants = self.filtered(
            lambda q: not float_is_zero(
                q.quantity, precision_rounding=q.product_uom_id.rounding or 0.01)
            and q.quantity > 0)
        if not quants:
            raise UserError(_(
                "Chọn ít nhất một dòng tồn còn hàng để hoá phế liệu."))
        cam = quants.location_id.filtered("dlm_no_inventory")
        if cam:
            raise UserError(_(
                "Không hoá phế liệu thẳng từ khu quá cảnh (%s) được.\n\n"
                "Hàng ở đó đang gắn với một phiếu đang mở. Mở đúng phiếu trả "
                "nhà cung cấp rồi bấm <Chuyển thành phế liệu> trên đó — làm vậy mới giữ "
                "được dấu vết lô hàng này đi từ đâu ra."
            ) % ", ".join(cam.mapped("display_name")))
        picking = self.env["stock.picking"]._dlm_build_to_scrap(quants)
        return picking._dlm_open_picking(
            picking, _("Hoá phế liệu %s") % picking.name)

    def action_dlm_sell_scrap(self):
        """Màn Tồn kho: tạo phiếu Bán phế liệu (nháp, chưa gán khách) từ các dòng tồn đang chọn."""
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
