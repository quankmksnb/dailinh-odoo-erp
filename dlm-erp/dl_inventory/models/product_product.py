# -*- coding: utf-8 -*-
"""Ô chọn mặt hàng trên phiếu kho: gắn nhãn "hết hàng ở nơi lấy" ngay trong dropdown."""

from odoo import _, api, models
from odoo.tools.float_utils import float_compare


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Gắn hậu tố "hết hàng" trong dropdown khi ô chọn truyền `dlm_src_location_id` qua context."""
        res = super().name_search(
            name=name, args=args, operator=operator, limit=limit)
        location_id = self.env.context.get("dlm_src_location_id")
        if not location_id or not res:
            return res
        on_hand = self._dlm_qty_by_product(
            location_id, [row[0] for row in res])
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure")
        return [
            (product_id, label
             if float_compare(on_hand.get(product_id, 0.0), 0.0,
                              precision_digits=precision) > 0
             else _("%s — hết hàng ở nơi lấy") % label)
            for product_id, label in res
        ]

    @api.model
    def _dlm_qty_by_product(self, location_id, product_ids):
        """Tổng tồn theo mặt hàng tại/dưới một vị trí — một truy vấn gộp (sudo: chỉ đọc số lượng)."""
        groups = self.env["stock.quant"].sudo()._read_group(
            [("location_id", "child_of", location_id),
             ("product_id", "in", product_ids)],
            groupby=["product_id"], aggregates=["quantity:sum"])
        return {product.id: quantity for product, quantity in groups}
