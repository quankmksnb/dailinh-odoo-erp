# -*- coding: utf-8 -*-
"""Đơn vị tính đi kèm số lượng suốt chuỗi báo giá → đơn → file gửi khách.

"2" một mình không phải là cam kết bán được: 2 bộ bàn ghế và 2 mét máng điện là
hai đơn hàng khác hẳn nhau. Trước bản này dòng báo giá chỉ có mỗi con số, nên
đơn vị khách đặt ở RFQ rơi mất ngay tại bước lập báo giá.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationUom(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Xưởng cơ khí Hải Đăng (ĐVT)",
            "partner_role": "customer",
            "mobile": "0900000031",
        })
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

    def _mk_quotation(self, qty=2.0, uom=None):
        return self.env["dl.quotation"].create({
            "partner_id": self.customer.id,
            "state": "accepted",
            "line_ids": [(0, 0, {
                "name": "Khung thép hàn",
                "qty": qty,
                "uom_id": (uom or self.uom_kg).id,
                "price_unit": 1000000.0,
            })],
        })

    # ------------------------------------------------------------------
    def test_dong_moi_mac_dinh_co_don_vi(self):
        """Dòng Sales thêm tay không được để trống ĐVT."""
        line = self.env["dl.quotation.line"].create({
            "name": "Dòng thêm tay",
            "qty": 1.0,
        })
        self.assertEqual(line.uom_id, self.uom_unit)

    def test_don_vi_chep_sang_don_ban_hang(self):
        """Lên đơn phải mang theo ĐVT — xưởng làm hàng đọc con số này."""
        quo = self._mk_quotation()
        quo.action_create_sale_order()
        order = self.env["dl.sale.order"].search([("quotation_id", "=", quo.id)])
        self.assertEqual(len(order.line_ids), 1)
        self.assertEqual(order.line_ids.uom_id, self.uom_kg)

    # ------------------------------------------------------------------
    def test_file_gui_khach_co_don_vi_va_bo_duoi_so_0(self):
        """File gửi khách hiện "2 kg", không phải "2,00" trống đơn vị."""
        quo = self._mk_quotation(qty=2.0)
        dong = quo._document_context()["lines"][0]
        self.assertEqual(dong["qty_txt"], "2")
        self.assertEqual(dong["uom_txt"], self.uom_kg.name)

    def test_file_gui_khach_giu_phan_le_co_nghia(self):
        """Bỏ đuôi số 0 KHÔNG được làm tròn: 12,5 kg vẫn là 12,5 kg.

        So theo dấu thập phân của ngôn ngữ đang chạy chứ không viết cứng dấu
        phẩy: test chạy dưới en_US ("12.5"), người dùng thật chạy vi_VN
        ("12,5") — thứ đang đo là cái ĐUÔI SỐ 0, không phải dấu phân cách."""
        dp = self.env["res.lang"]._lang_get(
            self.env.lang or "en_US").decimal_point
        quo = self._mk_quotation(qty=12.5)
        self.assertEqual(
            quo._document_context()["lines"][0]["qty_txt"], "12%s5" % dp)
