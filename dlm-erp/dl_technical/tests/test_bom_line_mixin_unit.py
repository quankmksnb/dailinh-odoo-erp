"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.line.mixin. Sheet nguồn:
DlBomLineMixin trong Report_5_1_UnitTests_L1.xlsx.

Viết lại 2026-08-11: bản trước viết cho hệ 17 công thức hình dạng
(dl.measurement.* / _measurement_quantity()) đã hỏng từ commit 11bff9f
(2026-08-09), vì cơ chế Shape/Rule đó đã bị gỡ khỏi dl_bom_line_mixin.py và
thay bằng hệ 5 ca theo material_id.dlm_calc_kind kết hợp nhóm ĐVT của vật tư
(xem test_material_calc_kind.py, sheet TestMaterialCalcKind trong Report 5.2,
test tích hợp cho _dlm_auto_quantity()/_dlm_recovery_value() với vật tư
thật). File cũ còn import một tên model đã bị xóa nên ImportError chặn luôn
cả module dl_technical, không chỉ file test này.

Bản viết lại này chỉ giữ/khôi phục các method có thể cô lập khỏi self.env
(không dùng self.search/self.write thật): _onchange_material_waste(),
_dlm_recovery_value() (nhánh mock bằng SimpleNamespace cho _dlm_uom_group()),
_compute_effective_qty(), _compute_uom(), _compute_computed_quantity() (nay
delegate qua _dlm_auto_quantity(), mock vật tư đủ field để test nhánh
cut_length/None), _check_quantity(), _check_piece_count() (constraint mới
thêm 2026-08-09, trước đó chưa có test). Nhánh chi tiết đầy đủ của
_dlm_auto_quantity()/_dlm_recovery_value() với dữ liệu Odoo thật (5 ca,
mm-m, thu hồi phế liệu quy đổi) đã có ở test_material_calc_kind.py, không
lặp lại ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_bom_line_mixin import DlBomLineMixin


class _FakeBomLine:
    """Stand-in thuần Python cho 1 dòng BOM: set đúng field mà các method
    thật cần đọc/ghi, mượn thẳng method thật từ DlBomLineMixin."""

    _onchange_material_waste = DlBomLineMixin._onchange_material_waste
    _dlm_recovery_value = DlBomLineMixin._dlm_recovery_value

    def __init__(self, **kwargs):
        self.quantity = 1.0
        self.piece_count = 1
        self.dim_length = 0.0
        self.dim_width = 0.0
        self.is_override = False
        self.waste_rate = 0.0
        self.effective_qty = 0.0
        self.material_id = None
        self.complexity_id = None
        self.uom_id = None
        self.__dict__.update(kwargs)

    def ensure_one(self):
        return self


# _onchange_material_waste(): % hao hụt = hao hụt cơ sở vật tư × hệ số phức tạp
class TestOnchangeMaterialWaste(unittest.TestCase):
    def test_material_and_complexity_set(self):
        """TC-UNIT-DlBomLineMixin-031: có cả vật tư (dlm_waste_rate=5) lẫn hệ
        số phức tạp (factor=1.5) thì waste_rate = 5 * 1.5 = 7.5."""
        material = SimpleNamespace(dlm_waste_rate=5.0)
        complexity = SimpleNamespace(factor=1.5)
        line = _FakeBomLine(material_id=material, complexity_id=complexity)
        line._onchange_material_waste()
        self.assertAlmostEqual(line.waste_rate, 7.5)

    def test_material_set_no_complexity_factor_defaults_to_1(self):
        """TC-UNIT-DlBomLineMixin-032: có vật tư nhưng không có hệ số phức
        tạp (complexity_id=None) thì hệ số mặc định là 1, waste_rate giữ
        nguyên bằng dlm_waste_rate của vật tư (5.0)."""
        material = SimpleNamespace(dlm_waste_rate=5.0)
        line = _FakeBomLine(material_id=material, complexity_id=None)
        line._onchange_material_waste()
        self.assertAlmostEqual(line.waste_rate, 5.0)

    def test_no_material_is_noop(self):
        """TC-UNIT-DlBomLineMixin-033: không có vật tư thì method return sớm,
        waste_rate hiện có (2.0) không bị đổi."""
        line = _FakeBomLine(material_id=None, waste_rate=2.0)
        line._onchange_material_waste()
        self.assertEqual(line.waste_rate, 2.0)  # early return, không đổi


