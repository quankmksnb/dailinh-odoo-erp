# -*- coding: utf-8 -*-
"""K3 — Số lô tự sinh khi nhận hàng NCC.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §3.4 và §15 câu 1 (đã chốt 2026-08-11:
Đại Linh TỰ SINH số lô, không dùng số in trên chứng từ NCC).
"""

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        self._dlm_autofill_lot_names()
        return super().button_validate()

    def _action_done(self):
        """K4 — Đóng dấu nguồn gốc lô ngay khi phiếu nhập hoàn tất.

        Đặt ở `_action_done` chứ không ở `button_validate` vì button_validate có
        thể trả về wizard (hỏi tạo phiếu chờ giao tiếp) và phiếu chưa xong thật.
        """
        res = super()._action_done()
        self._dlm_stamp_lot_origin()
        return res

    def _dlm_stamp_lot_origin(self):
        """Ghi NCC + ngày nhập + phiếu nguồn lên các lô vừa nhận.

        Chỉ phiếu NHẬP mới đóng dấu, và chỉ đóng dấu lô CHƯA có nguồn: lô sinh
        ra từ lần nhập đầu tiên, những lần luân chuyển sau không được ghi đè
        (nếu không, truy vết sẽ trỏ về phiếu chuyển kho nội bộ thay vì NCC).
        """
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            lots = picking.move_line_ids.lot_id.filtered(
                lambda lot: not lot.dlm_receipt_picking_id)
            if lots:
                lots.sudo().write({
                    "dlm_supplier_id": picking.partner_id.id,
                    "dlm_receipt_date": picking.date_done or fields.Date.context_today(picking),
                    "dlm_receipt_picking_id": picking.id,
                })
        return True

    def _dlm_autofill_lot_names(self):
        """Điền số lô tự sinh cho dòng NHẬN HÀNG còn trống.

        Chỉ áp cho phiếu nhập: hàng vào kho là nơi lô được SINH RA. Phiếu xuất /
        chuyển kho tiêu thụ lô đã có — tự sinh ở đó sẽ đẻ lô ma không có nguồn.

        Chỉ điền khi người dùng để trống: thủ kho vẫn có thể gõ đè số riêng.
        """
        sequence = self.env["ir.sequence"].sudo()
        for line in self.move_line_ids:
            if (line.picking_id.picking_type_id.code == "incoming"
                    and line.product_id.tracking == "lot"
                    and not line.lot_id and not line.lot_name):
                line.lot_name = sequence.next_by_code("stock.lot.serial")
        return True
