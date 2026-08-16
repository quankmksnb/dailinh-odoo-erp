# -*- coding: utf-8 -*-
"""Truy vết lô: lô này của NCC nào, nhập ngày nào, theo phiếu nào."""

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = "stock.lot"

    dlm_supplier_id = fields.Many2one(
        "res.partner", string="Nhà cung cấp", readonly=True, index=True,
        help="Nhà cung cấp giao lô này, lấy từ phiếu nhận hàng đầu tiên dùng lô.")
    dlm_receipt_date = fields.Date(
        string="Ngày nhập", readonly=True, index=True)
    dlm_receipt_picking_id = fields.Many2one(
        "stock.picking", string="Phiếu nhận", readonly=True,
        help="Phiếu nhận hàng đã sinh ra lô này.")

    def action_dlm_open_receipt(self):
        """Màn Truy vết lô: mở phiếu nhận đã sinh ra lô này."""
        self.ensure_one()
        receipt = self.dlm_receipt_picking_id
        if not receipt:
            raise UserError(_("Lô %s chưa gắn phiếu nhận nào.") % self.name)
        return receipt._dlm_open_picking(
            receipt, _("Phiếu nhận %s") % receipt.name)
