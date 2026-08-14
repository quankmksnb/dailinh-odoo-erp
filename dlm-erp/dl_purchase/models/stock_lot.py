# -*- coding: utf-8 -*-
"""K20 — Lô hàng mang theo GIÁ MUA của chính nó.

Thiết kế: ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §6.2.

Trước bản này lô đã truy được về NCC, ngày nhập và phiếu nguồn — nhưng **không
truy được về tiền**. Không có con số này thì câu "đơn hàng đó lãi bao nhiêu" chỉ
trả lời được bằng giá bảng NCC hôm nay, tức là bằng giá của một lô thép khác.
"""

from odoo import fields, models

from .dl_purchase_order import _DLM_BUY_PRICE_GROUPS


class StockLot(models.Model):
    _inherit = "stock.lot"

    # 🔴 `groups=` ở TẦNG FIELD, không phải chỉ ẩn trên view: thủ kho mở màn Lô
    # và Tồn kho hằng ngày — đây là chỗ dễ rò giá mua nhất của cả hệ thống
    # (DP-18 / §8.3 doc Kho).
    dlm_unit_cost = fields.Float(
        string="Giá mua đơn vị", digits="Product Price", copy=False,
        groups=_DLM_BUY_PRICE_GROUPS,
        help="Đồng trên ĐVT của mặt hàng, đóng lúc nhận hàng. Bất biến: lô đã "
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
        """Đóng giá lên lô. Chỉ ghi khi lô CHƯA có giá.

        Lô là bất biến: ghi đè giá của một lô đã nằm trong kho là viết lại lịch
        sử giá vốn của mọi đơn đã dùng nó.
        """
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
        """Giá dùng khi lô không đến từ đơn mua nào (§6.5).

        Thứ tự: giá NCC đang áp dụng → giá vốn tham chiếu → 0. Mọi ca ở đây đều
        gắn cờ ƯỚC TÍNH; con số 0 cuối cùng cũng vậy, vì "không biết" phải khác
        "bằng không".
        """
        self.ensure_one()
        product = self.product_id
        seller = product.sudo().seller_ids.filtered(lambda s: s.is_applied)[:1]
        if seller:
            try:
                return seller._dlm_reference_unit_cost(product)
            except Exception:  # noqa: BLE001 — bảng giá lệch ĐVT/tiền tệ
                pass
        return product.sudo().standard_price or 0.0
