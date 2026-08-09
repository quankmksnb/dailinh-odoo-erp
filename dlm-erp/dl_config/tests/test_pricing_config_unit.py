# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.pricing.config.

**Viết lại toàn bộ 2026-08-09** — bản cũ (280 dòng, 26 test case, sheet
DlPricingConfig trong Report 5.1) test màn OWL "Cấu hình Hệ thống" (S02) cũ:
_check_overlap/_compute_structure_total/_parse_level/_read_cost/_read_levels/
_read_sla/_read_waste. TOÀN BỘ 7 method đó đã bị GỠ khỏi
dl_config/models/pricing_config.py — không phải đổi tên/refactor, mà màn S02
đã bị KHAI TỬ hẳn theo đúng comment đầu file pricing_config.py: "Các cấu hình
khác (markup, chiết khấu, công đoạn, hao hụt, ma trận phê duyệt…) đã chuyển
sang các model quy tắc V3 riêng" — tức DlPricingWasteRule, DlPricingCost
AdjustmentRule, DlPricingOperationRule, DlPricingComplexityLevel, DlPricing
ProfitRule, DlPricingDiscountRule, DlPricingApprovalMatrix (đã có sheet/test
L1 riêng, đang PASS — xem Report 5 §4.2, FT-11/12/15). Class dl.pricing.config
hiện SIÊU NHỎ, chỉ còn đúng 2 tham số (vat_pct, rounding_to).

Method còn thuần Python (không đụng self.env/self.search/self.sudo/self.write):
_round_label() và _check_quote_settings(). Các method còn lại (_can_edit,
_get_singleton, get_quote_settings, save_quote_settings) đụng self.env/ORM —
L2, không test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.pricing_config import DlPricingConfig


def _cfg(**kw):
    base = dict(vat_pct=10.0, rounding_to=1000)
    base.update(kw)
    rec = SimpleNamespace(**base)
    return rec


class TestRoundLabel(unittest.TestCase):
    def test_zero_means_no_rounding(self):
        """TC-UNIT-DlPricingConfig-001"""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 0), "Không làm tròn")

    def test_1000_known_label(self):
        """TC-UNIT-DlPricingConfig-002"""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 1000), "Làm tròn đến 1.000đ")

    def test_10000_known_label(self):
        """TC-UNIT-DlPricingConfig-003"""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 10000), "Làm tròn đến 10.000đ")

    def test_unknown_value_falls_back_to_str(self):
        """TC-UNIT-DlPricingConfig-004 — giá trị không nằm trong 3 mốc đã đặt
        tên (0/1000/10000) thì hiển thị nguyên số, không lỗi."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 500), "500")

    def test_none_treated_as_zero(self):
        """TC-UNIT-DlPricingConfig-005 — v=None -> int(v or 0)=0."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, None), "Không làm tròn")


class TestCheckQuoteSettings(unittest.TestCase):
    def _check(self, rec):
        DlPricingConfig._check_quote_settings([rec])

    def test_happy_within_range(self):
        """TC-UNIT-DlPricingConfig-006"""
        rec = _cfg(vat_pct=10.0, rounding_to=1000)
        self._check(rec)  # không raise

    def test_vat_boundary_0_allowed(self):
        """TC-UNIT-DlPricingConfig-007 — biên dưới VAT=0 hợp lệ."""
        rec = _cfg(vat_pct=0.0, rounding_to=0)
        self._check(rec)

    def test_vat_boundary_100_allowed(self):
        """TC-UNIT-DlPricingConfig-008 — biên trên VAT=100 hợp lệ."""
        rec = _cfg(vat_pct=100.0, rounding_to=0)
        self._check(rec)

    def test_vat_negative_raises(self):
        """TC-UNIT-DlPricingConfig-009"""
        rec = _cfg(vat_pct=-1.0)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_vat_above_100_raises(self):
        """TC-UNIT-DlPricingConfig-010"""
        rec = _cfg(vat_pct=100.1)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_rounding_negative_raises(self):
        """TC-UNIT-DlPricingConfig-011"""
        rec = _cfg(rounding_to=-1)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_rounding_zero_allowed(self):
        """TC-UNIT-DlPricingConfig-012 — 0 = không làm tròn, hợp lệ."""
        rec = _cfg(rounding_to=0)
        self._check(rec)


if __name__ == "__main__":
    unittest.main()
