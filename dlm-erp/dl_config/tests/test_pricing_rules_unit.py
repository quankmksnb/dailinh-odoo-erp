# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho các model quy tắc cấu hình báo giá
đơn giản trong dl_config: dl.pricing.rule.mixin (phần thuần), dl.pricing.
commercial.mixin, dl.pricing.profit.rule, dl.pricing.discount.rule,
dl.pricing.cost.adjustment.rule, dl.pricing.operation.rule, dl.pricing.
complexity.level, dl.pricing.waste.rule.

Chỉ test constraint/compute/staticmethod thuần Python — các method dùng
self.search/self.write/self.copy (_assert_fits_group_ladder, action_apply
của mixin gốc, _activate_rule, action_create_revision...) là L2, không test
ở đây.
"""
import unittest
from datetime import date
from types import SimpleNamespace

from odoo.exceptions import UserError, ValidationError

from ..models.pricing_rule import DlPricingRuleMixin
from ..models.pricing_commercial import (
    DlPricingCommercialMixin, DlPricingProfitRule, DlPricingDiscountRule,
)
from ..models.pricing_cost import DlPricingCostAdjustmentRule
from ..models.pricing_operation import DlPricingOperationRule
from ..models.pricing_waste import DlPricingComplexityLevel, DlPricingWasteRule


# =============================================================================
# dl.pricing.rule.mixin — phần thuần Python
# =============================================================================
class TestDatesOverlap(unittest.TestCase):
    """_dates_overlap() — staticmethod thuần, không self."""

    def test_overlapping_ranges(self):
        """TC-UNIT-DlPricingRuleMixin-001"""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 6, 30), date(2026, 6, 1), date(2026, 12, 31)))

    def test_non_overlapping_ranges(self):
        """TC-UNIT-DlPricingRuleMixin-002"""
        self.assertFalse(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 3, 31), date(2026, 4, 1), date(2026, 6, 30)))

    def test_open_ended_a_to_none_treated_as_far_future(self):
        """TC-UNIT-DlPricingRuleMixin-003"""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), None, date(2030, 1, 1), date(2030, 6, 30)))

    def test_touching_boundary_counts_as_overlap(self):
        """TC-UNIT-DlPricingRuleMixin-004"""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 6, 30), date(2026, 6, 30), date(2026, 12, 31)))


class TestCheckValidRange(unittest.TestCase):
    """_check_valid_range() — constraint thuần."""

    def test_from_after_to_raises(self):
        """TC-UNIT-DlPricingRuleMixin-005"""
        rec = SimpleNamespace(valid_from="2026-06-01", valid_to="2026-01-01")
        with self.assertRaises(ValidationError):
            DlPricingRuleMixin._check_valid_range([rec])

    def test_no_valid_to_passes(self):
        """TC-UNIT-DlPricingRuleMixin-006"""
        rec = SimpleNamespace(valid_from="2026-01-01", valid_to=False)
        DlPricingRuleMixin._check_valid_range([rec])  # không raise

    def test_from_before_to_passes(self):
        """TC-UNIT-DlPricingRuleMixin-007"""
        rec = SimpleNamespace(valid_from="2026-01-01", valid_to="2026-12-31")
        DlPricingRuleMixin._check_valid_range([rec])  # không raise


# =============================================================================
# dl.pricing.commercial.mixin — action_apply() luôn raise (chưa gửi duyệt là
# không cho Áp dụng trực tiếp).
# =============================================================================
class TestCommercialMixinActionApply(unittest.TestCase):
    def test_always_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-001"""
        rec = SimpleNamespace()
        with self.assertRaises(UserError):
            DlPricingCommercialMixin.action_apply(rec)


# =============================================================================
# dl.pricing.profit.rule
# =============================================================================
class TestProfitRuleComputeName(unittest.TestCase):
    def test_happy_format(self):
        """TC-UNIT-DlPricingProfitRule-001"""
        rec = SimpleNamespace(target_markup=20.0, min_markup=5.0, revision=1)
        DlPricingProfitRule._compute_name([rec])
        self.assertEqual(rec.name, "Markup mục tiêu 20.0% / sàn 5.0% (b1)")


