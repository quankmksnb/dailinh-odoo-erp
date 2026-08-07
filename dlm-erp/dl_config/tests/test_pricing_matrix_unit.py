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

from odoo.exceptions import ValidationError

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

    def test_discount_above_default_only_no_longer_triggers(self):
        """TC-UNIT-DlPricingApprovalMatrix-003 — chốt 2026-07-27 (xem comment
        mục B trong evaluate_quotation): 'Mặc định' chỉ còn là mức gợi ý/tự
        điền, KHÔNG còn kích hoạt duyệt — discount_above_default vẫn nhận để
        tương thích chữ ký nhưng không tạo candidate nào nữa."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=True,
                            discount_above_max=False, below_floor=False)
        self.assertFalse(result["required"])

    def test_discount_above_max_and_below_floor_take_max_rank(self):
        """TC-UNIT-DlPricingApprovalMatrix-004 — chốt 2026-07-27: vượt mức
        tối đa một mình chỉ lên Trưởng KD (rank 1, xem TC-008); nếu ĐỒNG THỜI
        below_floor (rank 2, CEO) thì CEO thắng theo rank cao nhất, nhưng
        reasons vẫn giữ đủ cả 2 lý do."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=True, below_floor=True)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(len(result["reasons"]), 2)

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
        """TC-UNIT-DlPricingApprovalMatrix-008 — chốt 2026-07-27: vượt mức
        tối đa của nhóm khách (Sales tự quyết được tới mức tối đa, vượt mới
        cần duyệt) chỉ cần Trưởng KD duyệt ngoại lệ, không cần lên CEO."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=True, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "sales_manager")
        self.assertEqual(result["rank"], 1)
        self.assertEqual(len(result["reasons"]), 1)


_VND = SimpleNamespace(symbol="₫")


# =============================================================================
# _compute_name() — thuần Python, chỉ đọc field + _fmt_money() (module-level).
# =============================================================================
class TestComputeName(unittest.TestCase):
    def test_happy_format(self):
        """TC-UNIT-DlPricingApprovalMatrix-009"""
        rec = SimpleNamespace(value_from=20_000_000, approval_level="sales_manager",
                               revision=1, currency_id=_VND)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 20.000.000 ₫ → Trưởng kinh doanh (b1)")

    def test_ceo_level_and_revision_2(self):
        """TC-UNIT-DlPricingApprovalMatrix-010"""
        rec = SimpleNamespace(value_from=100_000_000, approval_level="ceo",
                               revision=2, currency_id=_VND)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 100.000.000 ₫ → Giám đốc (b2)")

    def test_no_currency_no_symbol_suffix(self):
        """TC-UNIT-DlPricingApprovalMatrix-011"""
        rec = SimpleNamespace(value_from=5000, approval_level="none",
                               revision=1, currency_id=False)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 5.000 → Không cần duyệt (b1)")


# =============================================================================
# _compute_level_rank() — map approval_level -> rank qua _LEVEL_RANK.
# =============================================================================
class TestComputeLevelRank(unittest.TestCase):
    def test_none_is_zero(self):
        """TC-UNIT-DlPricingApprovalMatrix-012"""
        rec = SimpleNamespace(approval_level="none")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 0)

    def test_sales_manager_is_one(self):
        """TC-UNIT-DlPricingApprovalMatrix-013"""
        rec = SimpleNamespace(approval_level="sales_manager")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 1)

    def test_ceo_is_two(self):
        """TC-UNIT-DlPricingApprovalMatrix-014"""
        rec = SimpleNamespace(approval_level="ceo")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 2)


# =============================================================================
# _check_value_from() — constraint thuần, chỉ so sánh value_from < 0.
# =============================================================================
class TestCheckValueFrom(unittest.TestCase):
    def test_negative_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-015"""
        rec = SimpleNamespace(value_from=-1)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._check_value_from([rec])

    def test_zero_boundary_passes(self):
        """TC-UNIT-DlPricingApprovalMatrix-016"""
        rec = SimpleNamespace(value_from=0)
        DlPricingApprovalMatrix._check_value_from([rec])  # không raise

    def test_positive_passes(self):
        """TC-UNIT-DlPricingApprovalMatrix-017"""
        rec = SimpleNamespace(value_from=20_000_000)
        DlPricingApprovalMatrix._check_value_from([rec])  # không raise


# =============================================================================
# _diff_label() — self.ensure_one() rồi đọc field trực tiếp, không đụng env.
# =============================================================================
class _MatrixRow(SimpleNamespace):
    def ensure_one(self):
        return self


