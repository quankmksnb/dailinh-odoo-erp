# -*- coding: utf-8 -*-
"""Nền dùng chung cho test phân hệ Kho.

Dữ liệu test TỰ TẠO, không dựa vào seed của dl_product/dl_demo: seed có thể đổi
theo nghiệp vụ, còn các bất biến ở đây phải đúng với MỌI dữ liệu.
"""

from odoo.tests.common import TransactionCase


class DlInventoryCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.loc_qc = cls.env.ref("dl_inventory.stock_location_nhan_qc")
        cls.loc_kho = cls.env.ref("dl_inventory.stock_location_nhan_kho")
        cls.loc_tra = cls.env.ref("dl_inventory.stock_location_nhan_tra")
        cls.loc_xuong = cls.env.ref("dl_inventory.stock_location_xuong")
        cls.loc_xuong_pl = cls.env.ref("dl_inventory.stock_location_xuong_pl")
        cls.loc_tp = cls.env.ref("dl_inventory.stock_location_tp")
        cls.loc_vendors = cls.env.ref("stock.stock_location_suppliers")

        cls.vendor = cls.env["res.partner"].create({"name": "NCC Thép (test)"})

        # Vật tư: create() của dl_product tự đặt storable + theo lô.
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 25x50x1.4 (test)",
            "product_kind": "material",
        })
        # Giá vốn do hệ thống quản (_DLM_PROTECTED_FIELDS chặn ghi thường).
        cls.material.sudo().standard_price = 200000.0

    def _make_receipt(self, product=None, qty=100.0):
        """Phiếu nhận hàng NCC ở trạng thái sẵn sàng nhập số."""
        product = product or self.material
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": self.vendor.id,
            "location_id": self.loc_vendors.id,
            "location_dest_id": self.loc_qc.id,
            "move_ids": [(0, 0, {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _receive(self, picking, qty=100.0):
        """Nhận đủ số và xác nhận phiếu."""
        picking.move_ids.quantity = qty
        picking.move_ids.picked = True
        picking.button_validate()
        return picking

    def _qc_picking(self, receipt):
        """Phiếu [2] "Kiểm & cất hàng" tuyến nhận 2 bước tự sinh ra."""
        return receipt.move_ids.move_dest_ids.picking_id.filtered(
            lambda p: p.picking_type_id.sequence_code == "KC")[:1]

    def _qty_at(self, location, product=None):
        """Tồn thực tế của một mặt hàng tại một vị trí."""
        quants = self.env["stock.quant"].search([
            ("location_id", "=", location.id),
            ("product_id", "=", (product or self.material).id),
        ])
        return sum(quants.mapped("quantity"))
