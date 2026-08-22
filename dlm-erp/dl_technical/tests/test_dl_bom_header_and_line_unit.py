# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.header.mixin (dùng chung cho
dl.bom / dl.bom.template) và dl.bom.line. Sheet nguồn: DlBomHeaderMixin,
DlBomLine.

Chỉ test nhánh không đụng self.env/self.search/super().write thật:
action_confirm (đụng self.env.user) và _set_current_version/
action_create_new_version (đụng self.search/self.copy) là L2, không test ở
đây. write()/unlink() chỉ test được nhánh raise (trước khi chạm super()), vì
super().write() cần self là instance thật.

_compute_next_version() cũng đụng self.search(), nhưng có một khối tính toán
thuần (max(...)+1) đáng test riêng. Dùng kỹ thuật patch.object(Class,
"search"/"_version_domain"/"ensure_one", ...) kết hợp object.__new__(Class),
giống cách đã áp dụng cho DlPricingApprovalMatrix.evaluate_quotation() (xem
dl_config/tests/test_pricing_matrix_unit.py), để cô lập phần thuần khỏi
self.search. Bổ sung 2026-08-09 (FT-69 PRD §4.1), trước đó chưa có test L1."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError

from ..models.dl_bom import DlBom
from ..models.dl_bom_header_mixin import DlBomHeaderMixin
from ..models.dl_bom_line import DlBomLine


def _bom(**kw):
    base = dict(status="draft", is_current=False, _description="BOM")
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec._check_can_reset_draft = lambda: None  # hook mặc định no-op
    return rec


# action_lock() / action_archive(): state machine thuần, không đụng self.env.
class TestActionLock(unittest.TestCase):
    def test_confirmed_to_locked(self):
        """TC-UNIT-DlBomHeaderMixin-001: BOM ở trạng thái confirmed thì
        action_lock() chuyển sang locked."""
        rec = _bom(status="confirmed")
        DlBomHeaderMixin.action_lock([rec])
        self.assertEqual(rec.status, "locked")

    def test_draft_raises(self):
        """TC-UNIT-DlBomHeaderMixin-002: BOM ở trạng thái draft thì
        action_lock() báo lỗi UserError (chỉ khóa được từ confirmed)."""
        rec = _bom(status="draft")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_lock([rec])

    def test_already_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-003: BOM đã ở trạng thái locked thì
        action_lock() báo lỗi UserError (không khóa lại lần nữa)."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_lock([rec])


class TestActionArchive(unittest.TestCase):
    def test_locked_to_archived_clears_current_flag(self):
        """TC-UNIT-DlBomHeaderMixin-004: BOM locked với is_current=True thì
        action_archive() chuyển status sang archived và tắt cờ is_current."""
        rec = _bom(status="locked", is_current=True)
        DlBomHeaderMixin.action_archive([rec])
        self.assertEqual(rec.status, "archived")
        self.assertFalse(rec.is_current)

    def test_draft_can_also_be_archived(self):
        """TC-UNIT-DlBomHeaderMixin-005: không giới hạn trạng thái nguồn."""
        rec = _bom(status="draft")
        DlBomHeaderMixin.action_archive([rec])
        self.assertEqual(rec.status, "archived")


class TestActionResetDraft(unittest.TestCase):
    def test_confirmed_to_draft_clears_current_flag(self):
        """TC-UNIT-DlBomHeaderMixin-006: BOM confirmed với is_current=True thì
        action_reset_draft() chuyển status về draft và tắt cờ is_current."""
        rec = _bom(status="confirmed", is_current=True)
        DlBomHeaderMixin.action_reset_draft([rec])
        self.assertEqual(rec.status, "draft")
        self.assertFalse(rec.is_current)

    def test_draft_raises(self):
        """TC-UNIT-DlBomHeaderMixin-007: BOM đã ở trạng thái draft thì
        action_reset_draft() báo lỗi UserError."""
        rec = _bom(status="draft")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])

    def test_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-008: chỉ 'Đã xác nhận' mới được về Nháp."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])

    def test_check_can_reset_draft_hook_called(self):
        """TC-UNIT-DlBomHeaderMixin-009: hook chặn (ví dụ dl_sale override)
        phải được gọi trước khi đổi trạng thái."""
        rec = _bom(status="confirmed")
        called = []
        rec._check_can_reset_draft = lambda: called.append(True) or (_ for _ in ()).throw(
            UserError("BOM đã dùng cho báo giá đã chốt."))
        with self.assertRaises(UserError):
            DlBomHeaderMixin.action_reset_draft([rec])
        self.assertEqual(rec.status, "confirmed")  # không đổi vì hook chặn trước


