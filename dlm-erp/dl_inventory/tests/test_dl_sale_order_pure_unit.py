# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho `dl.sale.order` (K6, mở rộng bởi
dl_inventory) — chỉ `_dlm_is_fully_delivered`, hàm duy nhất trong file này
không đụng self.env/ORM (nhận sẵn 2 dict `needed`/`delivered`, chỉ gọi
`self.ensure_one()` làm guard và đọc `product.uom_id.rounding`). Sheet
nguồn: DlSaleOrder trong Report 5.1_UnitTests_L1.xlsx (tiếp số thứ tự sau
các dòng đã có sẵn của dl_sale).

Mọi method khác trong dl_inventory/models/dl_sale_order.py (
_dlm_needed_qty/_dlm_delivered_qty/_dlm_planned_qty/_dlm_remaining_qty,
action_dlm_create_delivery...) đều đụng self.env/recordset thật ⇒ L2, xem
sheet TestDeliveryLink trong Report 5.2_IntegrationTests_L2.xlsx.

Chạy standalone bằng `python -m unittest` (cần package `odoo` + addons_path
trỏ tới dlm-erp trên PYTHONPATH, như các test L1 khác trong dự án).
"""
import unittest
from types import SimpleNamespace

from ..models.dl_sale_order import DlSaleOrder


def _order():
    """Stub thuần cho `self`: `_dlm_is_fully_delivered` chỉ gọi
    `self.ensure_one()` làm guard, không đụng self.env/field nào khác của
    đơn — nên chỉ cần no-op thay vì dựng cả recordset thật."""
    return SimpleNamespace(ensure_one=lambda: None)


class _Product:
    """Stub cho product: `_dlm_is_fully_delivered` chỉ đọc
    `product.uom_id.rounding`. Dùng class thường (không phải SimpleNamespace)
    vì `needed`/`delivered` dùng product làm KHOÁ dict — SimpleNamespace tự
    định nghĩa `__eq__` theo `__dict__` nên bị Python coi là unhashable."""

    def __init__(self, rounding=0.01):
        self.uom_id = SimpleNamespace(rounding=rounding)


def _product(rounding=0.01):
    return _Product(rounding=rounding)


class TestDlmIsFullyDelivered(unittest.TestCase):
    """TC-UNIT-DlSaleOrder-015..022 — nối tiếp các dòng 001..014 sẵn có của
    dl_sale trong sheet DlSaleOrder."""

    def test_exact_match_is_fully_delivered(self):
        """TC-UNIT-DlSaleOrder-015 — đã giao đúng bằng số cần."""
        thep = _product()
        needed = {thep: 100.0}
        delivered = {thep: 100.0}
        self.assertTrue(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_delivered_more_than_needed_is_fully_delivered(self):
        """TC-UNIT-DlSaleOrder-016 — giao dư (vd làm tròn ở tầng move) vẫn
        tính là đã giao đủ."""
        thep = _product()
        needed = {thep: 100.0}
        delivered = {thep: 100.5}
        self.assertTrue(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_delivered_less_than_needed_is_not_fully_delivered(self):
        """TC-UNIT-DlSaleOrder-017 — giao thiếu một sản phẩm."""
        thep = _product()
        needed = {thep: 100.0}
        delivered = {thep: 90.0}
        self.assertFalse(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_product_missing_from_delivered_dict_counts_as_zero(self):
        """TC-UNIT-DlSaleOrder-018 — sản phẩm cần giao nhưng chưa xuất hiện
        trong `delivered` (chưa có move nào done) ⇒ coi như đã giao 0."""
        thep = _product()
        needed = {thep: 50.0}
        delivered = {}
        self.assertFalse(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_empty_needed_is_vacuously_fully_delivered(self):
        """TC-UNIT-DlSaleOrder-019 — không có sản phẩm nào cần giao qua kho
        ⇒ vòng lặp rỗng, trả True (đây là trạng thái không thực tế phát sinh
        vì _compute_dlm_delivery_state đã chặn ở nhánh "nothing" trước khi
        gọi tới hàm này, nhưng vẫn cần đúng nếu gọi trực tiếp)."""
        self.assertTrue(
            DlSaleOrder._dlm_is_fully_delivered(_order(), {}, {}))

    def test_multiple_products_one_short_blocks_all(self):
        """TC-UNIT-DlSaleOrder-020 — nhiều sản phẩm, chỉ 1 sản phẩm giao
        thiếu ⇒ toàn đơn vẫn chưa "done" (không tính trung bình)."""
        thep = _product()
        ton = _product()
        needed = {thep: 100.0, ton: 20.0}
        delivered = {thep: 100.0, ton: 15.0}
        self.assertFalse(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_within_rounding_tolerance_counts_as_fully_delivered(self):
        """TC-UNIT-DlSaleOrder-021 — chênh lệch nằm trong sai số làm tròn
        của UoM (rounding=0.01, thiếu 0.001) vẫn được float_compare coi là
        bằng nhau."""
        thep = _product(rounding=0.01)
        needed = {thep: 100.0}
        delivered = {thep: 99.999}
        self.assertTrue(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))

    def test_falls_back_to_default_rounding_when_uom_rounding_falsy(self):
        """TC-UNIT-DlSaleOrder-022 — `rounding` của UoM bằng 0/False ⇒ hàm
        dùng mặc định 0.01 (`product.uom_id.rounding or 0.01`), không chia
        cho 0 / không coi mọi chênh lệch là hợp lệ."""
        thep = _product(rounding=0.0)
        needed = {thep: 100.0}
        delivered = {thep: 99.9}
        self.assertFalse(
            DlSaleOrder._dlm_is_fully_delivered(_order(), needed, delivered))


if __name__ == "__main__":
    unittest.main()
