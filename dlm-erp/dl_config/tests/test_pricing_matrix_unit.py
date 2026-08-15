"""Unit test L1 (thuần, không ORM/DB) cho dl.pricing.approval.matrix.
Sheet nguồn: DlPricingApprovalMatrix trong Report_5_1_UnitTests_L1.xlsx.

Chỉ test phần thuần Python của evaluate_quotation() (Approval Rule Engine).
_resolve_value_row() gọi self.search(...) nên được stub qua patch.object ở
cấp class. Phải patch class thay vì gán trực tiếp lên instance vì
DlPricingApprovalMatrix là models.Model dùng __slots__, không gán được thuộc
tính lên instance thường.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.pricing_matrix import DlPricingApprovalMatrix


class _FakeRow:
    """Stand-in cho recordset trả về từ _resolve_value_row()/self.browse().

    present=False mô phỏng recordset rỗng (falsy, không có dòng nào khớp
    ngưỡng). evaluate_quotation() chỉ đọc field khi row truthy nên các case
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
    patch ở cấp class. Company truyền vào phải truthy để tránh code chạm
    self.env.company (company or self.env.company)."""
    with patch.object(DlPricingApprovalMatrix, "browse", return_value=_EMPTY_ROW), \
         patch.object(DlPricingApprovalMatrix, "_resolve_value_row", return_value=row):
        matrix = object.__new__(DlPricingApprovalMatrix)
        return matrix.evaluate_quotation(
            25_000_000, company=SimpleNamespace(id=1), date=None, **flags)


class TestEvaluateQuotation(unittest.TestCase):
    def test_value_axis_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-001: chỉ trục giá trị (dòng ma trận khớp
        ngưỡng) kích hoạt, không kèm cờ discount/below_floor nào, thì
        evaluate_quotation() yêu cầu duyệt đúng theo cấp và thông tin của dòng ma
        trận đó."""
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
        """TC-UNIT-DlPricingApprovalMatrix-002: dòng ma trận khớp ngưỡng giá trị
        nhưng approval_level=none (rank 0) thì không tính là ứng viên cần duyệt,
        required=False."""
        row = _FakeRow(level_rank=0, approval_level="none", id=5, revision=1)
        result = _evaluate(row, discount_above_default=False,
                            discount_above_max=False, below_floor=False)
        self.assertFalse(result["required"])

    def test_discount_above_default_only_no_longer_triggers(self):
        """TC-UNIT-DlPricingApprovalMatrix-003: mức "Mặc định" chỉ còn là gợi ý tự
        điền, không còn kích hoạt duyệt nữa (chốt 2026-07-27, xem comment mục B
        trong evaluate_quotation). Tham số discount_above_default vẫn nhận để
        tương thích chữ ký hàm nhưng không tạo candidate nào nữa."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=True,
                            discount_above_max=False, below_floor=False)
        self.assertFalse(result["required"])

    def test_discount_above_max_and_below_floor_take_max_rank(self):
        """TC-UNIT-DlPricingApprovalMatrix-004: chốt 2026-07-27, vượt mức tối đa một
        mình chỉ cần Trưởng KD duyệt (rank 1, xem TC-008). Nếu đồng thời
        below_floor xảy ra (rank 2, CEO) thì CEO thắng theo rank cao nhất, nhưng
        reasons vẫn giữ đủ cả 2 lý do."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=True, below_floor=True)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(len(result["reasons"]), 2)

    def test_below_floor_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-005: chỉ trục below_floor (giá dưới sàn)
        kích hoạt, không kèm trục nào khác, thì yêu cầu duyệt ở cấp Giám đốc
        (rank 2) với đúng 1 lý do."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=False, below_floor=True)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "ceo")
        self.assertEqual(result["rank"], 2)
        self.assertEqual(len(result["reasons"]), 1)

    def test_multiple_axes_take_max_rank_but_merge_all_reasons(self):
        """TC-UNIT-DlPricingApprovalMatrix-006: vừa khớp ngưỡng giá trị (rank 1) vừa
        vi phạm below_floor (rank 2) thì cấp duyệt lấy theo rank cao nhất (ceo),
        nhưng reasons vẫn gộp đủ lý do của cả 2 trục."""
        row = _FakeRow(level_rank=1, approval_level="sales_manager", id=1, revision=1)
        result = _evaluate(row, discount_above_default=False,
                            discount_above_max=False, below_floor=True)
        self.assertEqual(result["level"], "ceo")  # rank cao nhất thắng
        self.assertEqual(result["rank"], 2)
        # reasons gồm cả lý do giá trị lẫn lý do giá sàn, không chỉ của "ceo"
        self.assertEqual(len(result["reasons"]), 2)

    def test_no_axis_fires(self):
        """TC-UNIT-DlPricingApprovalMatrix-007: không trục nào (giá trị, mặc định,
        vượt tối đa, dưới sàn) kích hoạt thì evaluate_quotation() trả về dict mặc
        định, required=False và toàn bộ field còn lại rỗng."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=False, below_floor=False)
        self.assertEqual(result, {
            "required": False, "level": False, "level_label": "",
            "rank": 0, "matrix_row_id": False, "matrix_revision": False,
            "reasons": [],
        })

    def test_discount_above_max_only(self):
        """TC-UNIT-DlPricingApprovalMatrix-008: chốt 2026-07-27, vượt mức tối đa của
        nhóm khách (Sales tự quyết được tới mức tối đa, vượt mới cần duyệt) chỉ
        cần Trưởng KD duyệt ngoại lệ, không cần lên CEO."""
        result = _evaluate(_EMPTY_ROW, discount_above_default=False,
                            discount_above_max=True, below_floor=False)
        self.assertTrue(result["required"])
        self.assertEqual(result["level"], "sales_manager")
        self.assertEqual(result["rank"], 1)
        self.assertEqual(len(result["reasons"]), 1)


_VND = SimpleNamespace(symbol="₫")


# _compute_name(): thuần Python, chỉ đọc field và gọi _fmt_money() (module-level).
class TestComputeName(unittest.TestCase):
    def test_happy_format(self):
        """TC-UNIT-DlPricingApprovalMatrix-009: _compute_name() ghép value_from, tên
        cấp duyệt và số revision thành field name đúng định dạng cho trường hợp
        sales_manager, revision 1."""
        rec = SimpleNamespace(value_from=20_000_000, approval_level="sales_manager",
                               revision=1, currency_id=_VND)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 20.000.000 ₫ → Trưởng kinh doanh (b1)")

    def test_ceo_level_and_revision_2(self):
        """TC-UNIT-DlPricingApprovalMatrix-010: _compute_name() với
        approval_level=ceo và revision=2 trả về đúng nhãn cấp Giám đốc và số
        revision b2."""
        rec = SimpleNamespace(value_from=100_000_000, approval_level="ceo",
                               revision=2, currency_id=_VND)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 100.000.000 ₫ → Giám đốc (b2)")

    def test_no_currency_no_symbol_suffix(self):
        """TC-UNIT-DlPricingApprovalMatrix-011: khi currency_id rỗng, _compute_name()
        không thêm ký hiệu tiền tệ vào field name, và approval_level=none hiển thị
        nhãn "Không cần duyệt"."""
        rec = SimpleNamespace(value_from=5000, approval_level="none",
                               revision=1, currency_id=False)
        DlPricingApprovalMatrix._compute_name([rec])
        self.assertEqual(rec.name, "Từ 5.000 → Không cần duyệt (b1)")


# _compute_level_rank(): ánh xạ approval_level sang rank qua _LEVEL_RANK.
class TestComputeLevelRank(unittest.TestCase):
    def test_none_is_zero(self):
        """TC-UNIT-DlPricingApprovalMatrix-012: _compute_level_rank() ánh xạ
        approval_level=none sang level_rank=0."""
        rec = SimpleNamespace(approval_level="none")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 0)

    def test_sales_manager_is_one(self):
        """TC-UNIT-DlPricingApprovalMatrix-013: _compute_level_rank() ánh xạ
        approval_level=sales_manager sang level_rank=1."""
        rec = SimpleNamespace(approval_level="sales_manager")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 1)

    def test_ceo_is_two(self):
        """TC-UNIT-DlPricingApprovalMatrix-014: _compute_level_rank() ánh xạ
        approval_level=ceo sang level_rank=2."""
        rec = SimpleNamespace(approval_level="ceo")
        DlPricingApprovalMatrix._compute_level_rank([rec])
        self.assertEqual(rec.level_rank, 2)


# _check_value_from(): constraint thuần, chỉ so sánh value_from < 0.
class TestCheckValueFrom(unittest.TestCase):
    def test_negative_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-015: _check_value_from() với value_from âm
        (-1) thì báo lỗi ValidationError."""
        rec = SimpleNamespace(value_from=-1)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._check_value_from([rec])

    def test_zero_boundary_passes(self):
        """TC-UNIT-DlPricingApprovalMatrix-016: _check_value_from() với
        value_from=0 (biên dưới) không raise, hợp lệ."""
        rec = SimpleNamespace(value_from=0)
        DlPricingApprovalMatrix._check_value_from([rec])  # không raise

    def test_positive_passes(self):
        """TC-UNIT-DlPricingApprovalMatrix-017: _check_value_from() với value_from
        dương (20 triệu) không raise, hợp lệ."""
        rec = SimpleNamespace(value_from=20_000_000)
        DlPricingApprovalMatrix._check_value_from([rec])  # không raise


