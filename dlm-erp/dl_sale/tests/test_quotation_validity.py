# -*- coding: utf-8 -*-
"""Hạn hiệu lực báo giá & cổng chặn lên đơn bằng giá cũ.

Giá thép trượt theo ngày, nên quãng từ lúc gửi khách tới lúc khách ký là chỗ
mất tiền lặng lẽ nhất: trước đây `action_create_sale_order` chép thẳng giá cũ
sang đơn mà không kiểm gì. `test_qua_han_thi_khong_len_don_duoc` là phép thử
canh đúng lỗ đó — đỏ nghĩa là hệ thống lại cho lên đơn bằng giá của tuần trước
và chênh lệch rơi vào biên lợi nhuận của công ty.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationValidity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["dl.quotation.pricing.service"]
        cls.customer = cls.env["res.partner"].create({
            "name": "Trường Mầm non Sao Mai (hiệu lực)",
            "partner_role": "customer",
            "mobile": "0900000011",
        })

    def _mk_quotation(self, validity_date=None, state="accepted",
                      issued_days_ago=None):
        """Báo giá dựng sẵn. `issued_days_ago` lùi NGÀY BÁO GIÁ về quá khứ.

        Bắt buộc phải lùi khi hạn nằm ở quá khứ: `_check_validity_date` chặn
        hạn < ngày báo giá. Ràng buộc đó đúng, và nó cũng đúng với đời thực —
        báo giá quá hạn là báo giá phát hành từ trước, không phải báo giá lập
        hôm nay với hạn hôm qua."""
        vals = {
            "partner_id": self.customer.id,
            "state": state,
            "validity_date": validity_date,
        }
        if issued_days_ago:
            phat_hanh = fields.Date.today() - timedelta(days=issued_days_ago)
            vals.update(date_order=phat_hanh, pricing_date=phat_hanh)
        return self.env["dl.quotation"].create(vals)

    # ------------------------------------------------------------------
    def test_han_mac_dinh_7_ngay(self):
        """TC-INT-TestQuotationValidity-001: Báo giá mới có hạn 7 ngày, không
        cam kết giá thép dài hơn thế."""
        hom_nay = fields.Date.today()
        self.assertEqual(
            self.service._validity_date_for(hom_nay),
            hom_nay + timedelta(days=7))

    def test_doi_han_bang_tham_so_he_thong(self):
        """TC-INT-TestQuotationValidity-002: Đổi hạn bằng cấu hình, không
        phải bằng sửa code."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dl_sale.quotation_validity_days", "10")
        hom_nay = fields.Date.today()
        self.assertEqual(
            self.service._validity_date_for(hom_nay),
            hom_nay + timedelta(days=10))

    def test_tham_so_rac_thi_ve_mac_dinh(self):
        """TC-INT-TestQuotationValidity-003: Tham số hỏng không được làm
        chết luồng tạo báo giá."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dl_sale.quotation_validity_days", "bảy")
        self.assertEqual(self.service._validity_days(), 7)

    # ------------------------------------------------------------------
    def test_qua_han_thi_khong_len_don_duoc(self):
        """TC-INT-TestQuotationValidity-004: Khách ký sau khi hết hạn thì bị
        chặn, bắt tính lại giá trước."""
        quo = self._mk_quotation(
            validity_date=fields.Date.today() - timedelta(days=1),
            issued_days_ago=8)
        with self.assertRaises(UserError) as ctx:
            quo.action_create_sale_order()
        self.assertIn("hết hiệu lực", ctx.exception.args[0])

    def test_con_han_thi_qua_cong(self):
        """TC-INT-TestQuotationValidity-005: Còn hạn thì cổng không được
        cản đường."""
        quo = self._mk_quotation(
            validity_date=fields.Date.today() + timedelta(days=3))
        # Chỉ đo cái cổng, không đo cả luồng tạo đơn.
        self.assertTrue(quo._dlm_check_pricing_fresh())

    def test_khong_co_han_thi_khong_chan(self):
        """TC-INT-TestQuotationValidity-006: Báo giá cũ chưa có hạn (trước
        bản này) không bị khoá cứng."""
        quo = self._mk_quotation(validity_date=False)
        self.assertTrue(quo._dlm_check_pricing_fresh())

    # ------------------------------------------------------------------
    def test_sap_het_han_theo_do_dai_han_cua_chinh_no(self):
        """TC-INT-TestQuotationValidity-007: Ngưỡng "sắp hết hạn" co theo
        hạn, báo giá 7 ngày không được kêu ngay ngày đầu."""
        hom_nay = fields.Date.today()
        ngan = self._mk_quotation(
            validity_date=hom_nay + timedelta(days=7), state="sent")
        # Hạn 7 ngày ⇒ ngưỡng 2 ngày ⇒ hôm nay còn 7 ngày: chưa "sắp hết".
        self.assertEqual(ngan.validity_state, "ok")

        dai = self._mk_quotation(
            validity_date=hom_nay + timedelta(days=30), state="sent")
        self.assertEqual(dai.validity_state, "ok")

        # Phát hành 6 ngày trước, hạn 7 ngày ⇒ còn 1 ngày: phải kêu.
        gan = self._mk_quotation(
            validity_date=hom_nay + timedelta(days=1), state="sent",
            issued_days_ago=6)
        self.assertEqual(gan.validity_state, "soon")

    def test_dai_canh_bao_khi_khach_ky_muon(self):
        """TC-INT-TestQuotationValidity-008: Đã đồng ý mà quá hạn thì dải đỏ
        nói rõ phải bấm gì, không để user đâm vào lỗi."""
        quo = self._mk_quotation(
            validity_date=fields.Date.today() - timedelta(days=2),
            issued_days_ago=9)
        self.assertEqual(quo.status_banner_level, "danger")
        self.assertIn("Cập nhật giá theo thị trường",
                      quo.status_banner_message)


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationPriceCommitment(TransactionCase):
    """Trong hạn hiệu lực, giá đã chào là CAM KẾT — doanh nghiệp chịu trượt giá.

    Quyết định 2026-08-20: 7 ngày đầu giá không đổi dù giá vật tư có nhảy (phần
    chênh đã tính vào markup). Hết hạn mà giá đổi thì phải chào LẠI khách chứ
    không được sửa số dưới chân khách rồi vẫn ghi "khách đã đồng ý".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Trường Tiểu học Hoa Sen (cam kết giá)",
            "partner_role": "customer",
            "mobile": "0900000012",
        })

    def _quo(self, state, ngay_truoc, han_truoc):
        hom_nay = fields.Date.today()
        return self.env["dl.quotation"].create({
            "partner_id": self.customer.id,
            "state": state,
            "date_order": hom_nay - timedelta(days=ngay_truoc),
            "pricing_date": hom_nay - timedelta(days=ngay_truoc),
            "validity_date": hom_nay - timedelta(days=han_truoc),
        })

    def test_con_han_thi_khong_chan_du_gia_dau_vao_da_doi(self):
        """TC-INT-TestQuotationPriceCommitment-001: Còn hạn thì lên đơn
        được, không hỏi giá vật tư hôm nay là bao nhiêu."""
        hom_nay = fields.Date.today()
        quo = self.env["dl.quotation"].create({
            "partner_id": self.customer.id,
            "state": "accepted",
            "date_order": hom_nay - timedelta(days=5),
            "pricing_date": hom_nay - timedelta(days=5),
            "validity_date": hom_nay + timedelta(days=2),
        })
        # Cổng chỉ soi HẠN, không soi giá — đó chính là "chịu trượt giá trong hạn".
        self.assertTrue(quo._dlm_check_pricing_fresh())

    def test_trang_thai_da_gui_khach_duoc_liet_ke_du(self):
        """TC-INT-TestQuotationPriceCommitment-002: Ba trạng thái khách đã
        thấy số phải nằm trong danh sách bắt chào lại.

        Thiếu một cái là lọt đúng ca đang muốn chặn, mà không lỗi nào nổ."""
        service = self.env["dl.quotation.pricing.service"]
        self.assertEqual(set(service._DA_GUI_KHACH_STATES),
                         {"approved", "sent", "accepted"})

    def test_khach_dong_y_muon_van_phai_co_loi_ra(self):
        """TC-INT-TestQuotationPriceCommitment-003: Ca 'accepted + quá hạn'
        phải bật cờ giá quá hạn.

        Đây là bẫy đã dính thật: `validity_state` chỉ tính trên _EXPIRABLE_STATES
        (không có 'accepted'), nên nếu gác nút Cập nhật giá bằng nó thì đúng ca
        cần nút nhất lại không có nút — trong khi cổng lên đơn vẫn chặn ⇒ người
        dùng kẹt cứng, không lối ra."""
        quo = self._quo("accepted", 10, 3)
        self.assertEqual(quo.validity_state, "ok",
                         "validity_state cố ý KHÔNG đánh dấu accepted là quá hạn")
        self.assertTrue(quo.dlm_price_stale,
                        "nhưng cờ giá-quá-hạn thì PHẢI bật, không thì mất nút")

    def test_con_han_thi_khong_bat_co(self):
        """TC-INT-TestQuotationPriceCommitment-004: Còn hạn thì không bật
        cờ giá quá hạn."""
        quo = self._quo("accepted", 3, -4)   # hạn còn 4 ngày nữa
        self.assertFalse(quo.dlm_price_stale)

    def test_da_len_don_thi_khong_bat_co(self):
        """TC-INT-TestQuotationPriceCommitment-005: Đơn đã lên rồi thì giá
        cũ là chuyện đã rồi, đừng mời tính lại."""
        quo = self._quo("ordered", 20, 13)
        self.assertFalse(quo.dlm_price_stale)
