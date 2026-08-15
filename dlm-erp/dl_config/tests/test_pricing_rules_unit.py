# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho các model quy tắc cấu hình báo giá
đơn giản trong dl_config: dl.pricing.rule.mixin (phần thuần), dl.pricing.
commercial.mixin, dl.pricing.profit.rule, dl.pricing.discount.rule,
dl.pricing.cost.adjustment.rule, dl.pricing.operation.rule, dl.pricing.
complexity.level, dl.pricing.waste.rule.

Chỉ test constraint/compute/staticmethod thuần Python. Các method dùng
self.search/self.write/self.copy (_assert_fits_group_ladder, action_apply
của mixin gốc, _activate_rule, action_create_revision...) thuộc L2, không
test ở đây.
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


# dl.pricing.rule.mixin: phần thuần Python
class TestDatesOverlap(unittest.TestCase):
    """_dates_overlap(): staticmethod thuần, không self."""

    def test_overlapping_ranges(self):
        """TC-UNIT-DlPricingRuleMixin-001: hai khoảng ngày hiệu lực chồng lấn
        nhau thì _dates_overlap() trả về True."""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 6, 30), date(2026, 6, 1), date(2026, 12, 31)))

    def test_non_overlapping_ranges(self):
        """TC-UNIT-DlPricingRuleMixin-002: hai khoảng ngày không chồng lấn
        (cách nhau hẳn) thì _dates_overlap() trả về False."""
        self.assertFalse(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 3, 31), date(2026, 4, 1), date(2026, 6, 30)))

    def test_open_ended_a_to_none_treated_as_far_future(self):
        """TC-UNIT-DlPricingRuleMixin-003: khoảng A không có ngày kết thúc
        (valid_to=None) được coi là kéo dài vô hạn, nên vẫn chồng lấn với
        khoảng B ở tương lai xa."""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), None, date(2030, 1, 1), date(2030, 6, 30)))

    def test_touching_boundary_counts_as_overlap(self):
        """TC-UNIT-DlPricingRuleMixin-004: hai khoảng ngày chạm đúng tại biên
        (ngày kết thúc của A trùng ngày bắt đầu của B) vẫn được tính là chồng
        lấn."""
        self.assertTrue(DlPricingRuleMixin._dates_overlap(
            date(2026, 1, 1), date(2026, 6, 30), date(2026, 6, 30), date(2026, 12, 31)))


class TestCheckValidRange(unittest.TestCase):
    """_check_valid_range(): constraint thuần."""

    def test_from_after_to_raises(self):
        """TC-UNIT-DlPricingRuleMixin-005: valid_from sau valid_to thì
        _check_valid_range() báo lỗi ValidationError."""
        rec = SimpleNamespace(valid_from="2026-06-01", valid_to="2026-01-01")
        with self.assertRaises(ValidationError):
            DlPricingRuleMixin._check_valid_range([rec])

    def test_no_valid_to_passes(self):
        """TC-UNIT-DlPricingRuleMixin-006: không nhập valid_to (để trống) thì
        _check_valid_range() không báo lỗi."""
        rec = SimpleNamespace(valid_from="2026-01-01", valid_to=False)
        DlPricingRuleMixin._check_valid_range([rec])  # không raise

    def test_from_before_to_passes(self):
        """TC-UNIT-DlPricingRuleMixin-007: valid_from trước valid_to thì
        _check_valid_range() không báo lỗi."""
        rec = SimpleNamespace(valid_from="2026-01-01", valid_to="2026-12-31")
        DlPricingRuleMixin._check_valid_range([rec])  # không raise


# dl.pricing.commercial.mixin: action_apply() luôn raise vì chưa gửi duyệt thì
# không được Áp dụng trực tiếp.
class TestCommercialMixinActionApply(unittest.TestCase):
    def test_always_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-001: gọi action_apply() trên
        mixin thương mại luôn báo lỗi UserError vì phải gửi duyệt trước, chưa
        được phép áp dụng trực tiếp."""
        rec = SimpleNamespace()
        with self.assertRaises(UserError):
            DlPricingCommercialMixin.action_apply(rec)


# dl.pricing.profit.rule
class TestProfitRuleComputeName(unittest.TestCase):
    def test_happy_format(self):
        """TC-UNIT-DlPricingProfitRule-001: với target_markup=20.0,
        min_markup=5.0, revision=1 thì _compute_name() sinh tên "Markup mục
        tiêu 20.0% / sàn 5.0% (b1)"."""
        rec = SimpleNamespace(target_markup=20.0, min_markup=5.0, revision=1)
        DlPricingProfitRule._compute_name([rec])
        self.assertEqual(rec.name, "Markup mục tiêu 20.0% / sàn 5.0% (b1)")


