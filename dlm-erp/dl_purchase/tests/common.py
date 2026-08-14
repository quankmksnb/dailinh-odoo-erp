# -*- coding: utf-8 -*-
"""Nền dùng chung cho test Mua hàng.

Dữ liệu TỰ TẠO, không dựa vào seed: seed đổi theo nghiệp vụ, còn các bất biến ở
đây phải đúng với MỌI dữ liệu.
"""

from odoo import fields
from odoo.tests.common import TransactionCase


class DlPurchaseCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"]._dlm_main_warehouse()
        cls.loc_qc = cls.env.ref("dl_inventory.stock_location_nhan_qc")
        cls.loc_kho = cls.env.ref("dl_inventory.stock_location_nhan_kho")
        cls.loc_xuong = cls.env.ref("dl_inventory.stock_location_xuong")
        cls.loc_tp = cls.env.ref("dl_inventory.stock_location_tp")

        cls.vendor = cls.env["res.partner"].create({
            "name": "Thắng Hảo (mua hàng)", "partner_role": "supplier"})
        cls.customer = cls.env["res.partner"].create({
            "name": "Trường Đồng Sơn (mua hàng)", "partner_role": "customer"})

        cls.thep = cls.env["product.product"].create({
            "name": "Thép hộp 30x60x1.4 (mua hàng)",
            "product_kind": "material",
        })

    # ------------------------------------------------------------------
    @classmethod
    def _apply_price(cls, product, partner, price):
        """Bảng giá nhà cung cấp ĐÃ DUYỆT & ĐANG ÁP DỤNG."""
        return cls.env["product.supplierinfo"].create({
            "partner_id": partner.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "price": price,
            "date_start": fields.Date.today(),
            "approval_state": "approved",
            "is_applied": True,
        })

    def _mk_po(self, lines, partner=None, expected=True):
        """lines = [(product, qty, price)]"""
        return self.env["dl.purchase.order"].create({
            "partner_id": (partner or self.vendor).id,
            "date_expected": fields.Date.today() if expected else False,
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
            }) for product, qty, price in lines],
        })

    def _receive_po(self, order):
        """Chốt đơn → nhận đủ hàng → kiểm đạt hết ⇒ hàng nằm ở Kho vật tư.

        Đi TRỌN luồng thật (không dựng tồn bằng kiểm kê) vì chính chỗ nối giữa
        đơn mua và phiếu nhận là thứ đang được đo.
        """
        order.action_dlm_confirm()
        receipt = order.dlm_picking_ids[:1]
        for move in receipt.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        receipt.button_validate()
        qc = receipt.move_ids.move_dest_ids.picking_id.filtered(
            lambda p: p.picking_type_id.sequence_code == "KC")[:1]
        if qc:
            qc.action_dlm_pass_all()
            qc.action_dlm_validate_qc()
        return receipt

    def _lot_of(self, product, location=None):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", (location or self.loc_kho).id),
        ])
        return quants.mapped("lot_id")
