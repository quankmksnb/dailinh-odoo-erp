# -*- coding: utf-8 -*-
"""Lô hàng mang theo giá mua của chính nó — nền cho giá vốn FIFO theo lô."""

from odoo import fields, models

from .dl_purchase_order import _DLM_BUY_PRICE_GROUPS


class StockLot(models.Model):
    _inherit = "stock.lot"

    # `groups=` ở TẦNG FIELD (không chỉ ẩn view): màn Lô/Tồn kho là chỗ dễ rò giá mua nhất.
    dlm_unit_cost = fields.Float(
        string="Giá mua đơn vị", digits="Product Price", copy=False,
        groups=_DLM_BUY_PRICE_GROUPS,
        help="Đồng trên đơn vị tính của mặt hàng, đóng lúc nhận hàng. Bất biến: lô đã "
             "nhập rồi thì giá của nó không đổi nữa.")
    dlm_purchase_order_id = fields.Many2one(
        "dl.purchase.order", string="Đơn mua nguồn", readonly=True, copy=False,
        index=True, groups=_DLM_BUY_PRICE_GROUPS)
    dlm_cost_is_estimated = fields.Boolean(
        string="Giá ước tính", readonly=True, copy=False,
        groups=_DLM_BUY_PRICE_GROUPS,
        help="Bật khi giá KHÔNG đến từ đơn mua (nhận tay, tồn đầu kỳ, hàng "
             "xưởng làm ra). Báo cáo giá vốn phải nói ra điều này — một con số "
             "sai mà trông chắc chắn thì tệ hơn một con số sai có dán nhãn.")

    def _dlm_stamp_cost(self, unit_cost, purchase_order=None):
        """Đóng giá lên lô, chỉ ghi khi lô CHƯA có giá (lô bất biến, không ghi đè)."""
        for lot in self:
            if lot.sudo().dlm_unit_cost:
                continue
            lot.sudo().write({
                "dlm_unit_cost": unit_cost,
                "dlm_purchase_order_id": purchase_order.id
                if purchase_order else False,
                "dlm_cost_is_estimated": not purchase_order,
            })
        return True

    def _dlm_fallback_cost(self):
        """Giá khi lô không đến từ đơn mua nào: giá NCC đang áp dụng → giá vốn tham chiếu → 0."""
        self.ensure_one()
        product = self.product_id
        seller = product.sudo().seller_ids.filtered(lambda s: s.is_applied)[:1]
        if seller:
            try:
                return seller._dlm_reference_unit_cost(product)
            except Exception:  # noqa: BLE001 — bảng giá lệch ĐVT/tiền tệ
                pass
        return product.sudo().standard_price or 0.0