# _diff_label(): gọi self.ensure_one() rồi đọc field trực tiếp, không đụng env.
class _MatrixRow(SimpleNamespace):
    def ensure_one(self):
        return self


class TestDiffLabel(unittest.TestCase):
    def test_without_specific_approver(self):
        """TC-UNIT-DlPricingApprovalMatrix-018: _diff_label() khi record không có
        approver_user_id cụ thể thì nhãn chỉ gồm ngưỡng giá trị và tên cấp duyệt,
        không có phần người duyệt."""
        rec = _MatrixRow(value_from=20_000_000, approval_level="sales_manager",
                          currency_id=_VND, approver_user_id=None)
        self.assertEqual(DlPricingApprovalMatrix._diff_label(rec),
                          "Ngưỡng 20.000.000 ₫ — Trưởng kinh doanh")

    def test_with_specific_approver_appends_name(self):
        """TC-UNIT-DlPricingApprovalMatrix-019: _diff_label() khi record có
        approver_user_id cụ thể thì nhãn có thêm phần tên người duyệt sau cấp
        duyệt."""
        approver = SimpleNamespace(name="Nguyễn Văn A")
        rec = _MatrixRow(value_from=20_000_000, approval_level="sales_manager",
                          currency_id=_VND, approver_user_id=approver)
        self.assertEqual(DlPricingApprovalMatrix._diff_label(rec),
                          "Ngưỡng 20.000.000 ₫ — Trưởng kinh doanh, người duyệt: Nguyễn Văn A")