# _dlm_recovery_value(): giá trị phế liệu thu hồi, trừ vào chi phí vật tư.
# Nhánh return sớm (không có vật tư / không có cờ thu hồi / rate=0) không
# chạm mat._dlm_uom_group()/dlm_mass_per_unit nên mock được bằng
# SimpleNamespace thuần. Nhánh happy-path đầy đủ (quy đổi mm-m, cây-kg) dùng
# dữ liệu Odoo thật, đã có ở test_material_calc_kind.py (T6/T6b), không lặp
# lại ở đây.
class TestDlmRecoveryValue(unittest.TestCase):
    def test_no_material_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-034: dòng BOM không có vật tư (material_id=None)
        thì _dlm_recovery_value() trả về 0.0."""
        line = _FakeBomLine(material_id=None)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_material_without_recovery_flag_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-035: vật tư không bật cờ thu hồi phế liệu
        (dlm_has_recovery=False) dù dlm_recovery_rate=50 thì vẫn trả về 0.0."""
        material = SimpleNamespace(dlm_has_recovery=False, dlm_recovery_rate=50.0)
        line = _FakeBomLine(material_id=material)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_material_zero_recovery_rate_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-036: vật tư bật cờ thu hồi nhưng
        dlm_recovery_rate=0.0 thì giá trị thu hồi vẫn là 0.0."""
        material = SimpleNamespace(dlm_has_recovery=True, dlm_recovery_rate=0.0)
        line = _FakeBomLine(material_id=material)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_happy_recovery_calculation_weight_group(self):
        """TC-UNIT-DlBomLineMixin-037: code thật đọc mat._dlm_uom_group() để
        chọn hệ số quy đổi kg. Ở nhóm weight, hệ số là 1 nên không cần
        dlm_mass_per_unit (xem _dlm_recovery_value() trong
        dl_bom_line_mixin.py)."""
        material = SimpleNamespace(
            dlm_has_recovery=True, dlm_recovery_rate=50.0,
            _dlm_uom_group=lambda: "weight",
            _dlm_scrap_unit_price=lambda: 20.0,
        )
        line = _FakeBomLine(material_id=material, effective_qty=10.0, quantity=8.0)
        # waste_qty = 10-8 = 2 (đã là kg vì weight-group); recovered = 2*50% = 1.0;
        # * scrap_price 20 = 20.0
        self.assertAlmostEqual(line._dlm_recovery_value(), 20.0)

    def test_happy_recovery_calculation_piece_group_converts_via_mass_per_unit(self):
        """TC-UNIT-DlBomLineMixin-037b: vật tư không mua theo kg (ví dụ theo
        cây), hao hụt phải quy đổi qua dlm_mass_per_unit trước khi nhân giá
        phế liệu/kg, khác với nhánh weight-group ở trên. Bỏ qua bước này thì
        mất trắng tiền thu hồi (xem T6 trong test_material_calc_kind.py)."""
        material = SimpleNamespace(
            dlm_has_recovery=True, dlm_recovery_rate=50.0,
            dlm_mass_per_unit=8.5,
            _dlm_uom_group=lambda: "unit",
            _dlm_scrap_unit_price=lambda: 20.0,
        )
        line = _FakeBomLine(material_id=material, effective_qty=10.0, quantity=8.0)
        # waste_qty=2 cây * 8.5 kg/cây = 17 kg; *50% = 8.5; *20 = 170.0
        self.assertAlmostEqual(line._dlm_recovery_value(), 170.0)


# _compute_effective_qty() / _compute_uom() / _compute_computed_quantity()
# Các method @api.depends này lặp "for rec in self:" trong code thật, nên
# gọi qua danh sách [rec] để giả lập recordset.
class TestComputeFields(unittest.TestCase):
    def test_effective_qty_happy(self):
        """TC-UNIT-DlBomLineMixin-038: quantity=100, waste_rate=5% thì
        effective_qty = 100 * (1 + 5/100) = 105."""
        line = _FakeBomLine(quantity=100.0, waste_rate=5.0)
        DlBomLineMixin._compute_effective_qty([line])
        self.assertAlmostEqual(line.effective_qty, 105.0)

    def test_effective_qty_zero_waste_boundary(self):
        """TC-UNIT-DlBomLineMixin-039: waste_rate=0 (biên dưới) thì
        effective_qty giữ nguyên bằng quantity (100)."""
        line = _FakeBomLine(quantity=100.0, waste_rate=0.0)
        DlBomLineMixin._compute_effective_qty([line])
        self.assertAlmostEqual(line.effective_qty, 100.0)

    def test_uom_from_material(self):
        """TC-UNIT-DlBomLineMixin-040: có vật tư với uom_id="kg" thì
        _compute_uom() gán uom_id của dòng BOM bằng uom_id của vật tư."""
        material = SimpleNamespace(uom_id="kg")
        line = _FakeBomLine(material_id=material)
        DlBomLineMixin._compute_uom([line])
        self.assertEqual(line.uom_id, "kg")

    def test_uom_no_material_is_false(self):
        """TC-UNIT-DlBomLineMixin-041: không có vật tư (material_id=None)
        thì _compute_uom() để uom_id là giá trị falsy."""
        line = _FakeBomLine(material_id=None)
        DlBomLineMixin._compute_uom([line])
        self.assertFalse(line.uom_id)

    def test_computed_quantity_mirrors_dlm_auto_quantity(self):
        """TC-UNIT-DlBomLineMixin-042: nay delegate qua _dlm_auto_quantity()
        (kind=cut_length, nhóm ĐVT 'length' trả thẳng total_m, không chia
        cho stock_length), không còn qua _measurement_quantity()/Shape."""
        material = SimpleNamespace(dlm_calc_kind="cut_length",
                                    _dlm_uom_group=lambda: "length")
        line = _FakeBomLine(material_id=material, dim_length=1000.0, piece_count=1)
        DlBomLineMixin._compute_computed_quantity([line])
        self.assertAlmostEqual(line.computed_quantity, 1.0)  # 1000mm -> 1m

    def test_computed_quantity_zero_when_no_material(self):
        """TC-UNIT-DlBomLineMixin-043: không có vật tư thì _dlm_auto_
        quantity() trả về None, compute phải ra 0.0 chứ không phải None."""
        line = _FakeBomLine(material_id=None)
        DlBomLineMixin._compute_computed_quantity([line])
        self.assertEqual(line.computed_quantity, 0.0)


# Constraints: _check_quantity() (không đổi) và _check_piece_count()
# (constraint mới thêm 2026-08-09, chưa có test trước bản viết lại này).
class TestConstraints(unittest.TestCase):
    def test_check_quantity_zero_raises(self):
        """TC-UNIT-DlBomLineMixin-044: quantity=0.0 (biên dưới) thì
        _check_quantity() báo lỗi ValidationError."""
        line = _FakeBomLine(quantity=0.0)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_quantity([line])

    def test_check_quantity_negative_raises(self):
        """TC-UNIT-DlBomLineMixin-045: quantity âm (-1.0) thì
        _check_quantity() báo lỗi ValidationError."""
        line = _FakeBomLine(quantity=-1.0)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_quantity([line])

    def test_check_quantity_positive_passes(self):
        """TC-UNIT-DlBomLineMixin-046: quantity dương rất nhỏ (0.001) thì
        _check_quantity() không báo lỗi."""
        line = _FakeBomLine(quantity=0.001)
        DlBomLineMixin._check_quantity([line])  # không raise

    def test_check_piece_count_zero_raises(self):
        """TC-UNIT-DlBomLineMixin-052: piece_count=0 (biên dưới) thì
        _check_piece_count() báo lỗi ValidationError."""
        line = _FakeBomLine(piece_count=0)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_piece_count([line])

    def test_check_piece_count_negative_raises(self):
        """TC-UNIT-DlBomLineMixin-053: piece_count âm (-1) thì
        _check_piece_count() báo lỗi ValidationError."""
        line = _FakeBomLine(piece_count=-1)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_piece_count([line])

    def test_check_piece_count_none_is_not_checked(self):
        """TC-UNIT-DlBomLineMixin-054: constraint chỉ raise khi piece_count
        khác None (rec.piece_count is not None and < 1), None thì bỏ qua."""
        line = _FakeBomLine(piece_count=None)
        DlBomLineMixin._check_piece_count([line])  # không raise

    def test_check_piece_count_positive_passes(self):
        """TC-UNIT-DlBomLineMixin-055: piece_count dương hợp lệ (4) thì
        _check_piece_count() không báo lỗi."""
        line = _FakeBomLine(piece_count=4)
        DlBomLineMixin._check_piece_count([line])  # không raise


if __name__ == "__main__":
    unittest.main()