class _FakeVersionRecordset:
    """Stand-in cho recordset trả về từ self.search(self._version_domain()).
    _compute_next_version() chỉ gọi .mapped('version') và kiểm tra truthy khi
    rỗng, không cần field/method nào khác."""

    def __init__(self, versions):
        self._versions = versions

    def mapped(self, field_name):
        assert field_name == "version"
        return self._versions

    def __bool__(self):
        return bool(self._versions)


def _next_version(existing_versions):
    fake_existing = _FakeVersionRecordset(existing_versions)
    with patch.object(DlBomHeaderMixin, "ensure_one", return_value=None), \
         patch.object(DlBomHeaderMixin, "_version_domain", return_value=[]), \
         patch.object(DlBomHeaderMixin, "search", return_value=fake_existing):
        rec = object.__new__(DlBomHeaderMixin)
        return rec._compute_next_version()


class TestComputeNextVersion(unittest.TestCase):
    def test_no_existing_version_starts_at_1(self):
        """TC-UNIT-DlBomHeaderMixin-013: chưa có version nào tồn tại thì
        _compute_next_version() trả về 1."""
        self.assertEqual(_next_version([]), 1)

    def test_existing_versions_returns_max_plus_1(self):
        """TC-UNIT-DlBomHeaderMixin-014: đã có các version [1, 2, 3] thì
        _compute_next_version() trả về max + 1 = 4."""
        self.assertEqual(_next_version([1, 2, 3]), 4)

    def test_single_existing_version(self):
        """TC-UNIT-DlBomHeaderMixin-015: chỉ có một version hiện có (5) thì
        _compute_next_version() trả về 6."""
        self.assertEqual(_next_version([5]), 6)

    def test_non_sequential_versions_uses_max_not_count(self):
        """TC-UNIT-DlBomHeaderMixin-016: phiên bản ở giữa có thể đã bị xóa
        hoặc không tồn tại (ví dụ dữ liệu cũ). Công thức phải lấy max(...)+1,
        không phải count(...)+1, để không sinh trùng version đã có."""
        self.assertEqual(_next_version([1, 3, 7]), 8)


class TestWriteGuard(unittest.TestCase):
    """Chỉ test nhánh raise (trước khi chạm super().write), vì self phải là
    instance thật mới an toàn gọi super()."""

    def test_locked_business_field_raises(self):
        """TC-UNIT-DlBomHeaderMixin-010: BOM locked mà ghi field nghiệp vụ
        product_qty thì write() báo lỗi UserError."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.write([rec], {"product_qty": 5.0})

    def test_locked_multiple_business_fields_raises(self):
        """TC-UNIT-DlBomHeaderMixin-011: BOM locked mà ghi đồng thời nhiều
        field nghiệp vụ (product_qty, version) thì write() vẫn báo lỗi
        UserError."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.write([rec], {"product_qty": 5.0, "version": 2})


class TestUnlinkGuard(unittest.TestCase):
    def test_locked_raises(self):
        """TC-UNIT-DlBomHeaderMixin-012: BOM ở trạng thái locked thì
        unlink() báo lỗi UserError."""
        rec = _bom(status="locked")
        with self.assertRaises(UserError):
            DlBomHeaderMixin.unlink([rec])


# dl.bom.line: compute thuần (nhánh vật tư thô). Nhánh material_processed
# đụng self.env nên không test ở đây, cùng quy ước với quotation_pricing_service.
class FakeSellers(list):
    def filtered(self, key):
        if callable(key):
            return FakeSellers(x for x in self if key(x))
        return FakeSellers(x for x in self if getattr(x, key))


