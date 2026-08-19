"""Trạng thái RFQ gộp từ dòng — mỗi RFQ đi đúng MỘT vòng đời.

Chốt 2026-08-18: loại RFQ nằm ở header (`request_type`), không còn ở từng dòng.
RFQ thương mại có sẵn sản phẩm + giá nên báo giá được ngay khi Lưu; RFQ gia công
phải chờ Kỹ thuật xử lý qua BOM. Trước đây hai loại trộn được trong một RFQ, và
phần thương mại bị giam theo nhịp của phần gia công.
"""

from odoo.exceptions import ValidationError
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
        # Dòng gia công bắt buộc có Nhóm SP — nhóm quyết định form hỏi Sales
        # thông số gì và Kỹ thuật dùng mẫu nào. Nhóm rỗng (chưa gắn BOM mẫu) là
        # đủ cho bài test này: nó chỉ soi rollup trạng thái, không đụng định mức.
        cls.categ = cls.env["product.category"].create({
            "name": "Khung thép (test rollup)",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
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
            "product_category_id": self.categ.id,
            "quantity": 1.0,
            "dimension_note": "1200x800",
        }

    def test_trading_rfq_is_ready_to_quote(self):
        """RFQ thương mại không có việc gì cho Kỹ thuật → chờ tạo báo giá ngay."""
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": "trading",
            "trading_line_ids": [(0, 0, self._trading_vals())],
        })

        self.assertEqual(request.status, "confirmed")

    def test_manufactured_rfq_waits_for_technician(self):
        """RFQ gia công vừa tạo → Kỹ thuật thấy "Chưa nhận"."""
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": "manufactured",
            "manufactured_line_ids": [(0, 0, self._manufactured_vals())],
        })

        self.assertEqual(request.status, "new")
        self.assertEqual(request.tech_stage, "pending")

    def test_technical_result_still_moves_to_processing(self):
        """Không hồi quy: có kết quả kỹ thuật trên dòng gia công thì "Đang xử lý"."""
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": "manufactured",
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

    def test_line_type_must_match_header_on_create(self):
        """RFQ thương mại KHÔNG chứa được dòng gia công — hai vòng đời tách hẳn."""
        with self.assertRaises(ValidationError):
            self.env["dl.quotation.request"].create({
                "customer_id": self.customer.id,
                "request_type": "trading",
                "trading_line_ids": [(0, 0, self._trading_vals())],
                "manufactured_line_ids": [(0, 0, self._manufactured_vals())],
            })

    def test_line_type_must_match_header_on_write(self):
        """Chặn cả đường ghi sau: thêm dòng lệch loại vào RFQ đã lưu."""
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "request_type": "trading",
            "trading_line_ids": [(0, 0, self._trading_vals())],
        })

        with self.assertRaises(ValidationError):
            request.write({
                "manufactured_line_ids": [(0, 0, self._manufactured_vals())],
            })
