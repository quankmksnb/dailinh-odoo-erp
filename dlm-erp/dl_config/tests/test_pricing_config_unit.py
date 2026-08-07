# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.pricing.config (S02 · Cấu hình
Hệ thống). Sheet nguồn: DlPricingConfig trong Report 5.1.

Chỉ test các method thuần Python — không đụng self.env/self.search/self.
create/self.write. Các method ORM (save_tab1/2/3, get_tab1/2/3,
_ensure_default_levels, _read_approvers, _get_singleton, _diff_levels) thuộc
L2, KHÔNG test ở đây — xem dl_config/tests/ cho L2 sau này.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.pricing_config import DlPricingConfig


class _Cfg(SimpleNamespace):
    def ensure_one(self):
        return self


# =============================================================================
# _compute_structure_total() — tổng 5 thành phần cơ cấu giá.
# =============================================================================
class TestComputeStructureTotal(unittest.TestCase):
    def test_sums_five_components(self):
        """TC-UNIT-DlPricingConfig-001"""
        rec = SimpleNamespace(material_pct=55.0, labor_pct=25.0, overhead_pct=5.0,
                               risk_pct=3.0, margin_pct=12.0)
        DlPricingConfig._compute_structure_total([rec])
        self.assertEqual(rec.structure_total, 100.0)

    def test_not_forced_to_100(self):
        """TC-UNIT-DlPricingConfig-002 — chỉ là tham khảo, không chặn cứng =100."""
        rec = SimpleNamespace(material_pct=50.0, labor_pct=20.0, overhead_pct=5.0,
                               risk_pct=3.0, margin_pct=12.0)
        DlPricingConfig._compute_structure_total([rec])
        self.assertEqual(rec.structure_total, 90.0)


# =============================================================================
# _round_label() — map rounding_to (int) -> nhãn hiển thị.
# =============================================================================
class TestRoundLabel(unittest.TestCase):
    def test_known_values(self):
        """TC-UNIT-DlPricingConfig-003"""
        cfg = _Cfg()
        self.assertEqual(DlPricingConfig._round_label(cfg, 0), "Không làm tròn")
        self.assertEqual(DlPricingConfig._round_label(cfg, 1000), "Làm tròn đến 1.000đ")
        self.assertEqual(DlPricingConfig._round_label(cfg, 10000), "Làm tròn đến 10.000đ")

    def test_unknown_value_falls_back_to_str(self):
        """TC-UNIT-DlPricingConfig-004"""
        cfg = _Cfg()
        self.assertEqual(DlPricingConfig._round_label(cfg, 500), "500")

    def test_falsy_value_treated_as_zero(self):
        """TC-UNIT-DlPricingConfig-005"""
        cfg = _Cfg()
        self.assertEqual(DlPricingConfig._round_label(cfg, None), "Không làm tròn")


# =============================================================================
# _read_cost() / _read_waste() / _read_sla() — data shaping cho OWL, chỉ đọc
# field của self, không đụng self.env.
# =============================================================================
class TestReadCost(unittest.TestCase):
    def test_happy_shape(self):
        """TC-UNIT-DlPricingConfig-006"""
        cfg = _Cfg(material_pct=55.0, labor_pct=25.0, overhead_pct=5.0, risk_pct=3.0,
                   margin_pct=12.0, max_discount_pct=15.0, vat_pct=8.0,
                   price_validity_days=30, rounding_to=1000)
        result = DlPricingConfig._read_cost(cfg)
        self.assertEqual(result, {
            "material": 55.0, "labor": 25.0, "overhead": 5.0, "risk": 3.0,
            "margin": 12.0, "maxDiscount": 15.0, "vat": 8.0,
            "priceValidity": 30, "rounding": 1000,
        })


class TestReadWaste(unittest.TestCase):
    def test_maps_waste_lines(self):
        """TC-UNIT-DlPricingConfig-007"""
        w1 = SimpleNamespace(group_name="Thép tấm", waste_pct=5.0)
        w2 = SimpleNamespace(group_name="Ống thép", waste_pct=8.0)
        cfg = _Cfg(waste_ids=[w1, w2])
        self.assertEqual(DlPricingConfig._read_waste(cfg), [
            {"group": "Thép tấm", "pct": 5.0}, {"group": "Ống thép", "pct": 8.0},
        ])

    def test_empty_waste(self):
        """TC-UNIT-DlPricingConfig-008"""
        cfg = _Cfg(waste_ids=[])
        self.assertEqual(DlPricingConfig._read_waste(cfg), [])


