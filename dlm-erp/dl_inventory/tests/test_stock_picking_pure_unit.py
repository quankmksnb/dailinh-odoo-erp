# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho các hàm/hỗ trợ thuần trong
stock_picking.py: `_dlm_fmt` (module-level) và `_dlm_banner_problems`
(bound method nhưng không đụng `self`). Sheet nguồn: StockPicking trong
Report 5.1_UnitTests_L1.xlsx.

Chạy standalone bằng `python -m unittest` (không cần Odoo server/DB, nhưng
cần package `odoo` import được trên PYTHONPATH và addons_path đã trỏ tới
dlm-erp, vì file model thật import `odoo.fields/models/exceptions/tools`).

Chỉ test hai hàm không đụng self.env/ORM. Mọi compute/action khác trong
StockPicking (banner dispatch theo state, action_confirm, QC split...) đều
đụng self.env/search/write nên thuộc phạm vi L2, xem sheet
TestQcReceipt/TestValidationRules trong Report 5.2_IntegrationTests_L2.xlsx.
"""
import unittest

from ..models.stock_picking import StockPicking, _dlm_fmt


def _picking():
    """Instance thuần: `_dlm_banner_problems` không đụng self.env nên không
    cần registry/cursor thật."""
    return object.__new__(StockPicking)


class TestDlmFmt(unittest.TestCase):
    """TC-UNIT-StockPicking-001..006: `_dlm_fmt` bỏ số 0 thừa, dùng dấu thập
    phân kiểu Việt (dấu phẩy thay dấu chấm)."""

    def test_integer_value_no_trailing_zero(self):
        """TC-UNIT-StockPicking-001: giá trị float nguyên (100.0) định dạng
        thành chuỗi không có phần thập phân thừa, kết quả "100"."""
        self.assertEqual(_dlm_fmt(100.0), "100")

    def test_decimal_value_uses_comma(self):
        """TC-UNIT-StockPicking-002: giá trị có phần thập phân (92.5) dùng
        dấu phẩy kiểu Việt thay dấu chấm, kết quả "92,5"."""
        self.assertEqual(_dlm_fmt(92.5), "92,5")

    def test_zero(self):
        """TC-UNIT-StockPicking-003: giá trị 0.0 định dạng thành "0", không
        có phần thập phân thừa."""
        self.assertEqual(_dlm_fmt(0.0), "0")

    def test_small_decimal(self):
        """TC-UNIT-StockPicking-004: giá trị thập phân nhỏ hơn 1 (0.1) vẫn
        dùng dấu phẩy kiểu Việt, kết quả "0,1"."""
        self.assertEqual(_dlm_fmt(0.1), "0,1")

    def test_trailing_zeros_stripped(self):
        """TC-UNIT-StockPicking-005: 100.00 (số nguyên dạng float) không còn
        đuôi .00, khớp đúng mục đích 'bỏ số 0 thừa' trong docstring."""
        self.assertEqual(_dlm_fmt(100.00), "100")

    def test_large_value_six_significant_digits(self):
        """TC-UNIT-StockPicking-006: %g mặc định 6 chữ số có nghĩa, giá trị
        lớn hơn sẽ chuyển sang ký hiệu khoa học. Ghi nhận đúng hành vi hiện
        tại, không phải bug, vì số lượng kho thực tế không tới mức này."""
        self.assertEqual(_dlm_fmt(1234567), "1,23457e+06")


class TestDlmBannerProblems(unittest.TestCase):
    """TC-UNIT-StockPicking-007..010: `_dlm_banner_problems` dựng dải đỏ chuẩn
    (mức "danger", HTML <ul><li>, luôn is_dismissible=True theo chữ ký trả
    về hiện tại, xem lời gọi trong _dlm_banner_transfer/_scrap_sale/_qc/
    _receipt/_delivery)."""

    def test_empty_problems_returns_empty_list(self):
        """TC-UNIT-StockPicking-007: truyền danh sách lỗi rỗng thì vẫn trả
        về đúng cấu trúc (level "danger", html có tiêu đề kèm <ul></ul>
        rỗng, is_dismissible True)."""
        level, html, dismissible = _picking()._dlm_banner_problems(
            [], "Chưa xác nhận phiếu được:")
        self.assertEqual(level, "danger")
        self.assertEqual(html, "Chưa xác nhận phiếu được:<ul></ul>")
        self.assertTrue(dismissible)

    def test_single_problem_wrapped_in_li(self):
        """TC-UNIT-StockPicking-008: một lỗi duy nhất được bọc trong đúng
        một thẻ <li>, nối sau tiêu đề đầu vào."""
        level, html, _dismissible = _picking()._dlm_banner_problems(
            ["Nguồn và đích trùng nhau"], "Chưa xác nhận phiếu được:")
        self.assertEqual(
            html,
            "Chưa xác nhận phiếu được:<ul><li>Nguồn và đích trùng nhau</li></ul>")

    def test_multiple_problems_each_own_li(self):
        """TC-UNIT-StockPicking-009: nhiều lỗi thì mỗi lỗi có thẻ <li> riêng,
        giữ đúng thứ tự truyền vào."""
        level, html, _dismissible = _picking()._dlm_banner_problems(
            ["Thép hộp: số lượng 0", "Tôn tấm: số lượng 0"],
            "Chưa xác nhận phiếu được:")
        self.assertEqual(
            html,
            "Chưa xác nhận phiếu được:<ul>"
            "<li>Thép hộp: số lượng 0</li>"
            "<li>Tôn tấm: số lượng 0</li></ul>")

    def test_level_always_danger_regardless_of_caller_message(self):
        """TC-UNIT-StockPicking-010: mức cảnh báo cố định "danger", không
        phụ thuộc nội dung `loi_mo_dau` truyền vào."""
        level, _html, _dismissible = _picking()._dlm_banner_problems(
            ["x"], "Bất kỳ tiêu đề nào")
        self.assertEqual(level, "danger")


if __name__ == "__main__":
    unittest.main()
