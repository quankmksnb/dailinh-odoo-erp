# -*- coding: utf-8 -*-
"""K19 — Vòng đời đơn mua và mối nối sang phiếu nhận."""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseOrder(DlPurchaseCase):

    def test_chot_don_sinh_phieu_nhan_gan_don_mua(self):
        """Chốt đơn ⇒ phiếu nhận vào hàng đợi thủ kho, có neo về đơn mua.

        Đỏ = Mua hàng chốt xong nhưng thủ kho không thấy việc gì, hoặc hàng về
        mà không truy được về giá đã chốt.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])

        order.action_dlm_confirm()

        self.assertEqual(order.state, "confirmed")
        picking = order.dlm_picking_ids
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.dlm_purchase_order_id, order)
        self.assertEqual(picking.partner_id, self.vendor)
        self.assertEqual(picking.picking_type_id.code, "incoming")
        self.assertEqual(picking.origin, order.name)

    def test_chot_don_thieu_gia_bi_chan(self):
        """MH-05 — dòng giá 0 ⇒ lô nhập về mang giá 0.

        Đỏ = giá vốn thực tế của MỌI đơn bán dùng lô đó sai vĩnh viễn, và không
        có gì báo động vì 0 cũng là một con số hợp lệ.
        """
        order = self._mk_po([(self.thep, 30.0, 0.0)])

        with self.assertRaises(UserError) as err:
            order.action_dlm_confirm()

        self.assertIn(self.thep.display_name, err.exception.args[0])

    def test_chot_don_thieu_ngay_ve_bi_chan(self):
        """MH-06 — không có ngày về thì màn Điều phối không tính được "đang về".

        Đỏ = đơn bán bị mua chồng: lần điều phối sau vẫn thấy thiếu vì hàng đang
        trên đường không được đếm.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)], expected=False)

        with self.assertRaises(UserError):
            order.action_dlm_confirm()

    def test_hai_dong_cung_mat_hang_bi_chan(self):
        """MH-12 — hai giá cho một mặt hàng thì lúc nhận không biết đóng giá nào.

        Đỏ = lô mang giá của dòng đầu tiên một cách tuỳ tiện.
        """
        order = self._mk_po([
            (self.thep, 30.0, 200000.0),
            (self.thep, 10.0, 220000.0),
        ])

        with self.assertRaises(UserError) as err:
            order.action_dlm_confirm()

        self.assertIn(self.thep.display_name, err.exception.args[0])

    def test_khong_dat_mua_phe_lieu(self):
        """MH-04 — phế liệu là thứ Đại Linh BÁN đi."""
        scrap = self.env["product.product"].create({
            "name": "Phế liệu thép (mua hàng)", "product_kind": "material"})
        scrap.sudo().dlm_is_scrap = True
        order = self._mk_po([(scrap, 50.0, 5000.0)])

        with self.assertRaises(UserError):
            order.action_dlm_confirm()

    def test_huy_don_da_nhan_hang_bi_chan(self):
        """🔴 MH-10 — hàng đã vào kho mà chứng từ mua biến mất là lỗ hổng đối soát.

        Đỏ = kiểm kê thấy 30 cây thép không giải thích được từ đâu ra.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self._receive_po(order)

        with self.assertRaises(UserError) as err:
            order.action_dlm_cancel()

        self.assertIn("Trả hàng nhà cung cấp", err.exception.args[0])

    def test_huy_don_chua_nhan_thi_huy_luon_phieu(self):
        """MH-11 — phiếu mồ côi nằm trong hàng đợi thủ kho là việc chết."""
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        order.action_dlm_confirm()
        picking = order.dlm_picking_ids

        order.action_dlm_cancel()

        self.assertEqual(order.state, "cancelled")
        self.assertEqual(picking.state, "cancel")

    def test_gui_hoi_gia_ghi_moc_thoi_gian(self):
        """Mốc gửi phải nằm trong hệ thống, dù mail gửi bằng Zalo.

        Đỏ = không ai trả lời được "gửi NCC lâu chưa" ⇒ đơn nằm chờ vô thời hạn.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])

        order.action_dlm_send()

        self.assertEqual(order.state, "sent")
        self.assertTrue(order.date_sent)

    def test_tinh_trang_nhan_suy_tu_chung_tu(self):
        """`dlm_receipt_state` phải đọc phiếu nhận, không phải một ô tick."""
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self.assertEqual(order.dlm_receipt_state, "nothing")

        self._receive_po(order)

        self.assertEqual(order.dlm_receipt_state, "done")
        self.assertAlmostEqual(order.line_ids.qty_received, 30.0, places=2)

    def test_ncc_giao_thieu_thi_van_treo(self):
        """🔴 Nhu cầu chỉ đóng khi hàng CÓ MẶT, không phải khi ai đó ký giấy.

        Đỏ = đơn mua tự đóng ở lần giao đầu ⇒ 40 cây còn thiếu biến mất khỏi mọi
        màn hình.
        """
        order = self._mk_po([(self.thep, 100.0, 200000.0)])
        order.action_dlm_confirm()
        receipt = order.dlm_picking_ids[:1]
        receipt.move_ids.quantity = 60.0
        receipt.move_ids.picked = True
        # NCC giao thiếu ⇒ Odoo MỞ WIZARD hỏi backorder chứ không tự quyết.
        # Trả lời "tạo phiếu cho phần còn lại" — đúng điều thủ kho làm thật.
        res = receipt.button_validate()
        # ⚠️ Action trả về KHÔNG có `res_id` — wizard chưa tồn tại, Odoo chỉ đưa
        # context chứa mặc định. Phải TẠO wizard từ context rồi mới process;
        # `browse(None).process()` chạy êm ru và không validate gì cả.
        if isinstance(res, dict) and res.get("res_model"):
            self.env[res["res_model"]].with_context(
                **res.get("context", {})).create({}).process()

        self.assertEqual(order.dlm_receipt_state, "partial")
        self.assertAlmostEqual(order.line_ids.qty_received, 60.0, places=2)

    def test_in_giay_gui_ncc_tu_dang_ky_font(self):
        """🔴 Tờ giấy phải tự đăng ký font, không sống nhờ việc ai đó đã in báo
        giá trước trong cùng tiến trình.

        Đỏ = tiến trình vừa khởi động, Mua hàng bấm [In yêu cầu báo giá] là ăn
        ValueError của reportlab ("Can't map determine family/bold/italic for
        dlsans-bold") — lỗi hệ thống trần, không phải câu tiếng Việt nào.
        """
        from reportlab.lib import fonts
        from reportlab.pdfbase import pdfmetrics

        from odoo.addons.dl_sale.models.quotation_document import (
            _PDF_FONT, _PDF_FONT_BOLD)

        # Đăng ký font của reportlab là trạng thái TOÀN TIẾN TRÌNH, mà test khác
        # (báo giá, biên bản hàng loại) có thể đã đăng ký hộ. Gỡ ra để dựng lại
        # đúng tiến trình sạch — không có bước này thì test xanh giả tuỳ thứ tự
        # chạy. Phải gỡ ở CẢ HAI bảng: `_fonts` là thứ hàm đăng ký kiểm để bỏ
        # qua, `_ps2tt_map` mới là bảng mà `<para>` tra cứu.
        for name in (_PDF_FONT, _PDF_FONT_BOLD):
            pdfmetrics._fonts.pop(name, None)
            fonts._ps2tt_map.pop(name.lower(), None)
        self.addCleanup(self.env["dl.quotation"]._register_pdf_font)

        order = self._mk_po([(self.thep, 20.0, 200000.0)])
        pdf = order._dlm_build_pdf(is_order=False)

        self.assertTrue(pdf.startswith(b"%PDF"))
