# -*- coding: utf-8 -*-
"""P1: lọc mặt hàng theo ngữ cảnh phiếu (SM-03/SM-04).

Thiết kế: docs/Thiet_ke_kho_thong_minh_context_aware.md SM-03, SM-04.

Cái sai đắt nếu hỏng có HAI chiều, và SM-03 đã vấp cả hai:

* lọc thiếu thì mời giao thứ khách không đặt (SM-04, giao hàng); * lọc thừa thì mặt hàng
biến mất khỏi dropdown, thủ kho không phân biệt được "khu đó hết hàng" với "hệ thống
hỏng" (SM-03, sửa 2026-08-12).

Nên phần SM-03 dưới đây kiểm cả ba tín hiệu thay-cho-việc-ẩn: nhãn trong dropdown, cột
"Tồn ở nơi lấy" của dòng, và dải cảnh báo của phiếu.
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
            "name": "Khách hàng (test SM)", "partner_role": "customer",
            "mobile": "0900000012"})
        # Hàng thương mại, KHÔNG theo lô — test nói về lọc mặt hàng, không phải lô.
        cls.prod_a = cls.env["product.product"].create({
            "name": "Bản lề A (test SM)", "product_kind": "trading"})
        cls.prod_a.tracking = "none"
        cls.prod_b = cls.env["product.product"].create({
            "name": "Bản lề B (test SM)", "product_kind": "trading"})
        cls.prod_b.tracking = "none"

    # Tiện ích
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

    # ── SM-03: chuyển kho — hết hàng thì NÓI RA, không giấu đi ───────────────
    def _name_search(self, location):
        """Danh sách mặt hàng đúng như dropdown của dòng chuyển kho thấy."""
        return dict(self.env["product.product"]
                    .with_context(dlm_src_location_id=location.id)
                    .name_search(name="test SM"))

    def test_sm03_het_hang_van_hien_kem_nhan(self):
        """TC-INT-TestSmartDomains-001: Ca người dùng báo: mặt hàng hết ở nơi lấy vẫn phải
        hiện.

        Giấu nó đi thì thủ kho tìm không thấy và tưởng hệ thống hỏng — nên phải vừa
        hiện, vừa nói rõ là hết.
        """
        self._stock_up(self.prod_a, 5.0, self.loc_kho)  # prod_b: không có tồn
        labels = self._name_search(self.loc_kho)

        self.assertIn(self.prod_b.id, labels,
                      "Mặt hàng hết hàng bị biến mất khỏi danh sách.")
        self.assertIn("hết hàng", labels[self.prod_b.id])
        self.assertNotIn("hết hàng", labels[self.prod_a.id],
                         "Hàng còn tồn mà bị dán nhãn hết.")

    def test_sm03_ton_ve_khong_thi_dan_nhan(self):
        """TC-INT-TestSmartDomains-002: Tồn = 0 (quant còn bản ghi, hàng thì hết) — ca dễ
        nhầm nhất: người dùng thấy kho "có ghi" mặt hàng này nên chắc chắn phải tìm ra
        nó.
        """
        self._stock_up(self.prod_a, 5.0, self.loc_kho)
        self._stock_up(self.prod_a, -5.0, self.loc_kho)  # về 0, quant vẫn tồn tại
        labels = self._name_search(self.loc_kho)
        self.assertIn("hết hàng", labels[self.prod_a.id])

    def test_sm03_khong_co_context_thi_khong_doi_ten(self):
        """TC-INT-TestSmartDomains-009: Nhãn chỉ được xuất hiện ở ô có khai context — không
        rò sang màn khác (name_search của product.product dùng chung cả hệ thống).
        """
        labels = dict(self.env["product.product"].name_search(name="test SM"))
        self.assertNotIn("hết hàng", labels[self.prod_b.id])

    def test_sm03_ton_o_noi_lay_hien_tren_dong(self):
        """TC-INT-TestSmartDomains-003: Chọn xong vẫn phải thấy số: cột "Tồn ở nơi lấy" của
        dòng.
        """
        self._stock_up(self.prod_a, 5.0, self.loc_kho)
        picking = self._transfer(self.loc_kho)
        move = self.env["stock.move"].create({
            "name": self.prod_b.name,
            "picking_id": picking.id,
            "product_id": self.prod_b.id,
            "product_uom_qty": 2.0,
            "product_uom": self.prod_b.uom_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
        })
        self.assertEqual(move.dlm_src_available_qty, 0.0)

        move.product_id = self.prod_a
        self.assertEqual(move.dlm_src_available_qty, 5.0,
                         "Đổi mặt hàng mà số tồn đứng hình.")

    def test_sm03_het_hang_thi_canh_bao_khong_chan(self):
        """TC-INT-TestSmartDomains-010: Cho chọn thì phải cảnh báo hệ quả — nhưng không
        chặn: đặt trước phiếu chờ hàng về là nghiệp vụ hợp lệ.

        Dùng vật tư chứ không phải hàng thương mại: tuyến khu nhập thì xưởng chỉ hợp lệ
        với vật tư, mà dải đỏ "sai khu" sẽ che mất dải vàng "hết hàng" cần đo ở đây.
        """
        picking = self._transfer(self.loc_kho)
        self.env["stock.move"].create({
            "name": self.material.name,
            "picking_id": picking.id,
            "product_id": self.material.id,
            "product_uom_qty": 2.0,
            "product_uom": self.material.uom_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
        })
        self.assertEqual(picking.dlm_banner_level, "warning")
        self.assertIn("đang hết hàng", picking.dlm_banner_message)
        self.assertFalse(picking.dlm_blocked,
                         "Hết hàng chỉ là cảnh báo, không được chặn phiếu.")

    # SM-04: giao hàng lọc theo đơn
    def test_sm04_giao_chi_hien_hang_trong_don(self):
        """TC-INT-TestSmartDomains-004: Phiếu giao chỉ được chọn mặt hàng nằm trên đơn gắn
        với nó.
        """
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
        """TC-INT-TestSmartDomains-005: Phiếu giao chưa gắn đơn thì danh sách rỗng (form
        khoá bảng và mời chọn đơn, đây là nhánh guard ở view).
        """
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
        })
        self.assertFalse(picking.dlm_orderable_product_ids)

    # SM-07: nhận hàng cảnh báo khi NCC chưa có bảng giá đang áp dụng
    def test_sm07_khong_gia_thi_canh_bao(self):
        """TC-INT-TestSmartDomains-006: Nhận mặt hàng của NCC chưa có bảng giá đang áp dụng
        thì dải vàng phải nêu đích danh, nhưng không chặn nhận hàng.
        """
        receipt = self._make_receipt()  # self.material chưa có supplierinfo
        self.assertIn(
            self.material.display_name, receipt._dlm_receipt_unpriced_names())
        level, message, blocked = receipt._dlm_banner_receipt()
        self.assertEqual(level, "warning")
        self.assertFalse(
            blocked, "SM-07 chỉ cảnh báo, không được chặn nhận hàng.")
        self.assertIn("Chưa có bảng giá đang áp dụng", message)

    def test_sm07_co_gia_thi_khong_canh_bao(self):
        """TC-INT-TestSmartDomains-007: Mặt hàng đã có bảng giá đang áp dụng từ đúng NCC
        thì không cảnh báo.
        """
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
        """TC-INT-TestSmartDomains-008: Bảng giá đang áp dụng của NCC khác không tính,
        phiếu nhận của NCC này vẫn phải cảnh báo (giá vốn tính theo đúng NCC giao hàng).
        """
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