# _change_summary(old): so sánh self với old, liệt kê đúng phần đã đổi.
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
        """TC-UNIT-DlPricingApprovalMatrix-020: _change_summary() khi old=None (chưa
        có bản ghi cũ để so sánh) trả về thông báo là ngưỡng mới được thêm vào
        thang phê duyệt."""
        rec = self._row()
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, None),
                          "Thêm ngưỡng mới vào thang phê duyệt")

    def test_identical_means_no_change(self):
        """TC-UNIT-DlPricingApprovalMatrix-021: _change_summary() khi rec và old
        giống hệt nhau thì trả về thông báo không có thay đổi nội dung chính."""
        rec = self._row()
        old = self._row()
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, old),
                          "Không thay đổi nội dung chính")

    def test_value_from_changed(self):
        """TC-UNIT-DlPricingApprovalMatrix-022: _change_summary() khi chỉ value_from
        đổi (20tr thành 50tr) thì trả về đúng dòng mô tả thay đổi ngưỡng."""
        rec = self._row(value_from=50_000_000)
        old = self._row(value_from=20_000_000)
        self.assertEqual(DlPricingApprovalMatrix._change_summary(rec, old),
                          "Ngưỡng: 20.000.000 ₫ → 50.000.000 ₫")

    def test_level_and_approver_changed_joined(self):
        """TC-UNIT-DlPricingApprovalMatrix-023: _change_summary() khi cả
        approval_level và approver_user_id đều đổi thì gộp 2 dòng mô tả thay đổi,
        nối nhau bằng dấu chấm phẩy."""
        approver = SimpleNamespace(name="Trần Thị B")
        rec = self._row(approval_level="ceo", approver=approver)
        old = self._row(approval_level="sales_manager", approver=_NO_APPROVER)
        summary = DlPricingApprovalMatrix._change_summary(rec, old)
        self.assertIn("Cấp duyệt: Trưởng kinh doanh → Giám đốc", summary)
        self.assertIn("Người duyệt cụ thể: (theo vai trò) → Trần Thị B", summary)
        self.assertEqual(summary.count(";"), 1)  # đúng 2 phần đổi, nối bằng "; "