class TestProfitRuleCheckMarkup(unittest.TestCase):
    def test_negative_target_raises(self):
        """TC-UNIT-DlPricingProfitRule-002: target_markup âm thì
        _check_markup() báo lỗi ValidationError."""
        rec = SimpleNamespace(target_markup=-1.0, min_markup=5.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_negative_min_raises(self):
        """TC-UNIT-DlPricingProfitRule-003: min_markup âm thì
        _check_markup() báo lỗi ValidationError."""
        rec = SimpleNamespace(target_markup=20.0, min_markup=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_min_greater_than_target_raises(self):
        """TC-UNIT-DlPricingProfitRule-004: min_markup lớn hơn target_markup
        thì _check_markup() báo lỗi ValidationError."""
        rec = SimpleNamespace(target_markup=5.0, min_markup=20.0)
        with self.assertRaises(ValidationError):
            DlPricingProfitRule._check_markup([rec])

    def test_min_equal_target_passes(self):
        """TC-UNIT-DlPricingProfitRule-005: min_markup bằng target_markup
        (trường hợp biên) thì _check_markup() không báo lỗi."""
        rec = SimpleNamespace(target_markup=20.0, min_markup=20.0)
        DlPricingProfitRule._check_markup([rec])  # boundary, không raise

    def test_happy_passes(self):
        """TC-UNIT-DlPricingProfitRule-006: target_markup và min_markup hợp
        lệ (target lớn hơn min) thì _check_markup() không báo lỗi."""
        rec = SimpleNamespace(target_markup=20.0, min_markup=5.0)
        DlPricingProfitRule._check_markup([rec])  # không raise


# dl.pricing.discount.rule
class TestDiscountRuleComputeGroupRank(unittest.TestCase):
    def test_new_is_zero(self):
        """TC-UNIT-DlPricingDiscountRule-001: nhóm khách hàng "new" (khách
        mới) thì _compute_group_rank() gán group_rank = 0."""
        rec = SimpleNamespace(customer_group="new")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 0)

    def test_existing_is_one(self):
        """TC-UNIT-DlPricingDiscountRule-002: nhóm khách hàng "existing"
        (khách hiện hữu) thì _compute_group_rank() gán group_rank = 1."""
        rec = SimpleNamespace(customer_group="existing")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 1)

    def test_loyal_is_two(self):
        """TC-UNIT-DlPricingDiscountRule-003: nhóm khách hàng "loyal" (khách
        thân thiết) thì _compute_group_rank() gán group_rank = 2."""
        rec = SimpleNamespace(customer_group="loyal")
        DlPricingDiscountRule._compute_group_rank([rec])
        self.assertEqual(rec.group_rank, 2)


