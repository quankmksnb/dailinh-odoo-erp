# -*- coding: utf-8 -*-
"""K3: số lô tự sinh và giá vốn bất khả xâm phạm.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §3.4, §3.8.

Hai bất biến ở đây là loại lỗi "sai âm thầm": không có test thì hỏng mà không
lỗi nào nổ, ví dụ hàng nhập không lô (mất truy vết vĩnh viễn), hoặc giá vốn bị
Odoo ghi đè (giá báo khách nhảy theo từng phiếu nhập).
"""

from odoo import fields
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestLotAndCost(DlInventoryCase):

    def test_vat_tu_mac_dinh_theo_lo(self):
        """TC-INT-TestLotAndCost-001: §3.4: vật tư và BTP tạo mới thì tự theo lô, không
        phải nhớ tick tay.

        Lô là mắt xích duy nhất truy ngược hàng lỗi về NCC và ngày nhập. Vật tư nhập khi
        chưa bật lô thì vĩnh viễn không có lô, không vá lại được.
        """
        self.assertEqual(self.material.tracking, "lot")
        self.assertEqual(self.material.detailed_type, "product")

        btp = self.env["product.product"].create({
            "name": "Chân bàn đã cắt (test)",
            "product_kind": "material_processed",
        })
        self.assertEqual(btp.tracking, "lot")

    def test_hang_thuong_mai_khong_theo_lo(self):
        """TC-INT-TestLotAndCost-002: §3.4: hàng thương mại mua đi bán lại, không phải
        nguồn lỗi gia công, nên đừng bắt thủ kho nhập lô cho nó.
        """
        trading = self.env["product.product"].create({
            "name": "Ốc vít đóng gói (test)",
            "product_kind": "trading",
        })
        self.assertEqual(trading.tracking, "none")

    def test_phe_lieu_khong_theo_lo(self):
        """TC-INT-TestLotAndCost-003: §3.4: phế liệu mang product_kind='material' nhưng
        không theo lô.

        Phế liệu là vụn gom từ nhiều lô khác nhau trong cùng thùng chứa. Bắt nhập số lô
        mỗi lần cân là công vô ích và không truy vết được gì.
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
            "Gắn làm SP phế liệu thì phải tự tắt theo lô.")

    def test_so_lo_tu_sinh_khi_nhan_hang(self):
        """TC-INT-TestLotAndCost-004: §15 câu 1: Đại Linh tự sinh số lô, thủ kho để trống
        vẫn nhận được.

        Số của NCC không có định dạng thống nhất, dễ trùng giữa các NCC và dễ gõ sai,
        trong khi lô là mắt xích truy vết.
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
        """TC-INT-TestLotAndCost-005: §3.4: tự sinh chỉ là mặc định. Lô ghi trên chứng từ
        NCC vẫn nhập được khi thủ kho muốn dùng số riêng.
        """
        picking = self._make_receipt()
        picking.move_line_ids.lot_name = "NCC-ABC-123"
        self._receive(picking)
        self.assertEqual(picking.move_line_ids.lot_id.name, "NCC-ABC-123")

    def test_gia_von_khong_doi_sau_khi_nhap_kho(self):
        """TC-INT-TestLotAndCost-006: §3.8: nhập kho không được đụng vào standard_price.

        standard_price do _dlm_recompute_reference_cost quản, lấy từ giá NCC đang áp
        dụng. Nếu bật định giá AVCO/FIFO, Odoo cũng ghi field đó mỗi lần nhập, hai nguồn
        tranh nhau làm giá vốn nhảy theo từng phiếu nhập, kéo theo giá báo khách nhảy
        theo, phá luồng duyệt giá 3 nấc.
        """
        cost_before = self.material.standard_price
        self.assertGreater(cost_before, 0, "Bối cảnh: vật tư phải có giá vốn.")

        self._receive(self._make_receipt())

        self.material.invalidate_recordset(["standard_price"])
        self.assertEqual(
            self.material.standard_price, cost_before,
            "Giá vốn bị đổi sau khi nhập kho thì đang có nguồn thứ hai ghi đè "
            "standard_price (kiểm định giá tồn kho).")

    def test_khong_co_dinh_gia_ton_kho(self):
        """TC-INT-TestLotAndCost-007: §3.8: lá chắn canh gác, cơ chế định giá tồn kho phải
        vắng mặt.

        `account` và `stock_account` đã gỡ khỏi dự án (2026-08-11). Nếu ai cài lại,
        `stock_account` (auto_install) quay lại và mở đường bật AVCO. Test này fail
        ngay, thay vì để phát hiện khi giá báo khách đã sai.
        """
        quant_fields = self.env["stock.quant"].fields_get()
        self.assertNotIn(
            "value", quant_fields,
            "stock_account đã quay lại thì bật được định giá AVCO. Xem §3.8.")

        categ_fields = self.env["product.category"].fields_get()
        self.assertNotIn("property_valuation", categ_fields)
        self.assertNotIn("property_cost_method", categ_fields)
