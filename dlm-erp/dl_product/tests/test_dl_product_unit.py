# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho product.product extension (dl_product),
PROD-02. Sheet nguồn: ProductProduct.

Chỉ test method thuần Python hoặc method chỉ cần self.env cho 1-2 lời gọi cụ thể
(đã fake qua _FakeEnv/_fields, cùng kỹ thuật đã dùng ở dl_sale/dl_config). Các method
create/write/_dlm_find_name_matches/_check_lifecycle_manager dùng self.search/
self.env.user.has_group với nhiều nhánh nên là L2, không test ở đây.
"""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError

from ..models.dl_product import ProductProduct


class _FakeEnv:
    """Cung cấp đúng 1 lookup mà _dlm_trading_blockers() cần:
    self.env['decimal.precision'].precision_get('Product Price')."""

    def __getitem__(self, key):
        if key == "decimal.precision":
            return SimpleNamespace(precision_get=lambda x: 2)
        raise KeyError(key)


_PRODUCT_KIND_FIELD = SimpleNamespace(
    get_description=lambda env: {"selection": [
        ("manufactured", "Sản phẩm gia công"), ("trading", "Sản phẩm thương mại"),
        ("material", "Vật tư"), ("material_processed", "Bán thành phẩm"),
    ]},
)


def _product(**kw):
    base = dict(product_kind="manufactured", categ_id=SimpleNamespace(dl_branch="other"),
                list_price=0.0, standard_price=0.0, default_code=False, env=_FakeEnv())
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec.ensure_one = lambda: rec
    rec.sudo = lambda: rec
    rec._fields = {"product_kind": _PRODUCT_KIND_FIELD}
    return rec


# _compute_dl_categ_branch() / _check_categ_branch()
class TestComputeDlCategBranch(unittest.TestCase):
    def test_manufactured_is_finished_branch(self):
        """TC-UNIT-ProductProduct-001: product_kind="manufactured" thì
        _compute_dl_categ_branch() gán dl_categ_branch = "finished"."""
        rec = SimpleNamespace(product_kind="manufactured")
        ProductProduct._compute_dl_categ_branch([rec])
        self.assertEqual(rec.dl_categ_branch, "finished")

    def test_trading_is_finished_branch(self):
        """TC-UNIT-ProductProduct-002: product_kind="trading" thì
        _compute_dl_categ_branch() gán dl_categ_branch = "finished"."""
        rec = SimpleNamespace(product_kind="trading")
        ProductProduct._compute_dl_categ_branch([rec])
        self.assertEqual(rec.dl_categ_branch, "finished")

    def test_material_is_material_branch(self):
        """TC-UNIT-ProductProduct-003: product_kind="material" thì
        _compute_dl_categ_branch() gán dl_categ_branch = "material"."""
        rec = SimpleNamespace(product_kind="material")
        ProductProduct._compute_dl_categ_branch([rec])
        self.assertEqual(rec.dl_categ_branch, "material")

    def test_material_processed_is_material_branch(self):
        """TC-UNIT-ProductProduct-004: product_kind="material_processed" thì
        _compute_dl_categ_branch() gán dl_categ_branch = "material"."""
        rec = SimpleNamespace(product_kind="material_processed")
        ProductProduct._compute_dl_categ_branch([rec])
        self.assertEqual(rec.dl_categ_branch, "material")


class TestCheckCategBranch(unittest.TestCase):
    def test_matching_branch_passes(self):
        """TC-UNIT-ProductProduct-005: dl_categ_branch của sản phẩm khớp với
        dl_branch của danh mục (đều "finished") thì _check_categ_branch()
        không báo lỗi."""
        rec = _product(product_kind="manufactured", dl_categ_branch="finished",
                       categ_id=SimpleNamespace(dl_branch="finished", display_name="Thành phẩm"))
        ProductProduct._check_categ_branch([rec])  # không raise

    def test_mismatched_branch_raises(self):
        """TC-UNIT-ProductProduct-006: dl_categ_branch của sản phẩm
        ("finished") lệch với dl_branch của danh mục ("material") thì
        _check_categ_branch() báo lỗi ValidationError."""
        rec = _product(product_kind="manufactured", dl_categ_branch="finished",
                       categ_id=SimpleNamespace(dl_branch="material", display_name="Vật tư kim loại"))
        with self.assertRaises(ValidationError):
            ProductProduct._check_categ_branch([rec])

    def test_other_branch_category_exempt(self):
        """TC-UNIT-ProductProduct-007: nhóm chưa phân nhánh (vd 'All' mặc định core)
        không bị chặn, coi như 'chưa phân nhóm'."""
        rec = _product(product_kind="manufactured", dl_categ_branch="finished",
                       categ_id=SimpleNamespace(dl_branch="other", display_name="All"))
        ProductProduct._check_categ_branch([rec])  # không raise


# _compute_dlm_sale_margin()
class TestComputeDlmSaleMargin(unittest.TestCase):
    def test_happy_margin(self):
        """TC-UNIT-ProductProduct-008: list_price=100000, standard_price=80000
        thì _compute_dlm_sale_margin() tính dlm_sale_margin = 20.0%."""
        rec = SimpleNamespace(list_price=100000.0, standard_price=80000.0)
        ProductProduct._compute_dlm_sale_margin([rec])
        self.assertEqual(rec.dlm_sale_margin, 20.0)

    def test_zero_list_price_is_zero_not_error(self):
        """TC-UNIT-ProductProduct-009: list_price=0 thì
        _compute_dlm_sale_margin() trả về dlm_sale_margin = 0.0 (không lỗi
        chia cho 0)."""
        rec = SimpleNamespace(list_price=0.0, standard_price=50000.0)
        ProductProduct._compute_dlm_sale_margin([rec])
        self.assertEqual(rec.dlm_sale_margin, 0.0)

    def test_zero_standard_price_is_100_percent(self):
        """TC-UNIT-ProductProduct-010: standard_price=0, list_price=100000
        thì _compute_dlm_sale_margin() tính dlm_sale_margin = 100.0%."""
        rec = SimpleNamespace(list_price=100000.0, standard_price=0.0)
        ProductProduct._compute_dlm_sale_margin([rec])
        self.assertEqual(rec.dlm_sale_margin, 100.0)


# _dlm_scrap_unit_price()
class TestDlmScrapUnitPrice(unittest.TestCase):
    def test_with_scrap_product(self):
        """TC-UNIT-ProductProduct-011: có dlm_scrap_product_id thì
        _dlm_scrap_unit_price() trả về list_price của sản phẩm phế liệu đó
        (15000.0)."""
        rec = _product(dlm_scrap_product_id=SimpleNamespace(list_price=15000.0))
        self.assertEqual(ProductProduct._dlm_scrap_unit_price(rec), 15000.0)

    def test_no_scrap_product_zero(self):
        """TC-UNIT-ProductProduct-012: không có dlm_scrap_product_id thì
        _dlm_scrap_unit_price() trả về 0.0."""
        rec = _product(dlm_scrap_product_id=None)
        self.assertEqual(ProductProduct._dlm_scrap_unit_price(rec), 0.0)


# _dlm_normalize_name()
class TestDlmNormalizeName(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self):
        """TC-UNIT-ProductProduct-013: chuỗi "  Khung  máy   ABC " nhiều
        khoảng trắng thừa và chữ hoa thì _dlm_normalize_name() chuẩn hóa về
        "khung máy abc" (gộp khoảng trắng, viết thường)."""
        rec = _product()
        self.assertEqual(ProductProduct._dlm_normalize_name(rec, "  Khung  máy   ABC "),
                          "khung máy abc")

    def test_preserves_vietnamese_diacritics(self):
        """TC-UNIT-ProductProduct-014: 'Khung máy ABC' và 'Khung may ABC' (thiếu dấu)
        không được coi là trùng nhau, theo chốt thiết kế."""
        rec = _product()
        self.assertNotEqual(
            ProductProduct._dlm_normalize_name(rec, "Khung máy ABC"),
            ProductProduct._dlm_normalize_name(rec, "Khung may ABC"))

    def test_empty_name_returns_empty_string(self):
        """TC-UNIT-ProductProduct-015: tên rỗng ("" hoặc False) thì
        _dlm_normalize_name() trả về chuỗi rỗng."""
        rec = _product()
        self.assertEqual(ProductProduct._dlm_normalize_name(rec, ""), "")
        self.assertEqual(ProductProduct._dlm_normalize_name(rec, False), "")


# _dlm_trading_blockers(): readiness engine kích hoạt SP thương mại.
class FakeSellerRS(list):
    """Mini stand-in cho recordset. Sau khi filtered()[:1] (như code thật làm), Odoo
    cho phép đọc field trực tiếp trên recordset 0/1 bản ghi (applied.approval_state,
    applied.price...); __getattr__ dưới đây mô phỏng đúng ngữ nghĩa đó."""

    def filtered(self, func):
        return FakeSellerRS(x for x in self if func(x))

    def __getitem__(self, item):
        if isinstance(item, slice):
            return FakeSellerRS(list.__getitem__(self, item))
        return list.__getitem__(self, item)

    def __getattr__(self, name):
        if len(self) == 1:
            return getattr(self[0], name)
        if len(self) == 0:
            return False
        raise AttributeError(name)


class TestDlmTradingBlockers(unittest.TestCase):
    _TODAY = date(2026, 8, 5)

    def test_no_applied_seller_only_reason(self):
        """TC-UNIT-ProductProduct-016: sản phẩm chưa có seller_ids nào thì
        _dlm_trading_blockers() trả về đúng 1 lý do nhắc nhập thông tin Mua
        hàng."""
        rec = _product(seller_ids=FakeSellerRS([]))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("Mua hàng", reasons[0])

    def test_applied_but_not_approved(self):
        """TC-UNIT-ProductProduct-017: seller đang áp dụng (is_applied=True)
        nhưng approval_state="draft" (chưa duyệt) thì
        _dlm_trading_blockers() trả về đúng 1 lý do là seller chưa được Mua
        hàng duyệt."""
        seller = SimpleNamespace(is_applied=True, approval_state="draft")
        rec = _product(seller_ids=FakeSellerRS([seller]))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("chưa được Mua hàng duyệt", reasons[0])

    def test_applied_expired(self):
        """TC-UNIT-ProductProduct-018: seller đã được duyệt nhưng
        _is_valid_on() trả về False (hết hiệu lực ở ngày hiện tại) thì
        _dlm_trading_blockers() trả về đúng 1 lý do liên quan hết hạn."""
        seller = SimpleNamespace(is_applied=True, approval_state="approved",
                                 _is_valid_on=lambda d: False)
        rec = _product(seller_ids=FakeSellerRS([seller]))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("hết hạn", reasons[0])

    def test_seller_partner_inactive(self):
        """TC-UNIT-ProductProduct-019: seller hợp lệ nhưng partner_id (nhà
        cung cấp) đã bị vô hiệu hóa (active=False) thì
        _dlm_trading_blockers() trả về đúng 1 lý do nhắc nhà cung cấp đã bị
        vô hiệu hóa."""
        seller = SimpleNamespace(is_applied=True, approval_state="approved",
                                 _is_valid_on=lambda d: True, price=100.0,
                                 partner_id=SimpleNamespace(active=False, display_name="NCC A"))
        rec = _product(seller_ids=FakeSellerRS([seller]))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("vô hiệu hóa", reasons[0])

    def test_cost_ready_but_no_list_price(self):
        """TC-UNIT-ProductProduct-020: giá vốn (standard_price=50000) đã sẵn
        sàng nhưng chưa nhập list_price (giá bán = 0) thì
        _dlm_trading_blockers() trả về đúng 1 lý do nhắc nhập Giá bán."""
        seller = SimpleNamespace(is_applied=True, approval_state="approved",
                                 _is_valid_on=lambda d: True, price=100.0,
                                 partner_id=SimpleNamespace(active=True))
        rec = _product(seller_ids=FakeSellerRS([seller]), standard_price=50000.0, list_price=0.0)
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("Chốt Giá bán", reasons[0])

    def test_list_price_below_standard_price_warns(self):
        """TC-UNIT-ProductProduct-021: list_price (40000) thấp hơn
        standard_price (50000) thì _dlm_trading_blockers() trả về đúng 1
        cảnh báo có chữ "CAO HƠN"."""
        seller = SimpleNamespace(is_applied=True, approval_state="approved",
                                 _is_valid_on=lambda d: True, price=100.0,
                                 partner_id=SimpleNamespace(active=True))
        rec = _product(seller_ids=FakeSellerRS([seller]), standard_price=50000.0, list_price=40000.0)
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(len(reasons), 1)
        self.assertIn("CAO HƠN", reasons[0])

    def test_fully_ready_no_blockers(self):
        """TC-UNIT-ProductProduct-022: seller đã duyệt, còn hiệu lực, nhà
        cung cấp active, list_price cao hơn standard_price thì
        _dlm_trading_blockers() trả về danh sách rỗng (không còn vướng mắc
        nào)."""
        seller = SimpleNamespace(is_applied=True, approval_state="approved",
                                 _is_valid_on=lambda d: True, price=100.0,
                                 partner_id=SimpleNamespace(active=True))
        rec = _product(seller_ids=FakeSellerRS([seller]), standard_price=50000.0, list_price=70000.0)
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            reasons = ProductProduct._dlm_trading_blockers(rec)
        self.assertEqual(reasons, [])


# _check_default_code(): chỉ test nhánh định dạng. Nhánh trùng mã dùng self.search
# nên là L2, không test ở đây.
class TestCheckDefaultCode(unittest.TestCase):
    def test_empty_code_skips(self):
        """TC-UNIT-ProductProduct-023: default_code để trống (False) thì
        _check_default_code() bỏ qua, không báo lỗi."""
        rec = _product(default_code=False)
        ProductProduct._check_default_code([rec])  # không raise

    def test_lowercase_letters_raise(self):
        """TC-UNIT-ProductProduct-024: default_code chứa chữ thường
        ("ct-200") sai định dạng thì _check_default_code() báo lỗi
        ValidationError."""
        rec = _product(default_code="ct-200")
        with self.assertRaises(ValidationError):
            ProductProduct._check_default_code([rec])


if __name__ == "__main__":
    unittest.main()