class TestDiffLabel(unittest.TestCase):
    def test_without_specific_approver(self):
        """TC-UNIT-DlPricingApprovalMatrix-018"""
        rec = _MatrixRow(value_from=20_000_000, approval_level="sales_manager",
                          currency_id=_VND, approver_user_id=None)
        self.assertEqual(DlPricingApprovalMatrix._diff_label(rec),
                          "Ngưỡng 20.000.000 ₫ — Trưởng kinh doanh")

    def test_with_specific_approver_appends_name(self):
        """TC-UNIT-DlPricingApprovalMatrix-019"""
        approver = SimpleNamespace(name="Nguyễn Văn A")
        rec = _MatrixRow(value_from=20_000_000, approval_level="sales_manager",
                          currency_id=_VND, approver_user_id=approver)
        self.assertEqual(DlPricingApprovalMatrix._diff_label(rec),
                          "Ngưỡng 20.000.000 ₫ — Trưởng kinh doanh, người duyệt: Nguyễn Văn A")


# =============================================================================
# _change_summary(old) — so sánh self vs old, liệt kê đúng phần đổi.
# =============================================================================
class _EmptyApprover:
    """Đúng ngữ nghĩa Many2one rỗng của Odoo: falsy nhưng .name đọc được
    (trả về False), không raise như None.name."""
    name = False

    def __bool__(self):
        return False


_NO_APPROVER = _EmptyApprover()


class TestChangeSummary(unittest.TestCase):
    def _row(self, value_from=20_000_000, approval_level="sales_manager", approver=_NO_APPROVER):
        return _MatrixRow(value_from=value_from, approval_level=approval_level,
                           currency_id=_VND, approver_user_id=approver)

    def test_no_old_means_new_threshold(self):
        """TC-UNIT-DlPricingApprovalMatrix-020"""
        rec = self._row()
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, None),
                          "Thêm ngưỡng mới vào thang phê duyệt")

    def test_identical_means_no_change(self):
        """TC-UNIT-DlPricingApprovalMatrix-021"""
        rec = self._row()
        old = self._row()
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, old),
                          "Không thay đổi nội dung chính")

    def test_value_from_changed(self):
        """TC-UNIT-DlPricingApprovalMatrix-022"""
        rec = self._row(value_from=50_000_000)
        old = self._row(value_from=20_000_000)
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, old),
                          "Ngưỡng: 20.000.000 ₫ → 50.000.000 ₫")

    def test_level_and_approver_changed_joined(self):
        """TC-UNIT-DlPricingApprovalMatrix-023"""
        approver = SimpleNamespace(name="Trần Thị B")
        rec = self._row(approval_level="ceo", approver=approver)
        old = self._row(approval_level="sales_manager", approver=_NO_APPROVER)
        summary = DlPricingApprovalMatrix._change_summary(rec, old)
        self.assertIn("Cấp duyệt: Trưởng kinh doanh → Giám đốc", summary)
        self.assertIn("Người duyệt cụ thể: (theo vai trò) → Trần Thị B", summary)
        self.assertEqual(summary.count(";"), 1)  # đúng 2 phần đổi, nối bằng "; "


# =============================================================================
# _allowed_user_ids() — chỉ test 2 nhánh không đụng self.env.ref(...); nhánh
# "theo vai trò" (group lookup qua env.ref) thuộc L2, không test ở đây.
# =============================================================================
class TestAllowedUserIds(unittest.TestCase):
    def test_none_level_returns_empty(self):
        """TC-UNIT-DlPricingApprovalMatrix-024"""
        rec = _MatrixRow(approval_level="none", approver_user_id=None)
        self.assertEqual(DlPricingApprovalMatrix._allowed_user_ids(rec), [])

    def test_specific_approver_returns_its_ids(self):
        """TC-UNIT-DlPricingApprovalMatrix-025"""
        approver = SimpleNamespace(ids=[7])
        rec = _MatrixRow(approval_level="sales_manager", approver_user_id=approver)
        self.assertEqual(DlPricingApprovalMatrix._allowed_user_ids(rec), [7])


# =============================================================================
# _compute_pending_request() — iterate self, gọi rec._pending_requests() (đã
# stub trực tiếp trên rec giả, không cần patch.object cấp class vì method này
# không tự gọi self.<method_khác>, chỉ gọi rec.<method> của từng bản ghi).
# =============================================================================
class TestComputePendingRequest(unittest.TestCase):
    def test_has_pending_request(self):
        """TC-UNIT-DlPricingApprovalMatrix-026"""
        rec = SimpleNamespace(_pending_requests=lambda: ["REQ1"])
        DlPricingApprovalMatrix._compute_pending_request([rec])
        self.assertEqual(rec.pending_request_id, ["REQ1"])
        self.assertTrue(rec.has_pending_request)

    def test_no_pending_request(self):
        """TC-UNIT-DlPricingApprovalMatrix-027"""
        rec = SimpleNamespace(_pending_requests=lambda: [])
        DlPricingApprovalMatrix._compute_pending_request([rec])
        self.assertEqual(rec.pending_request_id, [])
        self.assertFalse(rec.has_pending_request)


if __name__ == "__main__":
    unittest.main()