class TestReadSla(unittest.TestCase):
    def test_happy_shape(self):
        """TC-UNIT-DlPricingConfig-009"""
        cfg = _Cfg(sla_sales_manager_hours=4, sla_ceo_hours=8, sla_reminder_every_hours=2,
                   sla_require_late_reason=True, sla_overdue_remind=True,
                   sla_overdue_escalate=True, sla_overdue_log=True, sla_overdue_kpi=False)
        result = DlPricingConfig._read_sla(cfg)
        self.assertEqual(result, {
            "salesManager": 4, "ceo": 8, "reminderEvery": 2, "requireLateReason": True,
            "onOverdue": {"remind": True, "escalate": True, "log": True, "kpi": False},
        })


# =============================================================================
# _read_levels() — data shaping bảng cấp duyệt cho OWL.
# =============================================================================
class TestReadLevels(unittest.TestCase):
    @staticmethod
    def _level(**kw):
        base = dict(id=1, name="Cấp 1", value_min=20.0, value_max=100.0,
                    discount_min=5.0, discount_max=15.0, margin_min=8.0,
                    approver_role="sales_manager", approver_user_id=None,
                    backup_user_id=None, mode="sequential", sla_hours=4,
                    note="", is_active=True, is_priority=False, pending_count=0)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_happy_with_user_and_backup(self):
        """TC-UNIT-DlPricingConfig-010"""
        user = SimpleNamespace(id=5)
        backup = SimpleNamespace(id=6)
        lvl = self._level(approver_user_id=user, backup_user_id=backup)
        cfg = _Cfg(level_ids=[lvl])
        out = DlPricingConfig._read_levels(cfg)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["user"], "5")
        self.assertEqual(out[0]["backup"], "6")

    def test_no_user_no_backup_empty_string(self):
        """TC-UNIT-DlPricingConfig-011"""
        lvl = self._level(approver_user_id=None, backup_user_id=None)
        cfg = _Cfg(level_ids=[lvl])
        out = DlPricingConfig._read_levels(cfg)
        self.assertEqual(out[0]["user"], "")
        self.assertEqual(out[0]["backup"], "")

    def test_value_max_zero_becomes_none_infinity(self):
        """TC-UNIT-DlPricingConfig-012"""
        lvl = self._level(value_max=0.0)
        cfg = _Cfg(level_ids=[lvl])
        out = DlPricingConfig._read_levels(cfg)
        self.assertIsNone(out[0]["vMax"])

    def test_margin_min_zero_becomes_none(self):
        """TC-UNIT-DlPricingConfig-013"""
        lvl = self._level(margin_min=0.0)
        cfg = _Cfg(level_ids=[lvl])
        out = DlPricingConfig._read_levels(cfg)
        self.assertIsNone(out[0]["marginMin"])

    def test_positive_value_max_and_margin_kept(self):
        """TC-UNIT-DlPricingConfig-014"""
        lvl = self._level(value_max=100.0, margin_min=8.0)
        cfg = _Cfg(level_ids=[lvl])
        out = DlPricingConfig._read_levels(cfg)
        self.assertEqual(out[0]["vMax"], 100.0)
        self.assertEqual(out[0]["marginMin"], 8.0)


