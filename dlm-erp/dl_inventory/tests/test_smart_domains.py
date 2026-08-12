# -*- coding: utf-8 -*-
"""P1 — Lọc mặt hàng theo ngữ cảnh phiếu (SM-03/SM-04).

Thiết kế: docs/Thiet_ke_kho_thong_minh_context_aware.md SM-03, SM-04.

Hai field computed nuôi domain của product_id trên dòng hàng. Cái sai đắt nếu
hỏng: dropdown lọc SAI ⇒ hoặc mời chọn mặt hàng không thể giữ chỗ (chuyển kho),
hoặc cho giao thứ khách không đặt (giao hàng). Test kiểm chính LOGIC compute —
domain trong view đã được Odoo validate lúc nạp.
"""

from odoo import fields
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestSmartDomains(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách hàng (test SM)", "partner_role": "customer"})
        # Hàng thương mại, KHÔNG theo lô — test nói về lọc mặt hàng, không phải lô.
        cls.prod_a = cls.env["product.product"].create({
            "name": "Bản lề A (test SM)", "product_kind": "trading"})
        cls.prod_a.tracking = "none"
        cls.prod_b = cls.env["product.product"].create({
            "name": "Bản lề B (test SM)", "product_kind": "trading"})
        cls.prod_b.tracking = "none"

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _stock_up(self, product, qty, location):
        """Đặt tồn đầu kỳ trực tiếp, không đi qua phiếu nhận."""
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _transfer(self, source):
        return self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": source.id,
            "location_dest_id": self.loc_xuong.id,
        })

    def _order(self, product, qty=10.0):
        return self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "qty": qty,
                "price_unit": 50000.0,
            })],
        })

    # ── SM-03: chuyển kho lọc theo tồn ở nguồn ───────────────────────────────
    def test_sm03_nguon_chi_hien_hang_co_ton(self):
        """SP có tồn ở nguồn thì vào danh sách; SP không tồn thì không."""
        self._stock_up(self.prod_a, 5.0, self.loc_kho)
        picking = self._transfer(self.loc_kho)
        available = picking.dlm_source_available_product_ids
        self.assertIn(self.prod_a, available)
        self.assertNotIn(
            self.prod_b, available,
            "Mặt hàng không có tồn ở nguồn không được vào danh sách.")

    def test_sm03_ton_bang_khong_khong_tinh(self):
        """Tồn = 0 (quant có nhưng hết hàng) KHÔNG được coi là có sẵn —
        đây chính là bẫy 'hai điều kiện trên o2m' mà compute né bằng search."""
        self._stock_up(self.prod_a, 5.0, self.loc_kho)
        self._stock_up(self.prod_a, -5.0, self.loc_kho)  # về 0, quant vẫn tồn tại
        picking = self._transfer(self.loc_kho)
        self.assertNotIn(
            self.prod_a, picking.dlm_source_available_product_ids,
            "Tồn 0 không được hiện — reservation sẽ thất bại.")

    def test_sm03_doi_nguon_thi_danh_sach_doi_theo(self):
        """Đổi vị trí nguồn ⇒ compute chạy lại theo nguồn mới."""
        self._stock_up(self.prod_a, 5.0, self.loc_kho)
        picking = self._transfer(self.loc_kho)
        self.assertIn(self.prod_a, picking.dlm_source_available_product_ids)
        picking.location_id = self.loc_xuong  # không có tồn ở đây
        self.assertNotIn(self.prod_a, picking.dlm_source_available_product_ids)

    # ── SM-04: giao hàng lọc theo đơn ────────────────────────────────────────
    def test_sm04_giao_chi_hien_hang_trong_don(self):
        """Phiếu giao chỉ được chọn mặt hàng nằm trên đơn gắn với nó."""
        order = self._order(self.prod_a)
        order.action_dlm_create_delivery()
        picking = order.dlm_picking_ids[:1]
        self.assertTrue(picking)
        orderable = picking.dlm_orderable_product_ids
        self.assertIn(self.prod_a, orderable)
        self.assertNotIn(
            self.prod_b, orderable,
            "Mặt hàng ngoài đơn không được vào danh sách giao.")

    def test_sm04_khong_gan_don_thi_danh_sach_rong(self):
        """Phiếu giao chưa gắn đơn ⇒ danh sách rỗng (form khoá bảng + mời
        chọn đơn — nhánh guard ở view)."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
        })
        self.assertFalse(picking.dlm_orderable_product_ids)

    # ── SM-07: nhận hàng cảnh báo khi NCC chưa có bảng giá đang áp dụng ───────
    def test_sm07_khong_gia_thi_canh_bao(self):
        """Nhận mặt hàng NCC chưa có bảng giá đang áp dụng ⇒ dải vàng nêu đích
        danh, KHÔNG chặn nhận hàng."""
        receipt = self._make_receipt()  # self.material — chưa có supplierinfo
        self.assertIn(
            self.material.display_name, receipt._dlm_receipt_unpriced_names())
        level, message, blocked = receipt._dlm_banner_receipt()
        self.assertEqual(level, "warning")
        self.assertFalse(
            blocked, "SM-07 chỉ cảnh báo, không được chặn nhận hàng.")
        self.assertIn("Chưa có bảng giá đang áp dụng", message)

    def test_sm07_co_gia_thi_khong_canh_bao(self):
        """Mặt hàng đã có bảng giá đang áp dụng từ đúng NCC ⇒ không cảnh báo."""
        self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": self.material.product_tmpl_id.id,
            "price": 200000.0,
            "date_start": fields.Date.context_today(self.material),
            "approval_state": "approved",
            "is_applied": True,
        })
        receipt = self._make_receipt()
        self.assertFalse(
            receipt._dlm_receipt_unpriced_names(),
            "Đã có bảng giá đang áp dụng thì không được cảnh báo thiếu giá.")

    def test_sm07_khac_ncc_van_canh_bao(self):
        """Bảng giá đang áp dụng của NCC KHÁC không tính — phiếu nhận của NCC
        này vẫn phải cảnh báo (giá vốn theo đúng NCC giao)."""
        other_vendor = self.env["res.partner"].create({"name": "NCC khác (test)"})
        self.env["product.supplierinfo"].create({
            "partner_id": other_vendor.id,
            "product_tmpl_id": self.material.product_tmpl_id.id,
            "price": 200000.0,
            "date_start": fields.Date.context_today(self.material),
            "approval_state": "approved",
            "is_applied": True,
        })
        receipt = self._make_receipt()  # partner = self.vendor
        self.assertIn(
            self.material.display_name, receipt._dlm_receipt_unpriced_names())