class TestProfitRuleCheckMarkup(unittest.TestCase):
    def test_negative_target_raises(self):
        """TC-UNIT-DlPricingProfitRule-002"""
        rec = SimpleNamespace(target_markup=-1.0, min_markup=5.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_negative_min_raises(self):
        """TC-UNIT-DlPricingProfitRule-003"""
        rec = SimpleNamespace(target_markup=20.0, min_markup=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_min_greater_than_target_raises(self):
        """TC-UNIT-DlPricingProfitRule-004"""
        rec = SimpleNamespace(target_markup=5.0, min_markup=20.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_min_equal_target_passes(self):
        """TC-UNIT-DlPricingProfitRule-005"""
        rec = SimpleNamespace(target_markup=20.0, min_markup=20.0)
        DlPricingProfitRule._check_markup([rec])  # boundary, không raise

    def test_happy_passes(self):
        """TC-UNIT-DlPricingProfitRule-006"""
        rec = SimpleNamespace(target_markup=20.0, min_markup=5.0)
        DlPricingProfitRule._check_markup([rec])  # không raise


# =============================================================================
# dl.pricing.discount.rule
# =============================================================================
class TestDiscountRuleComputeGroupRank(unittest.TestCase):
    def test_new_is_zero(self):
        """TC-UNIT-DlPricingDiscountRule-001"""
        rec = SimpleNamespace(customer_group="new")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 0)

    def test_existing_is_one(self):
        """TC-UNIT-DlPricingDiscountRule-002"""
        rec = SimpleNamespace(customer_group="existing")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 1)

    def test_loyal_is_two(self):
        """TC-UNIT-DlPricingDiscountRule-003"""
        rec = SimpleNamespace(customer_group="loyal")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 2)