class TestComputePriceSnapshot(unittest.TestCase):
    def test_raw_material_uses_applied_seller_price(self):
        """TC-UNIT-DlBomLine-001: vật tư thô (product_kind=material) có
        seller đang áp dụng giá (is_applied=True, price=50000) thì
        price_snapshot lấy đúng giá của seller đó."""
        seller = SimpleNamespace(is_applied=True, price=50000.0)
        material = SimpleNamespace(product_kind="material",
                                    seller_ids=FakeSellers([seller]))
        rec = SimpleNamespace(material_id=material)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 50000.0)

    def test_raw_material_no_applied_seller_zero(self):
        """TC-UNIT-DlBomLine-002: vật tư thô không có seller nào đang áp
        dụng giá (seller_ids rỗng) thì price_snapshot = 0.0."""
        material = SimpleNamespace(product_kind="material", seller_ids=FakeSellers([]))
        rec = SimpleNamespace(material_id=material)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 0.0)

    def test_no_material_zero(self):
        """TC-UNIT-DlBomLine-003: dòng BOM không có vật tư (material_id=None)
        thì price_snapshot = 0.0."""
        rec = SimpleNamespace(material_id=None)
        DlBomLine._compute_price_snapshot([rec])
        self.assertEqual(rec.price_snapshot, 0.0)


class TestComputeRecoveryValue(unittest.TestCase):
    def test_delegates_to_dlm_recovery_value(self):
        """TC-UNIT-DlBomLine-004: _compute_recovery_value() chỉ ủy quyền
        thẳng cho _dlm_recovery_value() của dòng (mock trả về 20.0), lấy
        đúng giá trị đó gán vào recovery_value."""
        rec = SimpleNamespace(_dlm_recovery_value=lambda: 20.0)
        DlBomLine._compute_recovery_value([rec])
        self.assertEqual(rec.recovery_value, 20.0)


class TestComputeSubtotal(unittest.TestCase):
    def test_happy(self):
        """TC-UNIT-DlBomLine-005: effective_qty=10, price_snapshot=500,
        recovery_value=100 thì subtotal = 10*500 - 100 = 4900."""
        rec = SimpleNamespace(effective_qty=10.0, price_snapshot=500.0, recovery_value=100.0)
        DlBomLine._compute_subtotal([rec])
        self.assertEqual(rec.subtotal, 4900.0)

    def test_zero_recovery(self):
        """TC-UNIT-DlBomLine-006: recovery_value=0 (không thu hồi) thì
        subtotal = 10*500 - 0 = 5000, bằng đúng effective_qty * price_snapshot."""
        rec = SimpleNamespace(effective_qty=10.0, price_snapshot=500.0, recovery_value=0.0)
        DlBomLine._compute_subtotal([rec])
        self.assertEqual(rec.subtotal, 5000.0)


# dl.bom (không phải mixin, nhưng constraint nằm ở đây theo tên sheet gốc):
# _check_product_qty() / _check_product_not_obsolete().
class TestCheckProductQty(unittest.TestCase):
    def test_zero_raises(self):
        """TC-UNIT-DlBomHeaderMixin-020: product_qty=0 (biên dưới) thì
        _check_product_qty() báo lỗi ValidationError."""
        rec = SimpleNamespace(product_qty=0.0)
        with self.assertRaises(ValidationError):
            DlBom._check_product_qty([rec])

    def test_negative_raises(self):
        """product_qty âm (-5) thì cũng báo lỗi ValidationError."""
        rec = SimpleNamespace(product_qty=-5.0)
        with self.assertRaises(ValidationError):
            DlBom._check_product_qty([rec])

    def test_positive_passes(self):
        """product_qty dương (10) thì không báo lỗi."""
        rec = SimpleNamespace(product_qty=10.0)
        DlBom._check_product_qty([rec])  # không raise


class TestCheckProductNotObsolete(unittest.TestCase):
    def test_obsolete_product_raises(self):
        """TC-UNIT-DlBomHeaderMixin-019: sản phẩm ở trạng thái Ngừng
        (dlm_lifecycle_state='obsolete') thì _check_product_not_obsolete()
        báo lỗi ValidationError."""
        product = SimpleNamespace(dlm_lifecycle_state="obsolete", display_name="Ghế thép")
        rec = SimpleNamespace(product_id=product)
        with self.assertRaises(ValidationError):
            DlBom._check_product_not_obsolete([rec])

    def test_active_product_passes(self):
        """Sản phẩm chưa Ngừng (dlm_lifecycle_state='active') thì không báo lỗi."""
        product = SimpleNamespace(dlm_lifecycle_state="active", display_name="Ghế thép")
        rec = SimpleNamespace(product_id=product)
        DlBom._check_product_not_obsolete([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
