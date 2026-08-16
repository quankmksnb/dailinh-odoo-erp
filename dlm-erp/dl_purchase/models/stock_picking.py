# -*- coding: utf-8 -*-
"""Phiếu nhận hàng gắn đơn mua nguồn và đóng giá mua lên lô lúc xác nhận."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .dl_purchase_order import _DLM_BUY_PRICE_GROUPS


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dlm_purchase_order_id = fields.Many2one(
        "dl.purchase.order", string="Đơn mua nguồn", readonly=True, copy=False,
        index=True, ondelete="set null")
    dlm_purchase_name = fields.Char(
        string="Đơn mua", related="dlm_purchase_order_id.name", readonly=True,
        help="Nhân bản để thủ kho THẤY được số đơn mua mà không cần quyền đọc "
             "đơn mua — trên đó có giá.")

    def button_validate(self):
        """Xác nhận phiếu nhận NCC ⇒ đóng giá mua lên từng lô vừa sinh ra."""
        result = super().button_validate()
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            picking._dlm_stamp_lot_costs()
        return result

    def _dlm_stamp_lot_costs(self):
        """Gán giá cho mọi lô của phiếu nhận — không có đơn mua thì lấy giá bảng NCC và gắn cờ ước tính."""
        self.ensure_one()
        order = self.dlm_purchase_order_id.sudo()
        prices = {}
        if order:
            for line in order.line_ids:
                prices[line.product_id.id] = line.price_unit
        for move_line in self.move_line_ids:
            lot = move_line.lot_id
            if not lot:
                continue
            unit_cost = prices.get(move_line.product_id.id)
            if unit_cost:
                lot._dlm_stamp_cost(unit_cost, purchase_order=order)
            else:
                lot._dlm_stamp_cost(lot._dlm_fallback_cost())
        return True

    # ------------------------------------------------------------------
    # Điều hướng
    # ------------------------------------------------------------------
    def action_dlm_open_purchase_order(self):
        """Nút mở đơn mua nguồn từ phiếu nhận (chỉ Mua hàng/CEO/Admin/Kế toán)."""
        self.ensure_one()
        if not self.dlm_purchase_order_id:
            raise UserError(_("Phiếu %s không gắn đơn mua nào.") % self.name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Đơn mua %s") % self.dlm_purchase_order_id.name,
            "res_model": "dl.purchase.order",
            "res_id": self.dlm_purchase_order_id.id,
            "view_mode": "form",
            "target": "current",
        }


class StockMove(models.Model):
    _inherit = "stock.move"

    # Cột chỉ dùng ở báo cáo giá vốn — khai ở đây để không phải join tay.
    dlm_lot_cost = fields.Float(
        string="Giá vốn lô", compute="_compute_dlm_lot_cost",
        digits="Product Price", groups=_DLM_BUY_PRICE_GROUPS)

    @api.depends("move_line_ids.quantity", "move_line_ids.lot_id")
    def _compute_dlm_lot_cost(self):
        for move in self:
            move.dlm_lot_cost = move._dlm_fifo_cost()

    def _dlm_fifo_cost(self):
        """Tiền của move theo giá của chính lô đã lấy (lô do removal_strategy chọn lúc giữ chỗ)."""
        total = 0.0
        for line in self.move_line_ids:
            lot = line.lot_id.sudo()
            unit = lot.dlm_unit_cost if lot else 0.0
            if not unit:
                # Hàng không theo lô hoặc lô chưa có giá: rơi về giá vốn tham chiếu.
                unit = line.product_id.sudo().standard_price or 0.0
            total += line.quantity * unit
        return total
