"""Unit test L1 (thuần, không ORM/DB) cho dl.pricing.approval.matrix.
Sheet nguồn: DlPricingApprovalMatrix trong Report_5_1_UnitTests_L1.xlsx.

Chỉ test phần thuần Python của evaluate_quotation() (Priority #2 — Approval
Rule Engine). _resolve_value_row() gọi self.search(...) nên được stub qua
patch.object ở cấp class — patch class thay vì gán instance vì DlPricing-
ApprovalMatrix là models.Model dùng __slots__, không gán được thuộc tính lên
instance thường (giống lý do đã gặp ở Priority #1).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ..models.pricing_matrix import DlPricingApprovalMatrix


class _FakeRow:
    """Stand-in cho recordset trả về từ _resolve_value_row()/self.browse().

    present=False mô phỏng recordset rỗng (falsy, không có dòng nào khớp
    ngưỡng) — evaluate_quotation() chỉ đọc field khi row truthy nên các case
    "rỗng" không cần set field thật.
    """

    def __init__(self, level_rank=0, approval_level="none", id=0, revision=0,
                 present=True):
        self.level_rank = level_rank
        self.approval_level = approval_level
        self.currency_id = False  # False -> _fmt_money() không cần .symbol
        self.value_from = 0.0
        self.id = id
        self.revision = revision
        self._present = present

    def __bool__(self):
        return self._present


_EMPTY_ROW = _FakeRow(present=False)


def _evaluate(row, **flags):
    """Gọi evaluate_quotation() thật với _resolve_value_row()/browse() đã
    patch ở cấp class — company truyền vào phải truthy để tránh code chạm
    self.env.company (company or self.env.company)."""
    with patch.object(DlPricingApprovalMatrix, "browse", return_value=_EMPTY_ROW), \
         patch.object(DlPricingApprovalMatrix, "_resolve_value_row", return_value=row):
        matrix = object.__new__(DlPricingApprovalMatrix)
        return matrix.evaluate_quotation(
            25_000_000, company=SimpleNamespace(id=1), date=None, **flags)


class TestEvaluateQuotation(unittest.TestCase):
    def test_value_axis_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-001"""
        row = _FakeRow(level_rank=1, approval_level="sales_manager", id=10, revision=2)
        result = _evaluate(row, discount_above_default=False,
                            discount_above_max=False, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "sales_manager")
        self.assertEqual(result["rank"], 1)
        self.assertEqual(result["level_label"], "Trưởng kinh doanh")
        self.assertEqual(result["matrix_row_id"], 10)
        self.assertEqual(result["matrix_revision"], 2)
        self.assertEqual(len(result["reasons"]), 1)

    def test_value_axis_none_level_not_a_candidate(self):
        """TC-UNIT-DlPricingApprovalMatrix-002"""
        row = _FakeRow(level_rank=0, approval_level="none", id=5, revision=1)
        result = _evaluate(row, discount_above_default=False,
                            discount_above_max=False, below_floor=False)
        self.assertFalse(result["required"])

    def test_discount_above_default_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-003"""
        result = _evaluate(_EMPTY_ROW, discount_above_default=True,
                            discount_above_max=False, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "sales_manager")
        self.assertEqual(result["rank"], 1)
        self.assertEqual(len(result["reasons"]), 1)

    def test_discount_above_max_wins_over_default_elif(self):
        """TC-UNIT-DlPricingApprovalMatrix-004"""
        result = _evaluate(_EMPTY_ROW, discount_above_default=True,
                            discount_above_max=True, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        # elif: above_default không được cộng thêm khi above_max cũng True.
        self.assertEqual(len(result["reasons"]), 1)

    def test_below_floor_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-005"""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=False, below_floor=True)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(len(result["reasons"]), 1)

    def test_multiple_axes_take_max_rank_but_merge_all_reasons(self):
        """TC-UNIT-DlPricingApprovalMatrix-006"""
        row = _FakeRow(level_rank=1, approval_level="sales_manager", id=1, revision=1)
        result = _evaluate(row, discount_above_default=False,
                            discount_above_max=False, below_floor=True)
        self.assertEqual(result["level"], "ceo")  # rank cao nhất thắng
        self.assertEqual(result["rank"], 2)
        # nhưng reasons gồm CẢ lý do giá trị lẫn lý do giá sàn, không chỉ của "ceo".
        self.assertEqual(len(result["reasons"]), 2)

    def test_no_axis_fires(self):
        """TC-UNIT-DlPricingApprovalMatrix-007"""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=False, below_floor=False)
        self.assertEqual(result, {
            "required": False, "level": False, "level_label": "",
            "rank": 0, "matrix_row_id": False, "matrix_revision": False,
            "reasons": [],
        })

    def test_discount_above_max_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-008"""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=True, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(len(result["reasons"]), 1)


if __name__ == "__main__":
    unittest.main()