# _allowed_user_ids(): chỉ test 2 nhánh không đụng self.env.ref(...). Nhánh
# "theo vai trò" (group lookup qua env.ref) thuộc L2, không test ở đây.
class TestAllowedUserIds(unittest.TestCase):
    def test_none_level_returns_empty(self):
        """TC-UNIT-DlPricingApprovalMatrix-024: _allowed_user_ids() khi
        approval_level=none thì trả về danh sách rỗng, không ai được duyệt."""
        rec = _MatrixRow(approval_level="none", approver_user_id=None)
        self.assertEqual(DlPricingApprovalMatrix._allowed_user_ids(rec), [])

    def test_specific_approver_returns_its_ids(self):
        """TC-UNIT-DlPricingApprovalMatrix-025: _allowed_user_ids() khi có
        approver_user_id cụ thể thì trả về đúng id của người đó."""
        approver = SimpleNamespace(ids=[7])
        rec = _MatrixRow(approval_level="sales_manager", approver_user_id=approver)
        self.assertEqual(DlPricingApprovalMatrix._allowed_user_ids(rec), [7])


# _compute_pending_request(): duyệt qua self, gọi rec._pending_requests() đã
# stub trực tiếp trên rec giả. Không cần patch.object cấp class vì method này
# không tự gọi self.<method khác>, chỉ gọi rec.<method> của từng bản ghi.
class TestComputePendingRequest(unittest.TestCase):
    def test_has_pending_request(self):
        """TC-UNIT-DlPricingApprovalMatrix-026: _compute_pending_request() khi rec có
        pending request thì gán đúng pending_request_id và
        has_pending_request=True."""
        rec = SimpleNamespace(_pending_requests=lambda: ["REQ1"])
        DlPricingApprovalMatrix._compute_pending_request([rec])
        self.assertEqual(rec.pending_request_id, ["REQ1"])
        self.assertTrue(rec.has_pending_request)

    def test_no_pending_request(self):
        """TC-UNIT-DlPricingApprovalMatrix-027: _compute_pending_request() khi rec
        không có pending request nào thì pending_request_id rỗng và
        has_pending_request=False."""
        rec = SimpleNamespace(_pending_requests=lambda: [])
        DlPricingApprovalMatrix._compute_pending_request([rec])
        self.assertEqual(rec.pending_request_id, [])
        self.assertFalse(rec.has_pending_request)


# _check_approver_in_role() / _check_unique_threshold(): cả 2 chạm self.env
# (ref/search) nên self truyền vào cần vừa lặp được (for rec in self) vừa có
# .env. Dùng _RecordsetStub (list con) thay vì SimpleNamespace/object.__new__.
class _RecordsetStub(list):
    """list con mang thêm .env, để self thật vừa lặp được (for rec in self)
    vừa cho self.env.<method> hoạt động, không cần patch.object cấp class."""

    def __init__(self, records, env):
        super().__init__(records)
        self.env = env