# =============================================================================
# _parse_level() — chuẩn hóa payload OWL -> dict field DB, thuần Python.
# =============================================================================
class TestParseLevel(unittest.TestCase):
    def test_full_payload_happy(self):
        """TC-UNIT-DlPricingConfig-015"""
        cfg = _Cfg()
        payload = {
            "id": 7, "name": " Cấp 1 ", "vMin": "20", "vMax": "100",
            "dMin": "5", "dMax": "15", "marginMin": "8", "role": "sales_manager",
            "user": "12", "backup": "13", "mode": "sequential", "sla": "4",
            "note": " ghi chú ", "active": True, "priority": False,
        }
        out = DlPricingConfig._parse_level(cfg, payload)
        self.assertEqual(out, {
            "_id": 7, "name": "Cấp 1", "value_min": 20.0, "value_max": 100.0,
            "discount_min": 5.0, "discount_max": 15.0, "margin_min": 8.0,
            "approver_role": "sales_manager", "approver_user_id": 12,
            "backup_user_id": 13, "mode": "sequential", "sla_hours": 4,
            "note": "ghi chú", "is_active": True, "is_priority": False,
        })

    def test_empty_payload_uses_defaults(self):
        """TC-UNIT-DlPricingConfig-016"""
        cfg = _Cfg()
        out = DlPricingConfig._parse_level(cfg, {})
        self.assertEqual(out["_id"], 0)
        self.assertEqual(out["name"], "Cấp duyệt")
        self.assertEqual(out["approver_role"], "none")
        self.assertEqual(out["mode"], "sequential")
        self.assertEqual(out["approver_user_id"], False)
        self.assertEqual(out["backup_user_id"], False)
        self.assertTrue(out["is_active"])  # active mặc định True khi vắng key
        self.assertFalse(out["is_priority"])

    def test_none_payload_is_noop_defaults(self):
        """TC-UNIT-DlPricingConfig-017"""
        cfg = _Cfg()
        out = DlPricingConfig._parse_level(cfg, None)
        self.assertEqual(out["_id"], 0)
        self.assertEqual(out["name"], "Cấp duyệt")

    def test_invalid_role_falls_back_to_none(self):
        """TC-UNIT-DlPricingConfig-018"""
        cfg = _Cfg()
        out = DlPricingConfig._parse_level(cfg, {"role": "hacker"})
        self.assertEqual(out["approver_role"], "none")

    def test_invalid_mode_falls_back_to_sequential(self):
        """TC-UNIT-DlPricingConfig-019"""
        cfg = _Cfg()
        out = DlPricingConfig._parse_level(cfg, {"mode": "bogus"})
        self.assertEqual(out["mode"], "sequential")

    def test_negative_or_zero_id_treated_as_new(self):
        """TC-UNIT-DlPricingConfig-020"""
        cfg = _Cfg()
        self.assertEqual(DlPricingConfig._parse_level(cfg, {"id": -1})["_id"], 0)
        self.assertEqual(DlPricingConfig._parse_level(cfg, {"id": "7"})["_id"], 0)  # id không phải int -> 0

    def test_non_numeric_vmin_falls_back_to_zero(self):
        """TC-UNIT-DlPricingConfig-021"""
        cfg = _Cfg()
        out = DlPricingConfig._parse_level(cfg, {"vMin": "abc"})
        self.assertEqual(out["value_min"], 0.0)


# =============================================================================
# _check_overlap() — EX-06, chặn cứng khi 2 cấp active không-priority chồng
# khoảng giá trị. Thuần Python, chỉ đọc list dict đã parse.
# =============================================================================
class TestCheckOverlap(unittest.TestCase):
    @staticmethod
    def _lv(name, vmin, vmax, active=True, priority=False):
        return {"name": name, "value_min": vmin, "value_max": vmax,
                "is_active": active, "is_priority": priority}

    def test_no_overlap_adjacent_ranges_passes(self):
        """TC-UNIT-DlPricingConfig-022"""
        cfg = _Cfg()
        parsed = [self._lv("A", 0, 20), self._lv("B", 20, 100), self._lv("C", 100, 0)]
        DlPricingConfig._check_overlap(cfg, parsed)  # không raise

    def test_overlap_raises_with_both_names(self):
        """TC-UNIT-DlPricingConfig-023"""
        cfg = _Cfg()
        parsed = [self._lv("A", 0, 30), self._lv("B", 20, 100)]  # chồng [20,30)
        with self.assertRaises(ValidationError) as ctx:
            DlPricingConfig._check_overlap(cfg, parsed)
        self.assertIn("A", str(ctx.exception))
        self.assertIn("B", str(ctx.exception))

    def test_inactive_level_excluded_from_check(self):
        """TC-UNIT-DlPricingConfig-024"""
        cfg = _Cfg()
        parsed = [self._lv("A", 0, 30), self._lv("B", 20, 100, active=False)]
        DlPricingConfig._check_overlap(cfg, parsed)  # không raise vì B bị tắt

    def test_priority_level_excluded_from_check(self):
        """TC-UNIT-DlPricingConfig-025"""
        cfg = _Cfg()
        parsed = [self._lv("A", 0, 30), self._lv("B", 20, 100, priority=True)]
        DlPricingConfig._check_overlap(cfg, parsed)  # không raise vì B là ưu tiên

    def test_zero_value_max_means_infinity_can_overlap(self):
        """TC-UNIT-DlPricingConfig-026"""
        cfg = _Cfg()
        parsed = [self._lv("A", 0, 20), self._lv("B", 15, 0)]  # B=[15,inf) chồng A ở [15,20)
        with self.assertRaises(ValidationError):
            DlPricingConfig._check_overlap(cfg, parsed)


if __name__ == "__main__":
    unittest.main()
