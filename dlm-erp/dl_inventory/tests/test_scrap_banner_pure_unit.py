# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB/HTTP) cho `dlm_scrap_banner_html()`,
K7, controllers/scrap_banner.py. Sheet nguồn: ScrapBannerController trong
Report 5.1_UnitTests_L1.xlsx.

Hàm này không đụng `self`/`request`/ORM (tách khỏi endpoint chính vì lý do
đó, xem docstring trong code), nên test được thẳng như một hàm Python
thuần. Endpoint HTTP `/dl_inventory/scrap_banner` (route JSON, auth="user")
bọc quanh hàm này không test được ở L1 vì cần request/session, việc đó
thuộc phạm vi L3 (xem Report 5.3_SystemTests_L3.xlsx, HTTPFlows_DLM_JSONRPC).

Bất biến quan trọng nhất cần test (theo docstring code, §7.2/§11.8 thiết
kế): dải chú thích luôn xuất hiện và không đóng được. Odoo chỉ ẩn banner
khi HTML trả về có phần tử mang `data-o-hide-banner`, nên bài test chính là
xác nhận thuộc tính đó không có mặt.

Chạy standalone bằng `python -m unittest` (cần package `odoo` và addons_path
trỏ tới dlm-erp trên PYTHONPATH, vì file controller import `odoo._`/`http`).
"""
import unittest

from ..controllers.scrap_banner import dlm_scrap_banner_html


class TestDlmScrapBannerHtml(unittest.TestCase):
    """TC-UNIT-ScrapBannerController-001..004"""

    def test_returns_non_empty_string(self):
        """TC-UNIT-ScrapBannerController-001: gọi hàm không tham số, kết quả
        phải là chuỗi str và không rỗng sau khi strip."""
        html = dlm_scrap_banner_html()
        self.assertIsInstance(html, str)
        self.assertTrue(html.strip())

    def test_cannot_be_dismissed(self):
        """TC-UNIT-ScrapBannerController-002: bất biến quan trọng nhất, HTML
        không được chứa `data-o-hide-banner`, nếu không banner native của
        Odoo sẽ cho phép người dùng đóng dải chú thích này đi."""
        html = dlm_scrap_banner_html()
        self.assertNotIn("data-o-hide-banner", html)

    def test_contains_double_counting_warning_phrase(self):
        """TC-UNIT-ScrapBannerController-003: câu cảnh báo cốt lõi, tiền
        bán phế liệu không phải lợi nhuận tăng thêm vì đã trừ vào giá vốn từ
        lúc báo giá, để tránh tính hai lần."""
        html = dlm_scrap_banner_html()
        self.assertIn(
            "Tiền bán phế liệu không phải lợi nhuận tăng thêm.", html)

    def test_rendered_as_info_alert_div(self):
        """TC-UNIT-ScrapBannerController-004: bọc trong div.alert-info theo
        đúng khung banner native (`onboarding_banner.js`) mà Odoo gắn lên
        đầu view."""
        html = dlm_scrap_banner_html()
        self.assertIn('class="alert alert-info', html)


if __name__ == "__main__":
    unittest.main()
