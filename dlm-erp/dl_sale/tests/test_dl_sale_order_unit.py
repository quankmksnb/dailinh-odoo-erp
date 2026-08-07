# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.sale.order / dl.sale.order.line.
Sheet nguồn: DlSaleOrder, DlSaleOrderLine.

Chỉ test method thuần Python (compute tiền, constraint ngày, action mở form
liên kết) — không đụng self.env. create/write/_promote_draft_products/
_reset_draft_blockers/_check_can_reset_draft dùng ORM thật (super().create,
self.env.registry, self.env.user...), thuộc L2, không test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import UserError, ValidationError

from ..models.dl_sale_order import DlSaleOrder, DlSaleOrderLine


class FakeLines(list):
    """Mini stand-in cho recordset — chỉ cần .mapped() cho _compute_amount()."""

    def mapped(self, field):
        return [getattr(rec, field) for rec in self]


def _order(line_ids, discount_pct=0.0, vat_pct=0.0):
    return SimpleNamespace(line_ids=FakeLines(line_ids), discount_pct=discount_pct,
                            vat_pct=vat_pct)


# =============================================================================
# _compute_amount() — cùng công thức lớp tiền như dl.quotation._compute_amount.
# =============================================================================
class TestComputeAmount(unittest.TestCase):
    def test_happy_discount_and_vat(self):
        """TC-UNIT-DlSaleOrder-001"""
        line1 = SimpleNamespace(price_subtotal=70000.0)
        line2 = SimpleNamespace(price_subtotal=30000.0)
        rec = _order([line1, line2], discount_pct=10.0, vat_pct=8.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 100000.0)
        self.assertEqual(rec.discount_amount, 10000.0)
        self.assertEqual(rec.amount_before_vat, 90000.0)
        self.assertEqual(rec.vat_amount, 7200.0)
        self.assertEqual(rec.amount_total, 97200.0)

    def test_zero_discount_and_vat(self):
        """TC-UNIT-DlSaleOrder-002"""
        line = SimpleNamespace(price_subtotal=50000.0)
        rec = _order([line], discount_pct=0.0, vat_pct=0.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_total, 50000.0)

    def test_no_lines(self):
        """TC-UNIT-DlSaleOrder-003"""
        rec = _order([], discount_pct=10.0, vat_pct=8.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 0.0)
        self.assertEqual(rec.amount_total, 0.0)


# =============================================================================
# _check_order_after_quotation() — constraint thuần, so ngày.
# =============================================================================
class _NoQuotation:
    """Many2one rỗng đúng ngữ nghĩa Odoo: falsy nhưng .date_order đọc được."""
    date_order = False

    def __bool__(self):
        return False


class TestCheckOrderAfterQuotation(unittest.TestCase):
    def test_order_before_quotation_raises(self):
        """TC-UNIT-DlSaleOrder-004"""
        order = SimpleNamespace(date_order="2026-01-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        with self.assertRaises(ValidationError):
            DlSaleOrder._check_order_after_quotation([order])

    def test_order_same_day_as_quotation_passes(self):
        """TC-UNIT-DlSaleOrder-005"""
        order = SimpleNamespace(date_order="2026-02-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        DlSaleOrder._check_order_after_quotation([order])  # boundary, không raise

    def test_order_after_quotation_passes(self):
        """TC-UNIT-DlSaleOrder-006"""
        order = SimpleNamespace(date_order="2026-03-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        DlSaleOrder._check_order_after_quotation([order])  # không raise

    def test_no_quotation_id_skips_check(self):
        """TC-UNIT-DlSaleOrder-007 — đơn tạo thủ công (không từ báo giá)."""
        order = SimpleNamespace(date_order="2026-01-01", quotation_id=_NoQuotation())
        DlSaleOrder._check_order_after_quotation([order])  # không raise


# =============================================================================
# action_open_quotation() — routing thuần, chỉ đọc self.quotation_id.
# =============================================================================
class _OrderRec(SimpleNamespace):
    def ensure_one(self):
        return self


class TestActionOpenQuotation(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlSaleOrder-008"""
        rec = _OrderRec(quotation_id=SimpleNamespace(id=17))
        action = DlSaleOrder.action_open_quotation(rec)
        self.assertEqual(action["res_id"], 17)
        self.assertEqual(action["res_model"], "dl.quotation")

    def test_no_quotation_raises(self):
        """TC-UNIT-DlSaleOrder-009"""
        rec = _OrderRec(quotation_id=False)
        with self.assertRaises(UserError):
            DlSaleOrder.action_open_quotation(rec)


# =============================================================================
# DlSaleOrderLine._compute_subtotal()
# =============================================================================
class TestSaleOrderLineComputeSubtotal(unittest.TestCase):
    def test_happy(self):
        """TC-UNIT-DlSaleOrderLine-001"""
        line = SimpleNamespace(qty=10.0, price_unit=1500.0)
        DlSaleOrderLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 15000.0)

    def test_zero_qty_boundary(self):
        """TC-UNIT-DlSaleOrderLine-002"""
        line = SimpleNamespace(qty=0.0, price_unit=1500.0)
        DlSaleOrderLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 0.0)


if __name__ == "__main__":
    unittest.main()
