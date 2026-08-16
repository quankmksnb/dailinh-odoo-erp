"""Trạng thái RFQ gộp từ dòng — dòng thương mại KHÔNG phải việc của Kỹ thuật.

Bối cảnh: form "Tạo RFQ" của Sales có 2 bảng (thương mại / gia công). Bảng
thương mại bắt Sales chọn thẳng Sản phẩm (resolved_product_id) ngay lúc tạo —
đó là lựa chọn của Sales, không phải kết quả kỹ thuật. Nếu rollup tính dòng đó
là "đã có kết quả" thì RFQ vừa bấm Lưu đã nhảy sang "Đang xử lý", trong khi
bên Kỹ thuật chưa ai nhận (phải là "Chưa nhận").
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqStatusRollup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Khách Cá nhân + Di động: bộ constrains của dl_partner đòi Cá nhân phải
        # có di động, còn Doanh nghiệp thì thêm MST và địa chỉ — chọn cá nhân cho
        # gọn vì bài test này không đụng gì tới hồ sơ khách.
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách rollup trạng thái (test)",
            "partner_role": "customer",
            "partner_type": "individual",
            "mobile": "0912345678",
        })
        cls.trading_product = cls.env["product.product"].create({
            "name": "Ốc vít M8 (test rollup)",
            "product_kind": "trading",
            "dlm_lifecycle_state": "active",
        })

    def _trading_vals(self):
        return {
            "product_type": "trading",
            "resolved_product_id": self.trading_product.id,
            "quantity": 2.0,
        }

    def _manufactured_vals(self, name="Khung thép rollup (test)"):
        return {
            "product_type": "manufactured",
            "product_name": name,
            "quantity": 1.0,
            "dimension_note": "1200x800",
        }

    def test_mixed_rfq_stays_new_for_technician(self):
        """TC-INT-TestRfqStatusRollup-001: RFQ vừa tạo có cả dòng thương mại lẫn gia công
        thì Kỹ thuật thấy "Chưa nhận".

        Tạo qua đúng 2 field của form Sales (mỗi field là một lượt create dòng riêng) để
        bám sát đường ghi thật.
        """
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "trading_line_ids": [(0, 0, self._trading_vals())],
            "manufactured_line_ids": [(0, 0, self._manufactured_vals())],
        })

        self.assertEqual(request.status, "new")
        self.assertEqual(request.tech_stage, "pending")

    def test_trading_only_rfq_is_ready_to_quote(self):
        """TC-INT-TestRfqStatusRollup-002: RFQ toàn hàng thương mại không có việc gì cho Kỹ
        thuật thì chờ tạo báo giá.
        """
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "trading_line_ids": [(0, 0, self._trading_vals())],
        })

        self.assertEqual(request.status, "confirmed")

    def test_technical_result_still_moves_to_processing(self):
        """TC-INT-TestRfqStatusRollup-003: Không hồi quy: có kết quả kỹ thuật trên dòng gia
        công thì vẫn "Đang xử lý".
        """
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "trading_line_ids": [(0, 0, self._trading_vals())],
            "manufactured_line_ids": [
                (0, 0, self._manufactured_vals()),
                (0, 0, self._manufactured_vals("Giá kệ rollup (test)")),
            ],
        })

        request.manufactured_line_ids[0].write({
            "is_infeasible": True,
            "infeasible_reason": "Vượt hành trình máy chấn",
        })

        self.assertEqual(request.status, "processing")
        self.assertEqual(request.tech_stage, "processing")

    def test_new_manufactured_line_reopens_confirmed_rfq(self):
        """TC-INT-TestRfqStatusRollup-004: RFQ toàn thương mại (đang "Chờ tạo báo giá") mà
        Sales thêm dòng gia công thì phải quay lại hàng đợi Kỹ thuật, không được đứng ở
        "Chờ tạo báo giá".
        """
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "trading_line_ids": [(0, 0, self._trading_vals())],
        })
        self.assertEqual(request.status, "confirmed")

        request.write({
            "manufactured_line_ids": [(0, 0, self._manufactured_vals())],
        })

        self.assertEqual(request.status, "new")
        self.assertEqual(request.tech_stage, "pending")
