# -*- coding: utf-8 -*-
"""K19 — Vòng đời đơn mua và mối nối sang phiếu nhận."""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseOrder(DlPurchaseCase):

    def test_chot_don_sinh_phieu_nhan_gan_don_mua(self):
        """TC-INT-TestPurchaseOrder-001: Chốt đơn thì phiếu nhận vào hàng đợi thủ kho, có
        neo về đơn mua.

        Đỏ = Mua hàng chốt xong nhưng thủ kho không thấy việc gì, hoặc hàng về mà không
        truy được về giá đã chốt.
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
        """TC-INT-TestPurchaseOrder-002: MH-05 — dòng giá 0 thì lô nhập về mang giá 0.

        Đỏ = giá vốn thực tế của mọi đơn bán dùng lô đó sai vĩnh viễn, và không có gì
        báo động vì 0 cũng là một con số hợp lệ.
        """
        order = self._mk_po([(self.thep, 30.0, 0.0)])

        with self.assertRaises(UserError) as err:
            order.action_dlm_confirm()

        self.assertIn(self.thep.display_name, err.exception.args[0])

    def test_chot_don_thieu_ngay_ve_bi_chan(self):
        """TC-INT-TestPurchaseOrder-003: MH-06 — không có ngày về thì màn Điều phối không
        tính được "đang về".

        Đỏ = đơn bán bị mua chồng: lần điều phối sau vẫn thấy thiếu vì hàng đang trên
        đường không được đếm.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)], expected=False)

        with self.assertRaises(UserError):
            order.action_dlm_confirm()

    def test_hai_dong_cung_mat_hang_bi_chan(self):
        """TC-INT-TestPurchaseOrder-004: MH-12 — hai giá cho một mặt hàng thì lúc nhận
        không biết đóng giá nào.

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
        """TC-INT-TestPurchaseOrder-005: MH-04 — phế liệu là thứ Đại Linh bán đi.
        """
        scrap = self.env["product.product"].create({
            "name": "Phế liệu thép (mua hàng)", "product_kind": "material"})
        scrap.sudo().dlm_is_scrap = True
        order = self._mk_po([(scrap, 50.0, 5000.0)])

        with self.assertRaises(UserError):
            order.action_dlm_confirm()

    def test_huy_don_da_nhan_hang_bi_chan(self):
        """TC-INT-TestPurchaseOrder-006: MH-10 — hàng đã vào kho mà chứng từ mua biến mất
        là lỗ hổng đối soát.

        Đỏ = kiểm kê thấy 30 cây thép không giải thích được từ đâu ra.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self._receive_po(order)

        with self.assertRaises(UserError) as err:
            order.action_dlm_cancel()

        self.assertIn("Trả hàng nhà cung cấp", err.exception.args[0])

    def test_huy_don_chua_nhan_thi_huy_luon_phieu(self):
        """TC-INT-TestPurchaseOrder-007: MH-11 — phiếu mồ côi nằm trong hàng đợi thủ kho là
        việc chết.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        order.action_dlm_confirm()
        picking = order.dlm_picking_ids

        order.action_dlm_cancel()

        self.assertEqual(order.state, "cancelled")
        self.assertEqual(picking.state, "cancel")

    def test_gui_hoi_gia_ghi_moc_thoi_gian(self):
        """TC-INT-TestPurchaseOrder-008: Mốc gửi phải nằm trong hệ thống, dù mail gửi bằng
        Zalo.

        Đỏ = không ai trả lời được "gửi NCC lâu chưa" thì đơn nằm chờ vô thời hạn.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])

        order.action_dlm_send()

        self.assertEqual(order.state, "sent")
        self.assertTrue(order.date_sent)

    def test_tinh_trang_nhan_suy_tu_chung_tu(self):
        """TC-INT-TestPurchaseOrder-009: `dlm_receipt_state` phải đọc phiếu nhận, không
        phải một ô tick.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self.assertEqual(order.dlm_receipt_state, "nothing")

        self._receive_po(order)

        self.assertEqual(order.dlm_receipt_state, "done")
        self.assertAlmostEqual(order.line_ids.qty_received, 30.0, places=2)

    def test_ncc_giao_thieu_thi_van_treo(self):
        """TC-INT-TestPurchaseOrder-010: Nhu cầu chỉ đóng khi hàng có mặt, không phải khi
        ai đó ký giấy.

        Đỏ = đơn mua tự đóng ở lần giao đầu thì 40 cây còn thiếu biến mất khỏi mọi màn
        hình.
        """
        order = self._mk_po([(self.thep, 100.0, 200000.0)])
        order.action_dlm_confirm()
        receipt = order.dlm_picking_ids[:1]
        receipt.move_ids.quantity = 60.0
        receipt.move_ids.picked = True
        # NCC giao thiếu thì Odoo mở wizard hỏi backorder chứ không tự quyết.
        # Trả lời "tạo phiếu cho phần còn lại" — đúng điều thủ kho làm thật.
        res = receipt.button_validate()
        # Action trả về không có `res_id` — wizard chưa tồn tại, Odoo chỉ đưa
        # context chứa mặc định. Phải TẠO wizard từ context rồi mới process;
        # `browse(None).process()` chạy êm ru và không validate gì cả.
        if isinstance(res, dict) and res.get("res_model"):
            self.env[res["res_model"]].with_context(
                **res.get("context", {})).create({}).process()

        self.assertEqual(order.dlm_receipt_state, "partial")
        self.assertAlmostEqual(order.line_ids.qty_received, 60.0, places=2)

    def test_in_giay_gui_ncc_tu_dang_ky_font(self):
        """TC-INT-TestPurchaseOrder-011: Tờ giấy phải tự đăng ký font, không sống nhờ việc
        ai đó đã in báo giá trước trong cùng tiến trình.

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

    # -------------------------------------------- Gửi PDF cho NCC bằng email
    def test_gui_mail_ncc_dinh_san_pdf_va_dung_nguoi_nhan(self):
        """TC-INT-TestPurchaseOrder-012: Thư phải mở ra đã có file và đã điền NCC.

        Đỏ = Mua hàng vẫn phải tự tải PDF rồi tự gõ địa chỉ — đúng việc thủ công mà nút
        này sinh ra để thay thế, và gõ tay là gửi nhầm NCC.
        """
        self.vendor.email = "thanghao@test.local"
        order = self._mk_po([(self.thep, 20.0, 200000.0)])

        action = order.action_dlm_email()

        ctx = action["context"]
        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(ctx["default_partner_ids"], [(6, 0, self.vendor.ids)])
        attachment = self.env["ir.attachment"].browse(
            ctx["default_attachment_ids"][0][2])
        self.assertEqual(attachment.mimetype, "application/pdf")
        # Nháp thì tờ hỏi giá, không phải đơn đặt hàng.
        self.assertIn("YeuCauBaoGia", attachment.name)
        self.assertIn("Yêu cầu báo giá", ctx["default_subject"])
        # Đính kèm neo vào chính đơn: ba tháng sau còn tra được đã gửi cái gì.
        self.assertEqual(attachment.res_model, "dl.purchase.order")
        self.assertEqual(attachment.res_id, order.id)

    def test_don_da_chot_thi_gui_don_dat_hang_chu_khong_phai_hoi_gia(self):
        """TC-INT-TestPurchaseOrder-013: Một nút, hai tờ giấy — chọn theo trạng thái, không
        bắt người dùng chọn.
        """
        self.vendor.email = "thanghao@test.local"
        order = self._mk_po([(self.thep, 20.0, 200000.0)])
        order.action_dlm_confirm()

        ctx = order.action_dlm_email()["context"]

        attachment = self.env["ir.attachment"].browse(
            ctx["default_attachment_ids"][0][2])
        self.assertIn("DonDatHang", attachment.name)
        self.assertIn("Đơn đặt hàng", ctx["default_subject"])

    def test_ncc_khong_co_email_thi_chan_som_va_chi_duong_khac(self):
        """TC-INT-TestPurchaseOrder-014: Chặn trước khi mở trình soạn thư.

        Đỏ = composer mở ra với ô người nhận rỗng, người dùng bấm Gửi rồi tưởng đã gửi —
        im lặng, và NCC không bao giờ nhận được gì.
        """
        self.vendor.email = False
        order = self._mk_po([(self.thep, 20.0, 200000.0)])

        with self.assertRaises(UserError):
            order.action_dlm_email()

    def test_mo_thu_khong_tu_danh_dau_da_gui(self):
        """TC-INT-TestPurchaseOrder-015: Mốc "đã gửi" phải phản ánh việc đã xảy ra, không
        phải ý định.

        Composer gửi ở một bước SAU; đóng cửa sổ là thư không đi. Tự chuyển trạng thái ở
        đây thì "đã gửi lâu chưa" trả lời sai ngay từ đầu.
        """
        self.vendor.email = "thanghao@test.local"
        order = self._mk_po([(self.thep, 20.0, 200000.0)])

        order.action_dlm_email()

        self.assertEqual(order.state, "draft")
        self.assertFalse(order.date_sent)