class TestDiscountRuleCheckRates(unittest.TestCase):
    def test_default_above_100_raises(self):
        """TC-UNIT-DlPricingDiscountRule-004"""
        rec = SimpleNamespace(default_rate=101.0, max_rate=101.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_max_below_0_raises(self):
        """TC-UNIT-DlPricingDiscountRule-005"""
        rec = SimpleNamespace(default_rate=0.0, max_rate=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_default_greater_than_max_raises(self):
        """TC-UNIT-DlPricingDiscountRule-006"""
        rec = SimpleNamespace(default_rate=20.0, max_rate=10.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_default_equal_max_passes(self):
        """TC-UNIT-DlPricingDiscountRule-007"""
        rec = SimpleNamespace(default_rate=10.0, max_rate=10.0)
        DlPricingDiscountRule._check_rates([rec])  # boundary, không raise

    def test_happy_passes(self):
        """TC-UNIT-DlPricingDiscountRule-008"""
        rec = SimpleNamespace(default_rate=5.0, max_rate=15.0)
        DlPricingDiscountRule._check_rates([rec])  # không raise


# =============================================================================
# dl.pricing.cost.adjustment.rule — _check_value()
# =============================================================================
class TestCostAdjustmentCheckValue(unittest.TestCase):
    def test_percent_method_above_100_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-001"""
        rec = SimpleNamespace(method="percent_direct", value=101.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_percent_method_negative_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-002"""
        rec = SimpleNamespace(method="percent_cost", value=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_factor_zero_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-003"""
        rec = SimpleNamespace(method="factor", value=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_factor_positive_passes(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-004"""
        rec = SimpleNamespace(method="factor", value=1.5)
        DlPricingCostAdjustmentRule._check_value([rec])  # không raise

    def test_fixed_negative_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-005"""
        rec = SimpleNamespace(method="fixed", value=-500.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_fixed_zero_passes(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-006"""
        rec = SimpleNamespace(method="fixed", value=0.0)
        DlPricingCostAdjustmentRule._check_value([rec])  # 0 hợp lệ (không phải factor)


# =============================================================================
# dl.pricing.operation.rule — _check_values()
# =============================================================================
class TestOperationRuleCheckValues(unittest.TestCase):
    def test_percent_material_above_100_raises(self):
        """TC-UNIT-DlPricingOperationRule-001"""
        rec = SimpleNamespace(method="percent_material", price_rate=150.0, setup_fee=0.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_negative_price_rate_raises(self):
        """TC-UNIT-DlPricingOperationRule-002"""
        rec = SimpleNamespace(method="per_kg", price_rate=-1.0, setup_fee=0.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_negative_setup_fee_raises(self):
        """TC-UNIT-DlPricingOperationRule-003"""
        rec = SimpleNamespace(method="per_kg", price_rate=10.0, setup_fee=-5.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_happy_passes(self):
        """TC-UNIT-DlPricingOperationRule-004"""
        rec = SimpleNamespace(method="per_kg", price_rate=10.0, setup_fee=5.0)
        DlPricingOperationRule._check_values([rec])  # không raise


# =============================================================================
# dl.pricing.complexity.level — _check_factor()
# =============================================================================
class TestComplexityLevelCheckFactor(unittest.TestCase):
    def test_zero_raises(self):
        """TC-UNIT-DlPricingComplexityLevel-001"""
        rec = SimpleNamespace(factor=0.0)
        with self.assertRaises(ValidationError):
            DlPricingComplexityLevel._check_factor([rec])

    def test_negative_raises(self):
        """TC-UNIT-DlPricingComplexityLevel-002"""
        rec = SimpleNamespace(factor=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingComplexityLevel._check_factor([rec])

    def test_positive_passes(self):
        """TC-UNIT-DlPricingComplexityLevel-003"""
        rec = SimpleNamespace(factor=1.1)
        DlPricingComplexityLevel._check_factor([rec])  # không raise


# =============================================================================
# dl.pricing.waste.rule
# =============================================================================
class _EmptyRelation:
    """Đúng ngữ nghĩa Many2one rỗng của Odoo: falsy nhưng .display_name đọc
    được (trả về False), không raise như False.display_name."""
    display_name = False

    def __bool__(self):
        return False


_NO_RELATION = _EmptyRelation()


class TestWasteRuleComputeTargetLabel(unittest.TestCase):
    def test_product_target_uses_product_name(self):
        """TC-UNIT-DlPricingWasteRule-001"""
        rec = SimpleNamespace(target_type="product",
                               product_id=SimpleNamespace(display_name="Thép tấm"))
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "Thép tấm")

    def test_category_target_uses_category_name(self):
        """TC-UNIT-DlPricingWasteRule-002"""
        rec = SimpleNamespace(target_type="category",
                               category_id=SimpleNamespace(display_name="Vật tư kim loại"))
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "Vật tư kim loại")

    def test_product_target_no_product_shows_placeholder(self):
        """TC-UNIT-DlPricingWasteRule-003"""
        rec = SimpleNamespace(target_type="product", product_id=_NO_RELATION)
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "(Chưa chọn vật tư)")


class TestWasteRuleCheckTarget(unittest.TestCase):
    def test_category_type_without_category_raises(self):
        """TC-UNIT-DlPricingWasteRule-004"""
        rec = SimpleNamespace(target_type="category", category_id=False, product_id=False)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_target([rec])

    def test_product_type_without_product_raises(self):
        """TC-UNIT-DlPricingWasteRule-005"""
        rec = SimpleNamespace(target_type="product", category_id=False, product_id=False)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_target([rec])

    def test_category_type_with_category_passes(self):
        """TC-UNIT-DlPricingWasteRule-006"""
        rec = SimpleNamespace(target_type="category",
                               category_id=SimpleNamespace(id=1), product_id=False)
        DlPricingWasteRule._check_target([rec])  # không raise


class TestWasteRuleCheckRates(unittest.TestCase):
    def test_waste_rate_above_100_raises(self):
        """TC-UNIT-DlPricingWasteRule-007"""
        rec = SimpleNamespace(waste_rate=101.0, has_recovery=False, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_waste_rate_negative_raises(self):
        """TC-UNIT-DlPricingWasteRule-008"""
        rec = SimpleNamespace(waste_rate=-1.0, has_recovery=False, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_enabled_but_zero_rate_raises(self):
        """TC-UNIT-DlPricingWasteRule-009"""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_enabled_above_100_raises(self):
        """TC-UNIT-DlPricingWasteRule-010"""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=101.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_disabled_ignores_recovery_rate(self):
        """TC-UNIT-DlPricingWasteRule-011"""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=False, recovery_rate=999.0)
        DlPricingWasteRule._check_rates([rec])  # không raise vì has_recovery=False

    def test_happy_passes(self):
        """TC-UNIT-DlPricingWasteRule-012"""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=50.0)
        DlPricingWasteRule._check_rates([rec])  # không raise


class TestWasteRuleOnchangeTargetType(unittest.TestCase):
    def test_switch_to_category_clears_product(self):
        """TC-UNIT-DlPricingWasteRule-013"""
        rec = SimpleNamespace(target_type="category", product_id=SimpleNamespace(id=1),
                               category_id=False)
        DlPricingWasteRule._onchange_target_type(rec)
        self.assertFalse(rec.product_id)

    def test_switch_to_product_clears_category(self):
        """TC-UNIT-DlPricingWasteRule-014"""
        rec = SimpleNamespace(target_type="product", category_id=SimpleNamespace(id=1),
                               product_id=False)
        DlPricingWasteRule._onchange_target_type(rec)
        self.assertFalse(rec.category_id)


class TestWasteRuleOnchangeHasRecovery(unittest.TestCase):
    def test_disable_recovery_clears_rate_and_scrap(self):
        """TC-UNIT-DlPricingWasteRule-015"""
        rec = SimpleNamespace(has_recovery=False, recovery_rate=50.0,
                               scrap_product_id=SimpleNamespace(id=9))
        DlPricingWasteRule._onchange_has_recovery(rec)
        self.assertEqual(rec.recovery_rate, 0.0)
        self.assertFalse(rec.scrap_product_id)

    def test_enable_recovery_keeps_values(self):
        """TC-UNIT-DlPricingWasteRule-016"""
        rec = SimpleNamespace(has_recovery=True, recovery_rate=50.0,
                               scrap_product_id=SimpleNamespace(id=9))
        DlPricingWasteRule._onchange_has_recovery(rec)
        self.assertEqual(rec.recovery_rate, 50.0)


# =============================================================================
# dl.pricing.rule.mixin — action_apply/action_expire/action_create_revision
# (nhánh raise-sớm, trước khi chạm self._activate_rule()/self.search/write).
# Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage, ngoài phạm vi tự đặt
# ban đầu của file này, xem docstring đầu file).
# =============================================================================
class _RuleRow:
    def __init__(self, state):
        self.state = state

    def ensure_one(self):
        return self

    def __iter__(self):
        return iter([self])


class TestRuleMixinActionApply(unittest.TestCase):
    def test_non_draft_raises(self):
        """TC-UNIT-DlPricingRuleMixin-008"""
        rec = _RuleRow(state="active")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_apply(rec)


class TestRuleMixinActionExpire(unittest.TestCase):
    def test_neither_active_nor_pending_raises(self):
        """TC-UNIT-DlPricingRuleMixin-009"""
        rec = _RuleRow(state="draft")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_expire(rec)


class TestRuleMixinActionCreateRevision(unittest.TestCase):
    def test_non_active_raises(self):
        """TC-UNIT-DlPricingRuleMixin-010"""
        rec = _RuleRow(state="draft")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_create_revision(rec)


# =============================================================================
# dl.pricing.commercial.mixin — action_submit_approval() (nhánh raise-sớm) /
# action_apply_self_approve() (happy path, tự chế self để verify đúng thứ tự
# gọi submit -> check quyền -> approve mà không cần self.env thật).
# =============================================================================
class TestCommercialMixinActionSubmitApproval(unittest.TestCase):
    def test_non_draft_non_rejected_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-002"""
        rec = SimpleNamespace(state="pending")
        rec.ensure_one = lambda: rec
        with self.assertRaises(UserError):
            DlPricingCommercialMixin.action_submit_approval(rec)

    def test_missing_change_reason_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-003"""
        rec = SimpleNamespace(state="draft", change_reason=False)
        rec.ensure_one = lambda: rec
        with self.assertRaises(ValidationError):
            DlPricingCommercialMixin.action_submit_approval(rec)


class TestCommercialMixinActionApplySelfApprove(unittest.TestCase):
    def test_happy_delegates_submit_then_check_then_approve(self):
        """TC-UNIT-DlPricingCommercialMixin-004"""
        calls = []
        fake_request = SimpleNamespace(
            _check_can_resolve=lambda: calls.append("check"),
            action_approve=lambda: calls.append("approve"))
        rec = SimpleNamespace(
            _name="dl.pricing.profit.rule", id=42,
            action_submit_approval=lambda: calls.append("submit"),
            env={"dl.pricing.approval.request": SimpleNamespace(
                search=lambda domain, limit=None: fake_request)},
        )
        rec.ensure_one = lambda: rec
        result = DlPricingCommercialMixin.action_apply_self_approve(rec)
        self.assertEqual(calls, ["submit", "check", "approve"])
        self.assertTrue(result)


# =============================================================================
# dl.pricing.discount.rule — thang chiết khấu theo độ gắn bó (mới ≤ cũ ≤
# thân thiết). lower[field]/higher[field] dùng subscript nên cần __getitem__.
# =============================================================================
class _DiscountRow:
    def __init__(self, customer_group, default_rate, max_rate, state="active",
                 others=None):
        self.customer_group = customer_group
        self.default_rate = default_rate
        self.max_rate = max_rate
        self.state = state
        self.company_id = SimpleNamespace(id=1)
        self.ids = [1]
        self._others = others or []
        # rule._assert_fits_group_ladder() gọi trên chính instance stub —
        # gán thẳng method thật (unbound) làm callable trên self, vì
        # _DiscountRow không kế thừa DlPricingDiscountRule.
        self._assert_fits_group_ladder = lambda: (
            DlPricingDiscountRule._assert_fits_group_ladder(self))

    def __getitem__(self, key):
        return getattr(self, key)

    def ensure_one(self):
        return self

    def search(self, domain):
        return self._others

    def __iter__(self):
        return iter([self])


class TestDiscountRuleCheckGroupLadder(unittest.TestCase):
    def test_less_loyal_group_with_higher_discount_raises(self):
        """TC-UNIT-DlPricingDiscountRule-009 — nhóm 'Khách mới' (ít gắn bó
        hơn) có chiết khấu CAO hơn nhóm 'Khách thân thiết' đang áp dụng —
        đảo bậc, phải chặn."""
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=5.0,
                                     max_rate=10.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=10.0,
                                 max_rate=15.0, others=[loyal_active])
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_group_ladder([new_rule])

    def test_ascending_ladder_passes(self):
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=15.0,
                                     max_rate=20.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=5.0,
                                 max_rate=10.0, others=[loyal_active])
        DlPricingDiscountRule._check_group_ladder([new_rule])  # không raise


class TestDiscountRuleActionSubmitApproval(unittest.TestCase):
    def test_ladder_inversion_blocked_early_at_submit(self):
        """TC-UNIT-DlPricingDiscountRule-010 — chặn NGAY lúc Gửi duyệt (trước
        khi tới super().action_submit_approval()), không đợi tới lúc Áp
        dụng mới phát hiện đảo bậc."""
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=5.0,
                                     max_rate=10.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=10.0,
                                 max_rate=15.0, others=[loyal_active])
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule.action_submit_approval(new_rule)


# =============================================================================
# dl.pricing.cost.adjustment.rule — _check_conditions() (thuần, không
# self.env). Bổ sung 2026-08-11.
# =============================================================================
class TestCostAdjustmentCheckConditions(unittest.TestCase):
    def test_urgent_without_condition_days_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-007"""
        rec = SimpleNamespace(rule_type="urgent", condition_days=0,
                               condition_amount=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_conditions([rec])

    def test_small_order_without_condition_amount_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-008"""
        rec = SimpleNamespace(rule_type="small_order", condition_days=0,
                               condition_amount=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_conditions([rec])

    def test_other_rule_type_skips(self):
        rec = SimpleNamespace(rule_type="material_surcharge", condition_days=0,
                               condition_amount=0.0)
        DlPricingCostAdjustmentRule._check_conditions([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
