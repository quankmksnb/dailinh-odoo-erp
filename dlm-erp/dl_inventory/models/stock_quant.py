# -*- coding: utf-8 -*-
"""K4 — Màn Tồn kho đọc thẳng nguồn gốc lô.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §11.2.

Hai field related để thủ kho trả lời được "thép đang nằm kho này của ai, về ngày
nào" mà KHÔNG phải mở từng lô. Không lưu (`store=False`): dữ liệu đã nằm ở
stock.lot, nhân bản sang quant chỉ tạo thêm chỗ lệch.
"""

from odoo import fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    dlm_supplier_id = fields.Many2one(
        related="lot_id.dlm_supplier_id", string="Nhà cung cấp", readonly=True)
    dlm_receipt_date = fields.Date(
        related="lot_id.dlm_receipt_date", string="Ngày nhập", readonly=True)
