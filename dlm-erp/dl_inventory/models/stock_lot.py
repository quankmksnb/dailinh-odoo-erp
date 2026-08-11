# -*- coding: utf-8 -*-
"""K4 — Truy vết lô: lô này của NCC nào, nhập ngày nào, theo phiếu nào.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §5.5, §10.2.

Ba field ở đây là **toàn bộ giá trị của việc bật lô**. Không có chúng, số lô chỉ
là một chuỗi ký tự vô nghĩa: khách báo nứt mối hàn thì vẫn không biết thép mua
của ai, về ngày nào.

Cách ghi: **đóng dấu lúc phiếu nhập hoàn tất**, không dùng compute.
Lý do: `stock.lot` không có quan hệ o2m tới dòng dịch chuyển, nên compute stored
sẽ phải khai `depends` vào thứ không tồn tại ⇒ không bao giờ tính lại. Đóng dấu
một lần tại `_action_done` vừa chắc chắn vừa đúng ngữ nghĩa "lô sinh ra từ lần
nhập ĐẦU TIÊN".
"""

from odoo import _, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    dlm_supplier_id = fields.Many2one(
        "res.partner", string="Nhà cung cấp", readonly=True, index=True,
        help="NCC giao lô này, lấy từ phiếu nhận hàng đầu tiên dùng lô.")
    dlm_receipt_date = fields.Date(
        string="Ngày nhập", readonly=True, index=True)
    dlm_receipt_picking_id = fields.Many2one(
        "stock.picking", string="Phiếu nhận", readonly=True,
        help="Phiếu nhận hàng đã sinh ra lô này.")

    def action_dlm_open_receipt(self):
        """Mở phiếu nhận đã sinh ra lô — chặng cuối của chuỗi truy vết
        (khách báo hỏng → đơn → BOM → lô vật tư → phiếu nhận → NCC)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.dlm_receipt_picking_id.id,
            "view_mode": "form",
            "name": _("Phiếu nhận %s") % self.dlm_receipt_picking_id.name,
        }