class TestCheckApproverInRole(unittest.TestCase):
    def test_approver_not_in_role_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-028: _check_approver_in_role() khi
        approver_user_id được gán nhưng không thuộc nhóm vai trò tương ứng với
        approval_level thì báo lỗi ValidationError."""
        approver = SimpleNamespace(name="Nguyễn Văn A")
        other_user = SimpleNamespace(name="Người khác")
        group = SimpleNamespace(users=[other_user])
        rec = SimpleNamespace(approver_user_id=approver, approval_level="ceo")
        env = SimpleNamespace(ref=lambda *a, **kw: group)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._check_approver_in_role(_RecordsetStub([rec], env))

    def test_approver_in_role_passes(self):
        """approver_user_id thuộc đúng nhóm vai trò của approval_level thì
        _check_approver_in_role() không raise."""
        approver = SimpleNamespace(name="Nguyễn Văn A")
        group = SimpleNamespace(users=[approver])
        rec = SimpleNamespace(approver_user_id=approver, approval_level="ceo")
        env = SimpleNamespace(ref=lambda *a, **kw: group)
        DlPricingApprovalMatrix._check_approver_in_role(_RecordsetStub([rec], env))

    def test_no_approver_user_id_skips(self):
        """approver_user_id rỗng (không gán người duyệt cụ thể) thì
        _check_approver_in_role() bỏ qua kiểm tra, không gọi self.env.ref()."""
        rec = SimpleNamespace(approver_user_id=False, approval_level="ceo")
        env = SimpleNamespace(ref=lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("env.ref should not be called")))
        DlPricingApprovalMatrix._check_approver_in_role(_RecordsetStub([rec], env))


class TestCheckUniqueThreshold(unittest.TestCase):
    def test_duplicate_active_threshold_same_company_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-029: _check_unique_threshold() khi đã có
        bản ghi active khác cùng company và cùng ngưỡng giá trị (value_from) thì
        báo lỗi ValidationError trùng ngưỡng."""
        rec = SimpleNamespace(id=1, state="active", company_id=SimpleNamespace(id=1),
                               value_from=5_000_000.0, currency_id=False)
        env = SimpleNamespace()
        stub = _RecordsetStub([rec], env)
        stub.search = lambda domain, limit=None: [SimpleNamespace(id=2)]  # "twin"
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._check_unique_threshold(stub)

    def test_no_duplicate_passes(self):
        """search() không tìm thấy bản ghi active nào trùng ngưỡng thì
        _check_unique_threshold() không raise."""
        rec = SimpleNamespace(id=1, state="active", company_id=SimpleNamespace(id=1),
                               value_from=5_000_000.0, currency_id=False)
        env = SimpleNamespace()
        stub = _RecordsetStub([rec], env)
        stub.search = lambda domain, limit=None: []
        DlPricingApprovalMatrix._check_unique_threshold(stub)

    def test_draft_state_skips_check(self):
        """rec ở trạng thái draft (chưa active) thì _check_unique_threshold() bỏ qua
        kiểm tra trùng ngưỡng, không gọi search()."""
        rec = SimpleNamespace(id=1, state="draft", company_id=SimpleNamespace(id=1),
                               value_from=5_000_000.0)
        env = SimpleNamespace()
        stub = _RecordsetStub([rec], env)
        stub.search = lambda domain: (_ for _ in ()).throw(
            AssertionError("search should not run for non-active state"))
        DlPricingApprovalMatrix._check_unique_threshold(stub)


# _assert_fits_ladder(): self đóng vai trò 1 bản ghi đã ensure_one() (không
# phải recordset nhiều dòng), cần .search()/.ids/.revised_from_id/.company_id/
# .value_from/.level_rank/.currency_id, nên dùng _LadderRow tự chế.
class _LadderRow:
    def __init__(self, value_from, level_rank, approval_level="ceo", others=None):
        self.value_from = value_from
        self.level_rank = level_rank
        self.approval_level = approval_level
        self.currency_id = False
        self.ids = [1]
        self.revised_from_id = SimpleNamespace(ids=[])
        self.company_id = SimpleNamespace(id=1)
        self._others = others or []

    def ensure_one(self):
        return self

    def search(self, domain):
        return self._others


