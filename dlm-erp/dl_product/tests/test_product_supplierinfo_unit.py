# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho product.supplierinfo extension
(dl_product) — PROD-03 bảng giá NCC. Sheet nguồn: ProductSupplierinfo.

Chỉ test method thuần Python — không đụng self.env/self.search/self.write.
action_approve/action_reset_draft/action_set_applied/_dlm_apply/_dlm_unapply
(dùng self.write/self.search/self.env.uid) là L2, không test ở đây.
"""
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError

from ..models.product_supplierinfo import ProductSupplierinfo


def _seller(**kw):
    base = dict(date_start=False, date_end=False, approval_state="draft",
                is_applied=False, price=0.0, currency_id=None, company_id=None,
                product_uom=None, product_tmpl_id=SimpleNamespace(display_name="Thép tấm"))
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec.ensure_one = lambda: rec
    rec._is_valid_on = lambda d: ProductSupplierinfo._is_valid_on(rec, d)
    return rec


_TODAY = date(2026, 8, 5)


# =============================================================================
# _compute_validity_state()
# =============================================================================
class TestComputeValidityState(unittest.TestCase):
    def test_upcoming(self):
        """TC-UNIT-ProductSupplierinfo-001"""
        rec = _seller(date_start=_TODAY + timedelta(days=5), date_end=False)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._compute_validity_state([rec])
        self.assertEqual(rec.validity_state, "upcoming")

    def test_expired(self):
        """TC-UNIT-ProductSupplierinfo-002"""
        rec = _seller(date_start=_TODAY - timedelta(days=60), date_end=_TODAY - timedelta(days=1))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._compute_validity_state([rec])
        self.assertEqual(rec.validity_state, "expired")

    def test_expiring_within_30_days(self):
        """TC-UNIT-ProductSupplierinfo-003"""
        rec = _seller(date_start=_TODAY - timedelta(days=60), date_end=_TODAY + timedelta(days=20))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._compute_validity_state([rec])
        self.assertEqual(rec.validity_state, "expiring")

    def test_active_no_end_date(self):
        """TC-UNIT-ProductSupplierinfo-004"""
        rec = _seller(date_start=_TODAY - timedelta(days=10), date_end=False)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._compute_validity_state([rec])
        self.assertEqual(rec.validity_state, "active")

    def test_active_end_date_far_future(self):
        """TC-UNIT-ProductSupplierinfo-005"""
        rec = _seller(date_start=_TODAY - timedelta(days=10), date_end=_TODAY + timedelta(days=90))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._compute_validity_state([rec])
        self.assertEqual(rec.validity_state, "active")


# =============================================================================
# _compute_display_state()
# =============================================================================
class TestComputeDisplayState(unittest.TestCase):
    def test_applied(self):
        """TC-UNIT-ProductSupplierinfo-006"""
        rec = SimpleNamespace(is_applied=True, approval_state="approved")
        ProductSupplierinfo._compute_display_state([rec])
        self.assertEqual(rec.display_state, "applied")

    def test_approved_not_applied(self):
        """TC-UNIT-ProductSupplierinfo-007"""
        rec = SimpleNamespace(is_applied=False, approval_state="approved")
        ProductSupplierinfo._compute_display_state([rec])
        self.assertEqual(rec.display_state, "approved")

    def test_draft(self):
        """TC-UNIT-ProductSupplierinfo-008"""
        rec = SimpleNamespace(is_applied=False, approval_state="draft")
        ProductSupplierinfo._compute_display_state([rec])
        self.assertEqual(rec.display_state, "draft")


# =============================================================================
# _is_valid_on()
# =============================================================================
class TestIsValidOn(unittest.TestCase):
    def test_within_range_true(self):
        """TC-UNIT-ProductSupplierinfo-009"""
        rec = _seller(date_start=date(2026, 1, 1), date_end=date(2026, 12, 31))
        self.assertTrue(ProductSupplierinfo._is_valid_on(rec, date(2026, 6, 1)))

    def test_no_end_date_open_ended_true(self):
        """TC-UNIT-ProductSupplierinfo-010"""
        rec = _seller(date_start=date(2026, 1, 1), date_end=False)
        self.assertTrue(ProductSupplierinfo._is_valid_on(rec, date(2030, 1, 1)))

    def test_before_start_false(self):
        """TC-UNIT-ProductSupplierinfo-011"""
        rec = _seller(date_start=date(2026, 6, 1), date_end=False)
        self.assertFalse(ProductSupplierinfo._is_valid_on(rec, date(2026, 1, 1)))

    def test_after_end_false(self):
        """TC-UNIT-ProductSupplierinfo-012"""
        rec = _seller(date_start=date(2026, 1, 1), date_end=date(2026, 6, 1))
        self.assertFalse(ProductSupplierinfo._is_valid_on(rec, date(2026, 7, 1)))

    def test_no_start_date_false(self):
        """TC-UNIT-ProductSupplierinfo-013"""
        rec = _seller(date_start=False, date_end=False)
        self.assertFalse(ProductSupplierinfo._is_valid_on(rec, date(2026, 6, 1)))


# =============================================================================
# _check_is_applied() — chỉ 2 nhánh không đụng self.search (guard đơn giản).
# =============================================================================
class TestCheckIsApplied(unittest.TestCase):
    def test_applied_but_not_approved_raises(self):
        """TC-UNIT-ProductSupplierinfo-014"""
        rec = _seller(is_applied=True, approval_state="draft")
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            with self.assertRaises(ValidationError):
                ProductSupplierinfo._check_is_applied([rec])

    def test_applied_but_not_valid_raises(self):
        """TC-UNIT-ProductSupplierinfo-015"""
        rec = _seller(is_applied=True, approval_state="approved",
                      date_start=_TODAY + timedelta(days=10))  # chưa hiệu lực
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            with self.assertRaises(ValidationError):
                ProductSupplierinfo._check_is_applied([rec])

    def test_not_applied_skips_all_checks(self):
        """TC-UNIT-ProductSupplierinfo-016"""
        rec = _seller(is_applied=False, approval_state="draft")
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            ProductSupplierinfo._check_is_applied([rec])  # không raise


# =============================================================================
# _check_price_positive() / _check_date_range()
# =============================================================================
class TestCheckPricePositive(unittest.TestCase):
    def test_zero_raises(self):
        """TC-UNIT-ProductSupplierinfo-017"""
        rec = _seller(price=0.0)
        with self.assertRaises(ValidationError):
            ProductSupplierinfo._check_price_positive([rec])

    def test_negative_raises(self):
        """TC-UNIT-ProductSupplierinfo-018"""
        rec = _seller(price=-100.0)
        with self.assertRaises(ValidationError):
            ProductSupplierinfo._check_price_positive([rec])

    def test_positive_passes(self):
        """TC-UNIT-ProductSupplierinfo-019"""
        rec = _seller(price=50000.0)
        ProductSupplierinfo._check_price_positive([rec])  # không raise


class TestCheckDateRange(unittest.TestCase):
    def test_end_before_start_raises(self):
        """TC-UNIT-ProductSupplierinfo-020"""
        rec = _seller(date_start=date(2026, 6, 1), date_end=date(2026, 1, 1))
        with self.assertRaises(ValidationError):
            ProductSupplierinfo._check_date_range([rec])

    def test_end_equal_start_passes(self):
        """TC-UNIT-ProductSupplierinfo-021"""
        rec = _seller(date_start=date(2026, 1, 1), date_end=date(2026, 1, 1))
        ProductSupplierinfo._check_date_range([rec])  # boundary, không raise

    def test_no_end_date_passes(self):
        """TC-UNIT-ProductSupplierinfo-022"""
        rec = _seller(date_start=date(2026, 1, 1), date_end=False)
        ProductSupplierinfo._check_date_range([rec])  # không raise


# =============================================================================
# _dlm_reference_unit_cost() — quy đổi tiền tệ/UoM về chuẩn công ty.
# =============================================================================
class _Uom(SimpleNamespace):
    def _compute_price(self, price, dst_uom):
        return price * self.rate_to_dst


class TestDlmReferenceUnitCost(unittest.TestCase):
    def test_same_currency_same_uom_passthrough(self):
        """TC-UNIT-ProductSupplierinfo-023"""
        vnd = SimpleNamespace(name="VND")
        company = SimpleNamespace(currency_id=vnd)
        rec = _seller(price=50000.0, currency_id=vnd, company_id=company, product_uom=None)
        product = SimpleNamespace(uom_id=None)
        cost = ProductSupplierinfo._dlm_reference_unit_cost(rec, product)
        self.assertEqual(cost, 50000.0)

    def test_currency_mismatch_raises(self):
        """TC-UNIT-ProductSupplierinfo-024"""
        vnd = SimpleNamespace(name="VND")
        usd = SimpleNamespace(name="USD")
        company = SimpleNamespace(currency_id=vnd)
        rec = _seller(price=100.0, currency_id=usd, company_id=company, product_uom=None)
        product = SimpleNamespace(uom_id=None)
        with self.assertRaises(UserError):
            ProductSupplierinfo._dlm_reference_unit_cost(rec, product)

    def test_incompatible_uom_category_raises(self):
        """TC-UNIT-ProductSupplierinfo-025"""
        vnd = SimpleNamespace(name="VND")
        company = SimpleNamespace(currency_id=vnd)
        src_uom = _Uom(name="kg", category_id="mass")
        dst_uom = _Uom(name="m", category_id="length")
        rec = _seller(price=50000.0, currency_id=vnd, company_id=company, product_uom=src_uom)
        product = SimpleNamespace(uom_id=dst_uom)
        with self.assertRaises(UserError):
            ProductSupplierinfo._dlm_reference_unit_cost(rec, product)

    def test_compatible_uom_converts_price(self):
        """TC-UNIT-ProductSupplierinfo-026"""
        vnd = SimpleNamespace(name="VND")
        company = SimpleNamespace(currency_id=vnd)
        src_uom = _Uom(name="Tấn", category_id="mass", rate_to_dst=1000.0)
        dst_uom = _Uom(name="kg", category_id="mass")
        rec = _seller(price=5_000_000.0, currency_id=vnd, company_id=company, product_uom=src_uom)
        product = SimpleNamespace(uom_id=dst_uom)
        cost = ProductSupplierinfo._dlm_reference_unit_cost(rec, product)
        self.assertEqual(cost, 5_000_000_000.0)


if __name__ == "__main__":
    unittest.main()
