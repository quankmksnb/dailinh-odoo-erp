# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.header.mixin (dùng chung cho
dl.bom / dl.bom.template) và dl.bom.line. Sheet nguồn: DlBomHeaderMixin,
DlBomLine.

Chỉ test nhánh không đụng self.env/self.search/super().write thật:
action_confirm (đụng self.env.user) và _compute_next_version/
_set_current_version/action_create_new_version (đụng self.search/self.copy)
là L2, không test ở đây. write()/unlink() chỉ test được nhánh RAISE (trước
khi chạm super()), vì super().write() cần self là instance thật.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import UserError

from ..models.dl_bom_header_mixin import DlBomHeaderMixin
from ..models.dl_bom_line import DlBomLine


def _bom(**kw):
    base = dict(status="draft", is_current=False, _description="BOM")
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec._check_can_reset_draft = lambda: None  # hook mặc định no-op
    return rec


# =============================================================================
# action_lock() / action_archive() — state machine thuần, không đụng self.env.
# =============================================================================
class TestActionLock(unittest.TestCase):
    def test_confirmed_to_locked(self):
        """TC-UNIT-DlBomHeaderMixin-001"""
        rec = _bom(status="confirmed")
        DlBomHeaderMixin.action_lock([rec])
        self.assertEqual(rec.status, "locked")

    def test_draft_raises(self):
        """TC-UNIT-DlBomHeaderMixin-002"""
        rec = _bom(status="draft")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_lock([rec])

    def test_already_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-003"""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_lock([rec])


class TestActionArchive(unittest.TestCase):
    def test_locked_to_archived_clears_current_flag(self):
        """TC-UNIT-DlBomHeaderMixin-004"""
        rec = _bom(status="locked", is_current=True)
        DlBomHeaderMixin.action_archive([rec])
        self.assertEqual(rec.status, "archived")
        self.assertFalse(rec.is_current)

    def test_draft_can_also_be_archived(self):
        """TC-UNIT-DlBomHeaderMixin-005 — không giới hạn trạng thái nguồn."""
        rec = _bom(status="draft")
        DlBomHeaderMixin.action_archive([rec])
        self.assertEqual(rec.status, "archived")


class TestActionResetDraft(unittest.TestCase):
    def test_confirmed_to_draft_clears_current_flag(self):
        """TC-UNIT-DlBomHeaderMixin-006"""
        rec = _bom(status="confirmed", is_current=True)
        DlBomHeaderMixin.action_reset_draft([rec])
        self.assertEqual(rec.status, "draft")
        self.assertFalse(rec.is_current)

    def test_draft_raises(self):
        """TC-UNIT-DlBomHeaderMixin-007"""
        rec = _bom(status="draft")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])

    def test_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-008 — chỉ 'Đã xác nhận' mới được về Nháp."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])

    def test_check_can_reset_draft_hook_called(self):
        """TC-UNIT-DlBomHeaderMixin-009 — hook chặn (vd dl_sale override) phải
        được gọi trước khi đổi trạng thái."""
        rec = _bom(status="confirmed")
        called = []
        rec._check_can_reset_draft = lambda: called.append(True) or (_ for _ in ()).throw(
            UserError("BOM đã dùng cho báo giá đã chốt."))
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])
        self.assertEqual(rec.status, "confirmed")  # không đổi vì hook chặn trước


class TestWriteGuard(unittest.TestCase):
    """Chỉ test nhánh RAISE (trước khi chạm super().write) — self là instance
    thật mới an toàn gọi super()."""

    def test_locked_business_field_raises(self):
        """TC-UNIT-DlBomHeaderMixin-010"""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.write([rec], {"product_qty": 5.0})

    def test_locked_multiple_business_fields_raises(self):
        """TC-UNIT-DlBomHeaderMixin-011"""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.write([rec], {"product_qty": 5.0, "version": 2})


class TestUnlinkGuard(unittest.TestCase):
    def test_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-012"""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.unlink([rec])


# =============================================================================
# dl.bom.line — compute thuần (nhánh vật tư thô; nhánh material_processed
# đụng self.env, không test ở đây — cùng quy ước với quotation_pricing_service).
# =============================================================================
class FakeSellers(list):
    def filtered(self, key):
        if callable(key):
            return FakeSellers(x for x in self if key(x))
        return FakeSellers(x for x in self if getattr(x, key))


class TestComputePriceSnapshot(unittest.TestCase):
    def test_raw_material_uses_applied_seller_price(self):
        """TC-UNIT-DlBomLine-001"""
        seller = SimpleNamespace(is_applied=True, price=50000.0)
        material = SimpleNamespace(product_kind="material",
                                    seller_ids=FakeSellers([seller]))
        rec = SimpleNamespace(material_id=material)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 50000.0)

    def test_raw_material_no_applied_seller_zero(self):
        """TC-UNIT-DlBomLine-002"""
        material = SimpleNamespace(product_kind="material", seller_ids=FakeSellers([]))
        rec = SimpleNamespace(material_id=material)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 0.0)

    def test_no_material_zero(self):
        """TC-UNIT-DlBomLine-003"""
        rec = SimpleNamespace(material_id=None)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 0.0)


class TestComputeRecoveryValue(unittest.TestCase):
    def test_delegates_to_dlm_recovery_value(self):
        """TC-UNIT-DlBomLine-004"""
        rec = SimpleNamespace(_dlm_recovery_value=lambda: 20.0)
        DlBomLine._compute_recovery_value([rec])
        self.assertEqual(rec.recovery_value, 20.0)


class TestComputeSubtotal(unittest.TestCase):
    def test_happy(self):
        """TC-UNIT-DlBomLine-005"""
        rec = SimpleNamespace(effective_qty=10.0, price_snapshot=500.0, recovery_value=100.0)
        DlBomLine._compute_subtotal([rec])
        self.assertEqual(rec.subtotal, 4900.0)

    def test_zero_recovery(self):
        """TC-UNIT-DlBomLine-006"""
        rec = SimpleNamespace(effective_qty=10.0, price_snapshot=500.0, recovery_value=0.0)
        DlBomLine._compute_subtotal([rec])
        self.assertEqual(rec.subtotal, 5000.0)


if __name__ == "__main__":
    unittest.main()