class TestAssertFitsLadder(unittest.TestCase):
    def test_rank_inversion_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-030: ngưỡng thấp (2tr) đòi cấp cao (ceo,
        rank2) trong khi ngưỡng cao hơn (10tr) chỉ cần cấp thấp (sales_manager,
        rank1). Đây là nghịch lý nên phải chặn."""
        other = SimpleNamespace(value_from=10_000_000.0, level_rank=1,
                                 approval_level="sales_manager", currency_id=False)
        row = _LadderRow(value_from=2_000_000.0, level_rank=2, others=[other])
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._assert_fits_ladder(row)

    def test_duplicate_rank_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-031: 2 ngưỡng khác nhau cùng đòi cùng 1
        cấp duyệt (rank trùng), thừa nên phải chặn."""
        other = SimpleNamespace(value_from=5_000_000.0, level_rank=1,
                                 approval_level="sales_manager", currency_id=False)
        row = _LadderRow(value_from=2_000_000.0, level_rank=1,
                          approval_level="sales_manager", others=[other])
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix._assert_fits_ladder(row)

    def test_ascending_ladder_passes(self):
        """thang ngưỡng tăng dần đúng thứ tự (ngưỡng thấp hơn đòi cấp duyệt thấp
        hơn hoặc bằng) thì _assert_fits_ladder() không raise."""
        other = SimpleNamespace(value_from=10_000_000.0, level_rank=2,
                                 approval_level="ceo", currency_id=False)
        row = _LadderRow(value_from=2_000_000.0, level_rank=1,
                          approval_level="sales_manager", others=[other])
        DlPricingApprovalMatrix._assert_fits_ladder(row)  # không raise


# action_apply(): 4 nhánh raise sớm, trước khi chạm super().action_apply().
# Tự chế self đủ ._is_matrix_manager() / lặp được / self.env.uid, su.
class _ApplyRow:
    def __init__(self, approval_level="ceo", approver_user_id=None, revision=1,
                 change_reason=False, env_uid=1, env_su=False, is_manager=True):
        self.approval_level = approval_level
        self.approver_user_id = approver_user_id or SimpleNamespace(id=0)
        self.revision = revision
        self.change_reason = change_reason
        self.env = SimpleNamespace(uid=env_uid, su=env_su)
        self._is_manager = is_manager

    def _is_matrix_manager(self):
        return self._is_manager

    def __iter__(self):
        return iter([self])


class TestActionApply(unittest.TestCase):
    def test_non_manager_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-032: action_apply() khi người gọi không
        phải matrix manager (_is_matrix_manager()=False) thì báo lỗi
        AccessError."""
        rec = _ApplyRow(is_manager=False)
        with self.assertRaises(AccessError):
            DlPricingApprovalMatrix.action_apply(rec)

    def test_missing_approval_level_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-033: action_apply() khi approval_level
        chưa được chọn (rỗng) thì báo lỗi ValidationError."""
        rec = _ApplyRow(is_manager=True, approval_level=False)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix.action_apply(rec)

    def test_self_activation_blocked(self):
        """TC-UNIT-DlPricingApprovalMatrix-034: action_apply() khi người kích hoạt
        (env.uid) trùng với approver_user_id của chính dòng ma trận đó (tự kích
        hoạt cho mình) thì báo lỗi ValidationError."""
        rec = _ApplyRow(is_manager=True, approval_level="ceo",
                         approver_user_id=SimpleNamespace(id=5),
                         env_uid=5, env_su=False)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix.action_apply(rec)

    def test_revision_without_reason_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-035: action_apply() khi revision > 1 (đã
        có sửa đổi trước đó) nhưng change_reason còn rỗng thì báo lỗi
        ValidationError."""
        rec = _ApplyRow(is_manager=True, approval_level="ceo", revision=2,
                         change_reason=False)
        with self.assertRaises(ValidationError):
            DlPricingApprovalMatrix.action_apply(rec)


# action_submit_approval(): chỉ nhánh raise sớm (state != draft), trước khi
# chạm self._assert_fits_ladder()/self.env.
class _SubmitRow:
    def __init__(self, state="draft"):
        self.state = state
        self.env = {"dl.pricing.approval.request": None}

    def ensure_one(self):
        return self

    def __iter__(self):
        return iter([self])


class TestActionSubmitApproval(unittest.TestCase):
    def test_non_draft_raises(self):
        """TC-UNIT-DlPricingApprovalMatrix-036: action_submit_approval() khi dòng ma
        trận không còn ở trạng thái draft thì báo lỗi UserError."""
        rec = _SubmitRow(state="active")
        with self.assertRaises(UserError):
            DlPricingApprovalMatrix.action_submit_approval(rec)


if __name__ == "__main__":
    unittest.main()