class TestDiscountRuleCheckRates(unittest.TestCase):
    def test_default_above_100_raises(self):
        """TC-UNIT-DlPricingDiscountRule-004: default_rate vượt quá 100% thì
        _check_rates() báo lỗi ValidationError."""
        rec = SimpleNamespace(default_rate=101.0, max_rate=101.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_max_below_0_raises(self):
        """TC-UNIT-DlPricingDiscountRule-005: max_rate âm (dưới 0%) thì
        _check_rates() báo lỗi ValidationError."""
        rec = SimpleNamespace(default_rate=0.0, max_rate=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_default_greater_than_max_raises(self):
        """TC-UNIT-DlPricingDiscountRule-006: default_rate lớn hơn max_rate
        thì _check_rates() báo lỗi ValidationError."""
        rec = SimpleNamespace(default_rate=20.0, max_rate=10.0)
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_rates([rec])

    def test_default_equal_max_passes(self):
        """TC-UNIT-DlPricingDiscountRule-007: default_rate bằng max_rate
        (trường hợp biên) thì _check_rates() không báo lỗi."""
        rec = SimpleNamespace(default_rate=10.0, max_rate=10.0)
        DlPricingDiscountRule._check_rates([rec])  # boundary, không raise

    def test_happy_passes(self):
        """TC-UNIT-DlPricingDiscountRule-008: default_rate và max_rate hợp
        lệ (default nhỏ hơn max) thì _check_rates() không báo lỗi."""
        rec = SimpleNamespace(default_rate=5.0, max_rate=15.0)
        DlPricingDiscountRule._check_rates([rec])  # không raise


# dl.pricing.cost.adjustment.rule: _check_value()
class TestCostAdjustmentCheckValue(unittest.TestCase):
    def test_percent_method_above_100_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-001: phương thức tính theo
        phần trăm (percent_direct) mà value vượt quá 100% thì _check_value()
        báo lỗi ValidationError."""
        rec = SimpleNamespace(method="percent_direct", value=101.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_percent_method_negative_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-002: phương thức percent_cost
        mà value âm thì _check_value() báo lỗi ValidationError."""
        rec = SimpleNamespace(method="percent_cost", value=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_factor_zero_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-003: phương thức factor mà
        value bằng 0 thì _check_value() báo lỗi ValidationError, vì hệ số
        nhân không được bằng 0."""
        rec = SimpleNamespace(method="factor", value=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_factor_positive_passes(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-004: phương thức factor với
        value dương (1.5) thì _check_value() không báo lỗi."""
        rec = SimpleNamespace(method="factor", value=1.5)
        DlPricingCostAdjustmentRule._check_value([rec])  # không raise

    def test_fixed_negative_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-005: phương thức fixed mà
        value âm thì _check_value() báo lỗi ValidationError."""
        rec = SimpleNamespace(method="fixed", value=-500.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_value([rec])

    def test_fixed_zero_passes(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-006: phương thức fixed với
        value bằng 0 thì _check_value() không báo lỗi, vì giá trị 0 chỉ bị
        chặn với phương thức factor."""
        rec = SimpleNamespace(method="fixed", value=0.0)
        DlPricingCostAdjustmentRule._check_value([rec])  # 0 hợp lệ (không phải factor)


# dl.pricing.operation.rule: _check_values()
class TestOperationRuleCheckValues(unittest.TestCase):
    def test_percent_material_above_100_raises(self):
        """TC-UNIT-DlPricingOperationRule-001: phương thức percent_material
        mà price_rate vượt quá 100% thì _check_values() báo lỗi
        ValidationError."""
        rec = SimpleNamespace(method="percent_material", price_rate=150.0, setup_fee=0.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_negative_price_rate_raises(self):
        """TC-UNIT-DlPricingOperationRule-002: price_rate âm thì
        _check_values() báo lỗi ValidationError."""
        rec = SimpleNamespace(method="per_kg", price_rate=-1.0, setup_fee=0.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_negative_setup_fee_raises(self):
        """TC-UNIT-DlPricingOperationRule-003: setup_fee âm thì
        _check_values() báo lỗi ValidationError."""
        rec = SimpleNamespace(method="per_kg", price_rate=10.0, setup_fee=-5.0)
        with self.assertRaises(ValidationError):
            DlPricingOperationRule._check_values([rec])

    def test_happy_passes(self):
        """TC-UNIT-DlPricingOperationRule-004: method, price_rate và
        setup_fee đều hợp lệ thì _check_values() không báo lỗi."""
        rec = SimpleNamespace(method="per_kg", price_rate=10.0, setup_fee=5.0)
        DlPricingOperationRule._check_values([rec])  # không raise


# dl.pricing.complexity.level: _check_factor()
class TestComplexityLevelCheckFactor(unittest.TestCase):
    def test_zero_raises(self):
        """TC-UNIT-DlPricingComplexityLevel-001: factor bằng 0 thì
        _check_factor() báo lỗi ValidationError."""
        rec = SimpleNamespace(factor=0.0)
        with self.assertRaises(ValidationError):
            DlPricingComplexityLevel._check_factor([rec])

    def test_negative_raises(self):
        """TC-UNIT-DlPricingComplexityLevel-002: factor âm thì
        _check_factor() báo lỗi ValidationError."""
        rec = SimpleNamespace(factor=-1.0)
        with self.assertRaises(ValidationError):
            DlPricingComplexityLevel._check_factor([rec])

    def test_positive_passes(self):
        """TC-UNIT-DlPricingComplexityLevel-003: factor dương (1.1) thì
        _check_factor() không báo lỗi."""
        rec = SimpleNamespace(factor=1.1)
        DlPricingComplexityLevel._check_factor([rec])  # không raise


# dl.pricing.waste.rule
class _EmptyRelation:
    """Đúng ngữ nghĩa Many2one rỗng của Odoo: falsy nhưng .display_name đọc
    được (trả về False), không raise như False.display_name."""
    display_name = False

    def __bool__(self):
        return False


_NO_RELATION = _EmptyRelation()


class TestWasteRuleComputeTargetLabel(unittest.TestCase):
    def test_product_target_uses_product_name(self):
        """TC-UNIT-DlPricingWasteRule-001: target_type="product" và có
        product_id thì _compute_target_label() lấy target_label theo tên
        vật tư (display_name của product_id)."""
        rec = SimpleNamespace(target_type="product",
                               product_id=SimpleNamespace(display_name="Thép tấm"))
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "Thép tấm")

    def test_category_target_uses_category_name(self):
        """TC-UNIT-DlPricingWasteRule-002: target_type="category" và có
        category_id thì _compute_target_label() lấy target_label theo tên
        danh mục (display_name của category_id)."""
        rec = SimpleNamespace(target_type="category",
                               category_id=SimpleNamespace(display_name="Vật tư kim loại"))
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "Vật tư kim loại")

    def test_product_target_no_product_shows_placeholder(self):
        """TC-UNIT-DlPricingWasteRule-003: target_type="product" nhưng chưa
        chọn product_id thì _compute_target_label() trả về placeholder
        "(Chưa chọn vật tư)"."""
        rec = SimpleNamespace(target_type="product", product_id=_NO_RELATION)
        DlPricingWasteRule._compute_target_label([rec])
        self.assertEqual(rec.target_label, "(Chưa chọn vật tư)")


class TestWasteRuleCheckTarget(unittest.TestCase):
    def test_category_type_without_category_raises(self):
        """TC-UNIT-DlPricingWasteRule-004: target_type="category" nhưng
        chưa chọn category_id thì _check_target() báo lỗi ValidationError."""
        rec = SimpleNamespace(target_type="category", category_id=False, product_id=False)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_target([rec])

    def test_product_type_without_product_raises(self):
        """TC-UNIT-DlPricingWasteRule-005: target_type="product" nhưng chưa
        chọn product_id thì _check_target() báo lỗi ValidationError."""
        rec = SimpleNamespace(target_type="product", category_id=False, product_id=False)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_target([rec])

    def test_category_type_with_category_passes(self):
        """TC-UNIT-DlPricingWasteRule-006: target_type="category" và có
        category_id thì _check_target() không báo lỗi."""
        rec = SimpleNamespace(target_type="category",
                               category_id=SimpleNamespace(id=1), product_id=False)
        DlPricingWasteRule._check_target([rec])  # không raise


class TestWasteRuleCheckRates(unittest.TestCase):
    def test_waste_rate_above_100_raises(self):
        """TC-UNIT-DlPricingWasteRule-007: waste_rate vượt quá 100% thì
        _check_rates() báo lỗi ValidationError."""
        rec = SimpleNamespace(waste_rate=101.0, has_recovery=False, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_waste_rate_negative_raises(self):
        """TC-UNIT-DlPricingWasteRule-008: waste_rate âm thì _check_rates()
        báo lỗi ValidationError."""
        rec = SimpleNamespace(waste_rate=-1.0, has_recovery=False, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_enabled_but_zero_rate_raises(self):
        """TC-UNIT-DlPricingWasteRule-009: bật thu hồi phế liệu
        (has_recovery=True) nhưng recovery_rate bằng 0 thì _check_rates()
        báo lỗi ValidationError."""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=0.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_enabled_above_100_raises(self):
        """TC-UNIT-DlPricingWasteRule-010: bật thu hồi phế liệu nhưng
        recovery_rate vượt quá 100% thì _check_rates() báo lỗi
        ValidationError."""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=101.0)
        with self.assertRaises(ValidationError):
            DlPricingWasteRule._check_rates([rec])

    def test_recovery_disabled_ignores_recovery_rate(self):
        """TC-UNIT-DlPricingWasteRule-011: tắt thu hồi phế liệu
        (has_recovery=False) thì _check_rates() bỏ qua giá trị recovery_rate
        dù nó vô lý (999%), không báo lỗi."""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=False, recovery_rate=999.0)
        DlPricingWasteRule._check_rates([rec])  # không raise vì has_recovery=False

    def test_happy_passes(self):
        """TC-UNIT-DlPricingWasteRule-012: waste_rate và recovery_rate đều
        hợp lệ, has_recovery=True thì _check_rates() không báo lỗi."""
        rec = SimpleNamespace(waste_rate=5.0, has_recovery=True, recovery_rate=50.0)
        DlPricingWasteRule._check_rates([rec])  # không raise


class TestWasteRuleOnchangeTargetType(unittest.TestCase):
    def test_switch_to_category_clears_product(self):
        """TC-UNIT-DlPricingWasteRule-013: đổi target_type sang "category"
        thì _onchange_target_type() tự xóa product_id đang chọn."""
        rec = SimpleNamespace(target_type="category", product_id=SimpleNamespace(id=1),
                               category_id=False)
        DlPricingWasteRule._onchange_target_type(rec)
        self.assertFalse(rec.product_id)

    def test_switch_to_product_clears_category(self):
        """TC-UNIT-DlPricingWasteRule-014: đổi target_type sang "product"
        thì _onchange_target_type() tự xóa category_id đang chọn."""
        rec = SimpleNamespace(target_type="product", category_id=SimpleNamespace(id=1),
                               product_id=False)
        DlPricingWasteRule._onchange_target_type(rec)
        self.assertFalse(rec.category_id)


class TestWasteRuleOnchangeHasRecovery(unittest.TestCase):
    def test_disable_recovery_clears_rate_and_scrap(self):
        """TC-UNIT-DlPricingWasteRule-015: tắt has_recovery thì
        _onchange_has_recovery() tự đặt recovery_rate về 0 và xóa
        scrap_product_id."""
        rec = SimpleNamespace(has_recovery=False, recovery_rate=50.0,
                               scrap_product_id=SimpleNamespace(id=9))
        DlPricingWasteRule._onchange_has_recovery(rec)
        self.assertEqual(rec.recovery_rate, 0.0)
        self.assertFalse(rec.scrap_product_id)

    def test_enable_recovery_keeps_values(self):
        """TC-UNIT-DlPricingWasteRule-016: bật has_recovery thì
        _onchange_has_recovery() giữ nguyên recovery_rate đang có, không
        xóa."""
        rec = SimpleNamespace(has_recovery=True, recovery_rate=50.0,
                               scrap_product_id=SimpleNamespace(id=9))
        DlPricingWasteRule._onchange_has_recovery(rec)
        self.assertEqual(rec.recovery_rate, 50.0)


# dl.pricing.rule.mixin: action_apply/action_expire/action_create_revision,
# chỉ nhánh raise sớm, trước khi chạm self._activate_rule()/self.search/write.
class _RuleRow:
    def __init__(self, state):
        self.state = state

    def ensure_one(self):
        return self

    def __iter__(self):
        return iter([self])


class TestRuleMixinActionApply(unittest.TestCase):
    def test_non_draft_raises(self):
        """TC-UNIT-DlPricingRuleMixin-008: quy tắc không ở trạng thái draft
        (nháp) mà gọi action_apply() thì báo lỗi UserError."""
        rec = _RuleRow(state="active")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_apply(rec)


class TestRuleMixinActionExpire(unittest.TestCase):
    def test_neither_active_nor_pending_raises(self):
        """TC-UNIT-DlPricingRuleMixin-009: quy tắc không ở trạng thái active
        hay pending mà gọi action_expire() thì báo lỗi UserError."""
        rec = _RuleRow(state="draft")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_expire(rec)


class TestRuleMixinActionCreateRevision(unittest.TestCase):
    def test_non_active_raises(self):
        """TC-UNIT-DlPricingRuleMixin-010: quy tắc không ở trạng thái active
        mà gọi action_create_revision() thì báo lỗi UserError."""
        rec = _RuleRow(state="draft")
        with self.assertRaises(UserError):
            DlPricingRuleMixin.action_create_revision(rec)


# dl.pricing.commercial.mixin: action_submit_approval() (nhánh raise sớm) và
# action_apply_self_approve() (happy path, tự chế self để verify đúng thứ tự
# gọi submit, check quyền, rồi approve, mà không cần self.env thật).
class TestCommercialMixinActionSubmitApproval(unittest.TestCase):
    def test_non_draft_non_rejected_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-002: quy tắc không ở trạng thái
        draft hay rejected mà gọi action_submit_approval() thì báo lỗi
        UserError."""
        rec = SimpleNamespace(state="pending")
        rec.ensure_one = lambda: rec
        with self.assertRaises(UserError):
            DlPricingCommercialMixin.action_submit_approval(rec)

    def test_missing_change_reason_raises(self):
        """TC-UNIT-DlPricingCommercialMixin-003: trạng thái draft nhưng
        thiếu change_reason (lý do thay đổi) thì action_submit_approval()
        báo lỗi ValidationError."""
        rec = SimpleNamespace(state="draft", change_reason=False)
        rec.ensure_one = lambda: rec
        with self.assertRaises(ValidationError):
            DlPricingCommercialMixin.action_submit_approval(rec)


class TestCommercialMixinActionApplySelfApprove(unittest.TestCase):
    def test_happy_delegates_submit_then_check_then_approve(self):
        """TC-UNIT-DlPricingCommercialMixin-004: action_apply_self_approve()
        gọi lần lượt action_submit_approval(), _check_can_resolve() rồi
        action_approve() của yêu cầu duyệt tìm được, và trả về kết quả
        truthy."""
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


# dl.pricing.discount.rule: thang chiết khấu theo độ gắn bó (mới <= cũ <=
# thân thiết). lower[field]/higher[field] dùng subscript nên cần __getitem__.
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
        # rule._assert_fits_group_ladder() gọi trên chính instance stub, nên
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
        """TC-UNIT-DlPricingDiscountRule-009: nhóm "Khách mới" (ít gắn bó hơn) có
        chiết khấu cao hơn nhóm "Khách thân thiết" đang áp dụng, tức đảo bậc,
        phải chặn."""
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=5.0,
                                     max_rate=10.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=10.0,
                                 max_rate=15.0, others=[loyal_active])
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule._check_group_ladder([new_rule])

    def test_ascending_ladder_passes(self):
        """Nhóm "Khách mới" (ít gắn bó hơn) có chiết khấu thấp hơn nhóm
        "Khách thân thiết", đúng thứ bậc tăng dần, kỳ vọng không raise."""
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=15.0,
                                     max_rate=20.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=5.0,
                                 max_rate=10.0, others=[loyal_active])
        DlPricingDiscountRule._check_group_ladder([new_rule])  # không raise


class TestDiscountRuleActionSubmitApproval(unittest.TestCase):
    def test_ladder_inversion_blocked_early_at_submit(self):
        """TC-UNIT-DlPricingDiscountRule-010: chặn ngay lúc Gửi duyệt, trước khi
        tới super().action_submit_approval(), không đợi tới lúc Áp dụng mới
        phát hiện đảo bậc."""
        loyal_active = _DiscountRow(customer_group="loyal", default_rate=5.0,
                                     max_rate=10.0)
        new_rule = _DiscountRow(customer_group="new", default_rate=10.0,
                                 max_rate=15.0, others=[loyal_active])
        with self.assertRaises(ValidationError):
            DlPricingDiscountRule.action_submit_approval(new_rule)


# dl.pricing.cost.adjustment.rule: _check_conditions() (thuần, không self.env).
class TestCostAdjustmentCheckConditions(unittest.TestCase):
    def test_urgent_without_condition_days_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-007: rule_type="urgent" (phụ
        phí gấp) nhưng condition_days bằng 0 (chưa cấu hình) thì
        _check_conditions() báo lỗi ValidationError."""
        rec = SimpleNamespace(rule_type="urgent", condition_days=0,
                               condition_amount=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_conditions([rec])

    def test_small_order_without_condition_amount_raises(self):
        """TC-UNIT-DlPricingCostAdjustmentRule-008: rule_type="small_order"
        (phụ phí đơn nhỏ) nhưng condition_amount bằng 0 (chưa cấu hình) thì
        _check_conditions() báo lỗi ValidationError."""
        rec = SimpleNamespace(rule_type="small_order", condition_days=0,
                               condition_amount=0.0)
        with self.assertRaises(ValidationError):
            DlPricingCostAdjustmentRule._check_conditions([rec])

    def test_other_rule_type_skips(self):
        """rule_type không phải urgent/small_order (material_surcharge) thì
        không cần condition_days/condition_amount, kỳ vọng không raise."""
        rec = SimpleNamespace(rule_type="material_surcharge", condition_days=0,
                               condition_amount=0.0)
        DlPricingCostAdjustmentRule._check_conditions([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
