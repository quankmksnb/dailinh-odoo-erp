# -*- coding: utf-8 -*-
"""K3 — Số lô tự sinh & giá vốn bất khả xâm phạm.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §3.4, §3.8.

Hai bất biến ở đây là loại "sai âm thầm": không có test thì hỏng mà KHÔNG lỗi
nào nổ — hàng nhập không lô (mất truy vết vĩnh viễn), hoặc giá vốn bị Odoo ghi
đè (giá báo khách nhảy theo từng phiếu nhập).
"""

from odoo import fields
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestLotAndCost(DlInventoryCase):

    def test_vat_tu_mac_dinh_theo_lo(self):
        """§3.4 — Vật tư & BTP tạo mới ⇒ theo lô, không phải nhớ tick tay.

        Lô là mắt xích duy nhất truy ngược hàng lỗi về NCC + ngày nhập. Vật tư
        nhập khi chưa bật lô thì VĨNH VIỄN không có lô — không vá được.
        """
        self.assertEqual(self.material.tracking, "lot")
        self.assertEqual(self.material.detailed_type, "product")

        btp = self.env["product.product"].create({
            "name": "Chân bàn đã cắt (test)",
            "product_kind": "material_processed",
        })
        self.assertEqual(btp.tracking, "lot")

    def test_hang_thuong_mai_khong_theo_lo(self):
        """§3.4 — Hàng thương mại mua đi bán lại, KHÔNG phải nguồn lỗi gia công
        ⇒ đừng bắt thủ kho nhập lô cho nó."""
        trading = self.env["product.product"].create({
            "name": "Ốc vít đóng gói (test)",
            "product_kind": "trading",
        })
        self.assertEqual(trading.tracking, "none")

    def test_phe_lieu_khong_theo_lo(self):
        """§3.4 — Phế liệu mang product_kind='material' nhưng KHÔNG theo lô.

        Phế liệu là vụn gom từ nhiều lô khác nhau trong cùng thùng chứa: bắt
        nhập số lô mỗi lần cân là công vô ích và không truy vết được gì.
        """
        scrap = self.env["product.product"].create({
            "name": "Phế liệu thép (test)",
            "product_kind": "material",
        })
        self.material.sudo().write({
            "dlm_has_recovery": True,
            "dlm_scrap_product_id": scrap.id,
        })
        scrap.invalidate_recordset(["tracking"])
        self.assertEqual(
            scrap.tracking, "none",
            "Gắn làm SP phế liệu ⇒ phải tự tắt theo lô.")

    def test_so_lo_tu_sinh_khi_nhan_hang(self):
        """§15 câu 1 — Đại Linh TỰ SINH số lô: thủ kho để trống vẫn nhận được.

        Số của NCC không có định dạng thống nhất, dễ trùng giữa các NCC và dễ gõ
        sai — mà lô là mắt xích truy vết.
        """
        picking = self._make_receipt()
        self.assertFalse(picking.move_line_ids.lot_name,
                         "Bối cảnh: thủ kho CHƯA nhập lô.")

        self._receive(picking)

        lots = picking.move_line_ids.lot_id
        self.assertEqual(len(lots), 1)
        self.assertTrue(
            lots.name.startswith("LO/%s/" % fields.Date.today().year),
            "Số lô phải theo mẫu LO/<năm>/xxxxx, thực tế: %s" % lots.name)

    def test_thu_kho_van_go_de_duoc_so_lo(self):
        """§3.4 — Tự sinh chỉ là MẶC ĐỊNH. Lô ghi trên chứng từ NCC vẫn nhập
        được khi thủ kho muốn dùng số riêng."""
        picking = self._make_receipt()
        picking.move_line_ids.lot_name = "NCC-ABC-123"
        self._receive(picking)
        self.assertEqual(picking.move_line_ids.lot_id.name, "NCC-ABC-123")

    def test_gia_von_khong_doi_sau_khi_nhap_kho(self):
        """🔴 §3.8 — Nhập kho KHÔNG được đụng vào standard_price.

        standard_price do _dlm_recompute_reference_cost quản, lấy từ giá NCC
        đang áp dụng. Nếu bật định giá AVCO/FIFO, Odoo cũng ghi field đó mỗi lần
        nhập ⇒ hai nguồn tranh nhau ⇒ giá vốn nhảy theo từng phiếu nhập ⇒ GIÁ
        BÁO KHÁCH nhảy theo, phá luồng duyệt giá 3 nấc.
        """
        cost_before = self.material.standard_price
        self.assertGreater(cost_before, 0, "Bối cảnh: vật tư phải có giá vốn.")

        self._receive(self._make_receipt())

        self.material.invalidate_recordset(["standard_price"])
        self.assertEqual(
            self.material.standard_price, cost_before,
            "Giá vốn bị đổi sau khi nhập kho ⇒ đang có nguồn thứ hai ghi đè "
            "standard_price (kiểm định giá tồn kho).")

    def test_khong_co_dinh_gia_ton_kho(self):
        """🔴 §3.8 — Lá chắn canh gác: cơ chế định giá tồn kho phải VẮNG MẶT.

        `account` + `stock_account` đã gỡ khỏi dự án 2026-08-11. Nếu ai cài lại,
        `stock_account` (auto_install) quay lại và mở đường bật AVCO — test này
        đỏ NGAY, thay vì phát hiện khi giá báo khách đã sai.
        """
        quant_fields = self.env["stock.quant"].fields_get()
        self.assertNotIn(
            "value", quant_fields,
            "stock_account đã quay lại ⇒ bật được định giá AVCO. Xem §3.8.")

        categ_fields = self.env["product.category"].fields_get()
        self.assertNotIn("property_valuation", categ_fields)
        self.assertNotIn("property_cost_method", categ_fields)
