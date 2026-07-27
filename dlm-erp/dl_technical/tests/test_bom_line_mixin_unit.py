"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.line.mixin (FT-19 — tự tính
số lượng vật tư từ hình dạng/kích thước; GB-12 — override bắt buộc lý do).
Sheet nguồn: DlBomLineMixin + DlMeasurementShapeCodeCheck trong
Report_5_1_UnitTests_L1.xlsx.

`dl.parametric.formula` (tên trong PRD) KHÔNG tồn tại trong code — đã grep xác
nhận, chỉ còn nhắc trong docstring như cơ chế cũ đã bỏ. Logic thật nằm ở
DlBomLineMixin._measurement_quantity() (17 công thức hard-code theo
shape.code) và các onchange/constraint xung quanh nó.

Kỹ thuật mock: các method dưới đây CHỈ ĐỌC field của self (không có method nào
trong nhóm test ở đây ghi field qua descriptor thật của ORM ngoại trừ các
onchange — mà onchange chỉ set field trên chính đối tượng self, không đụng
self.env). Vì DlBomLineMixin là AbstractModel dùng field descriptor thật (gán
`self.quantity = x` sẽ chạm cơ chế cache/env của Odoo nếu self là instance
thật), ta KHÔNG dùng `object.__new__(DlBomLineMixin)` làm self — thay vào đó
"mượn" thẳng các hàm thật (`DlBomLineMixin.<method>`) làm method trên 1 class
giả `_FakeBomLine` thuần Python (setattr tự do, không phải field descriptor).
Đây vẫn là gọi ĐÚNG code thật trong dl_bom_line_mixin.py, chỉ khác đối tượng
`self` được truyền vào.
"""
import math
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_bom_line_mixin import DlBomLineMixin, DlMeasurementShapeCodeCheck


class _FakeBomLine:
    """Stand-in thuần Python cho 1 dòng BOM — set đúng field mà các method
    thật cần đọc/ghi, mượn thẳng method thật từ DlBomLineMixin."""

    _measurement_quantity = DlBomLineMixin._measurement_quantity
    _onchange_measurement_values = DlBomLineMixin._onchange_measurement_values
    _onchange_measurement_shape = DlBomLineMixin._onchange_measurement_shape
    _onchange_measurement_type = DlBomLineMixin._onchange_measurement_type
    _onchange_material_waste = DlBomLineMixin._onchange_material_waste
    _dlm_recovery_value = DlBomLineMixin._dlm_recovery_value

    def __init__(self, **kwargs):
        self.measurement_shape_id = None
        self.measurement_type_id = None
        self.measurement_coefficient = 0.0
        self.dim_length = 0.0
        self.dim_width = 0.0
        self.dim_thickness = 0.0
        self.dim_side = 0.0
        self.dim_diameter = 0.0
        self.dim_height = 0.0
        self.quantity = 1.0
        self.is_override = False
        self.waste_rate = 0.0
        self.effective_qty = 0.0
        self.material_id = None
        self.complexity_id = None
        self.__dict__.update(kwargs)

    def ensure_one(self):
        return self


def _shape(code, default_coefficient=0.0, measurement_type_id=None):
    return SimpleNamespace(code=code, default_coefficient=default_coefficient,
                            measurement_type_id=measurement_type_id)


# =============================================================================
# _measurement_quantity() — 17 công thức + 2 case biên (không chọn Shape /
# code lạ không nằm trong KNOWN_SHAPE_CODES)
# =============================================================================
class TestMeasurementQuantity(unittest.TestCase):
    def test_no_shape_selected_returns_none(self):
        """TC-UNIT-DlBomLineMixin-001"""
        line = _FakeBomLine(measurement_shape_id=None)
        self.assertIsNone(line._measurement_quantity())

    def test_shape_code_empty_returns_none(self):
        """TC-UNIT-DlBomLineMixin-002"""
        line = _FakeBomLine(measurement_shape_id=_shape(code=""))
        self.assertIsNone(line._measurement_quantity())

    def test_shape_code_unknown_returns_none(self):
        """TC-UNIT-DlBomLineMixin-003"""
        line = _FakeBomLine(measurement_shape_id=_shape(code="not_a_real_code"))
        self.assertIsNone(line._measurement_quantity())

    def test_flat_plate(self):
        """TC-UNIT-DlBomLineMixin-004"""
        line = _FakeBomLine(measurement_shape_id=_shape("flat_plate"),
                             measurement_coefficient=7850.0,
                             dim_length=2000.0, dim_width=1000.0, dim_thickness=10.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2.0 * 1.0 * 0.01 * 7850.0)

    def test_hollow_square_tube(self):
        """TC-UNIT-DlBomLineMixin-005"""
        line = _FakeBomLine(measurement_shape_id=_shape("hollow_square_tube"),
                             measurement_coefficient=7850.0,
                             dim_side=100.0, dim_thickness=5.0, dim_length=3000.0)
        inner = 0.1 - 2 * 0.005
        expected = (0.1 ** 2 - inner ** 2) * 3.0 * 7850.0
        self.assertAlmostEqual(line._measurement_quantity(), expected)

    def test_hollow_square_tube_thick_wall_clamped_at_zero(self):
        """TC-UNIT-DlBomLineMixin-006"""
        # Boundary: độ dày >= nửa cạnh -> inner âm phải kẹp về 0, không cho ra
        # số âm vô lý (max(side - 2*thickness, 0.0) trong code thật).
        line = _FakeBomLine(measurement_shape_id=_shape("hollow_square_tube"),
                             measurement_coefficient=7850.0,
                             dim_side=100.0, dim_thickness=80.0, dim_length=1000.0)
        expected = (0.1 ** 2 - 0.0 ** 2) * 1.0 * 7850.0
        self.assertAlmostEqual(line._measurement_quantity(), expected)

    def test_hollow_round_tube(self):
        """TC-UNIT-DlBomLineMixin-007"""
        line = _FakeBomLine(measurement_shape_id=_shape("hollow_round_tube"),
                             measurement_coefficient=7850.0,
                             dim_diameter=100.0, dim_thickness=5.0, dim_length=3000.0)
        radius, inner_r = 0.05, 0.05 - 0.005
        expected = math.pi * (radius ** 2 - inner_r ** 2) * 3.0 * 7850.0
        self.assertAlmostEqual(line._measurement_quantity(), expected)

    def test_solid_round_bar(self):
        """TC-UNIT-DlBomLineMixin-008"""
        line = _FakeBomLine(measurement_shape_id=_shape("solid_round_bar"),
                             measurement_coefficient=7850.0,
                             dim_diameter=100.0, dim_length=2000.0)
        expected = math.pi * (0.05 ** 2) * 2.0 * 7850.0
        self.assertAlmostEqual(line._measurement_quantity(), expected)

    def test_solid_square_bar(self):
        """TC-UNIT-DlBomLineMixin-009"""
        line = _FakeBomLine(measurement_shape_id=_shape("solid_square_bar"),
                             measurement_coefficient=7850.0,
                             dim_side=100.0, dim_length=2000.0)
        self.assertAlmostEqual(line._measurement_quantity(), (0.1 ** 2) * 2.0 * 7850.0)

    def test_area_rectangle(self):
        """TC-UNIT-DlBomLineMixin-010"""
        line = _FakeBomLine(measurement_shape_id=_shape("area_rectangle"),
                             dim_length=2000.0, dim_width=1500.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2.0 * 1.5)

    def test_area_square(self):
        """TC-UNIT-DlBomLineMixin-011"""
        line = _FakeBomLine(measurement_shape_id=_shape("area_square"), dim_side=1000.0)
        self.assertAlmostEqual(line._measurement_quantity(), 1.0 ** 2)

    def test_area_circle(self):
        """TC-UNIT-DlBomLineMixin-012"""
        line = _FakeBomLine(measurement_shape_id=_shape("area_circle"), dim_diameter=2000.0)
        self.assertAlmostEqual(line._measurement_quantity(), math.pi * 1.0 ** 2)

    def test_area_triangle(self):
        """TC-UNIT-DlBomLineMixin-013"""
        line = _FakeBomLine(measurement_shape_id=_shape("area_triangle"),
                             dim_length=2000.0, dim_height=1500.0)
        self.assertAlmostEqual(line._measurement_quantity(), 0.5 * 2.0 * 1.5)

    def test_perimeter_rectangle(self):
        """TC-UNIT-DlBomLineMixin-014"""
        line = _FakeBomLine(measurement_shape_id=_shape("perimeter_rectangle"),
                             dim_length=2000.0, dim_width=1000.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2 * (2.0 + 1.0))

    def test_perimeter_square(self):
        """TC-UNIT-DlBomLineMixin-015"""
        line = _FakeBomLine(measurement_shape_id=_shape("perimeter_square"), dim_side=1000.0)
        self.assertAlmostEqual(line._measurement_quantity(), 4 * 1.0)

    def test_perimeter_circle(self):
        """TC-UNIT-DlBomLineMixin-016"""
        line = _FakeBomLine(measurement_shape_id=_shape("perimeter_circle"), dim_diameter=2000.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2 * math.pi * 1.0)

    def test_volume_box(self):
        """TC-UNIT-DlBomLineMixin-017"""
        line = _FakeBomLine(measurement_shape_id=_shape("volume_box"),
                             dim_length=2000.0, dim_width=1000.0, dim_height=500.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2.0 * 1.0 * 0.5)

    def test_volume_cube(self):
        """TC-UNIT-DlBomLineMixin-018"""
        line = _FakeBomLine(measurement_shape_id=_shape("volume_cube"), dim_side=1000.0)
        self.assertAlmostEqual(line._measurement_quantity(), 1.0 ** 3)

    def test_volume_cylinder(self):
        """TC-UNIT-DlBomLineMixin-019"""
        line = _FakeBomLine(measurement_shape_id=_shape("volume_cylinder"),
                             dim_diameter=2000.0, dim_height=2000.0)
        self.assertAlmostEqual(line._measurement_quantity(), math.pi * 1.0 ** 2 * 2.0)

    def test_volume_sphere(self):
        """TC-UNIT-DlBomLineMixin-020"""
        line = _FakeBomLine(measurement_shape_id=_shape("volume_sphere"), dim_diameter=2000.0)
        self.assertAlmostEqual(line._measurement_quantity(), (4.0 / 3.0) * math.pi * 1.0 ** 3)

    def test_length_segment(self):
        """TC-UNIT-DlBomLineMixin-021"""
        line = _FakeBomLine(measurement_shape_id=_shape("length_segment"), dim_length=2500.0)
        self.assertAlmostEqual(line._measurement_quantity(), 2.5)


# =============================================================================
# _onchange_measurement_values() — chỉ ghi self.quantity khi KHÔNG is_override
# VÀ qty tính ra not None và > 0
# =============================================================================
class TestOnchangeMeasurementValues(unittest.TestCase):
    def test_override_keeps_existing_quantity(self):
        """TC-UNIT-DlBomLineMixin-022"""
        line = _FakeBomLine(is_override=True, quantity=9.0,
                             measurement_shape_id=_shape("area_square"), dim_side=1000.0)
        line._onchange_measurement_values()
        self.assertEqual(line.quantity, 9.0)  # không bị ghi đè dù shape hợp lệ

    def test_computed_qty_overwrites_quantity(self):
        """TC-UNIT-DlBomLineMixin-023"""
        line = _FakeBomLine(is_override=False, quantity=9.0,
                             measurement_shape_id=_shape("area_square"), dim_side=2000.0)
        line._onchange_measurement_values()
        self.assertAlmostEqual(line.quantity, 4.0)  # side=2m -> area=4.0, ghi đè 9.0 cũ

    def test_no_shape_keeps_existing_quantity(self):
        """TC-UNIT-DlBomLineMixin-024"""
        line = _FakeBomLine(is_override=False, quantity=3.0, measurement_shape_id=None)
        line._onchange_measurement_values()
        self.assertEqual(line.quantity, 3.0)  # _measurement_quantity() trả None -> không ghi

    def test_zero_result_not_written(self):
        """TC-UNIT-DlBomLineMixin-025"""
        # Mọi kích thước = 0 -> qty tính ra = 0.0 -> KHÔNG ghi đè (qty > 0 mới ghi).
        line = _FakeBomLine(is_override=False, quantity=5.0,
                             measurement_shape_id=_shape("area_square"), dim_side=0.0)
        line._onchange_measurement_values()
        self.assertEqual(line.quantity, 5.0)


# =============================================================================
# _onchange_measurement_shape() — reset kích thước, set hệ số theo Shape
# =============================================================================
class TestOnchangeMeasurementShape(unittest.TestCase):
    def test_shape_selected_sets_default_coefficient_and_resets_dims(self):
        """TC-UNIT-DlBomLineMixin-026"""
        line = _FakeBomLine(measurement_shape_id=_shape("flat_plate", default_coefficient=7850.0),
                             dim_length=999.0, dim_width=999.0, dim_thickness=999.0,
                             dim_side=999.0, dim_diameter=999.0, dim_height=999.0)
        line._onchange_measurement_shape()
        self.assertEqual(line.measurement_coefficient, 7850.0)
        self.assertEqual((line.dim_length, line.dim_width, line.dim_thickness,
                           line.dim_side, line.dim_diameter, line.dim_height),
                          (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    def test_shape_cleared_sets_coefficient_zero(self):
        """TC-UNIT-DlBomLineMixin-027"""
        line = _FakeBomLine(measurement_shape_id=None, dim_length=999.0)
        line._onchange_measurement_shape()
        self.assertEqual(line.measurement_coefficient, 0.0)
        self.assertEqual(line.dim_length, 0.0)


# =============================================================================
# _onchange_measurement_type() — xóa Shape nếu không còn khớp Rule mới chọn
# =============================================================================
class TestOnchangeMeasurementType(unittest.TestCase):
    def test_shape_cleared_when_type_mismatches(self):
        """TC-UNIT-DlBomLineMixin-028"""
        old_type = SimpleNamespace(name="Khối lượng")
        new_type = SimpleNamespace(name="Diện tích")
        line = _FakeBomLine(measurement_shape_id=_shape("flat_plate", measurement_type_id=old_type),
                             measurement_type_id=new_type)
        line._onchange_measurement_type()
        self.assertFalse(line.measurement_shape_id)

    def test_shape_kept_when_type_matches(self):
        """TC-UNIT-DlBomLineMixin-029"""
        same_type = SimpleNamespace(name="Khối lượng")
        shape = _shape("flat_plate", measurement_type_id=same_type)
        line = _FakeBomLine(measurement_shape_id=shape, measurement_type_id=same_type)
        line._onchange_measurement_type()
        self.assertIs(line.measurement_shape_id, shape)

    def test_no_shape_selected_is_noop(self):
        """TC-UNIT-DlBomLineMixin-030"""
        line = _FakeBomLine(measurement_shape_id=None, measurement_type_id=SimpleNamespace())
        line._onchange_measurement_type()  # không raise, không đổi gì
        self.assertIsNone(line.measurement_shape_id)


# =============================================================================
# _onchange_material_waste() — % hao hụt = hao hụt cơ sở vật tư × hệ số phức tạp
# =============================================================================
class TestOnchangeMaterialWaste(unittest.TestCase):
    def test_material_and_complexity_set(self):
        """TC-UNIT-DlBomLineMixin-031"""
        material = SimpleNamespace(dlm_waste_rate=5.0)
        complexity = SimpleNamespace(factor=1.5)
        line = _FakeBomLine(material_id=material, complexity_id=complexity)
        line._onchange_material_waste()
        self.assertAlmostEqual(line.waste_rate, 7.5)

    def test_material_set_no_complexity_factor_defaults_to_1(self):
        """TC-UNIT-DlBomLineMixin-032"""
        material = SimpleNamespace(dlm_waste_rate=5.0)
        line = _FakeBomLine(material_id=material, complexity_id=None)
        line._onchange_material_waste()
        self.assertAlmostEqual(line.waste_rate, 5.0)

    def test_no_material_is_noop(self):
        """TC-UNIT-DlBomLineMixin-033"""
        line = _FakeBomLine(material_id=None, waste_rate=2.0)
        line._onchange_material_waste()
        self.assertEqual(line.waste_rate, 2.0)  # early return, không đổi


# =============================================================================
# _dlm_recovery_value() — giá trị phế liệu thu hồi, trừ vào chi phí vật tư
# =============================================================================
class TestDlmRecoveryValue(unittest.TestCase):
    def test_no_material_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-034"""
        line = _FakeBomLine(material_id=None)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_material_without_recovery_flag_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-035"""
        material = SimpleNamespace(dlm_has_recovery=False, dlm_recovery_rate=50.0)
        line = _FakeBomLine(material_id=material)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_material_zero_recovery_rate_returns_zero(self):
        """TC-UNIT-DlBomLineMixin-036"""
        material = SimpleNamespace(dlm_has_recovery=True, dlm_recovery_rate=0.0)
        line = _FakeBomLine(material_id=material)
        self.assertEqual(line._dlm_recovery_value(), 0.0)

    def test_happy_recovery_calculation(self):
        """TC-UNIT-DlBomLineMixin-037"""
        material = SimpleNamespace(dlm_has_recovery=True, dlm_recovery_rate=50.0,
                                    _dlm_scrap_unit_price=lambda: 20.0)
        line = _FakeBomLine(material_id=material, effective_qty=10.0, quantity=8.0)
        # waste_qty = 10-8 = 2; recovered = 2 * 50% = 1.0; * scrap_price 20 = 20.0
        self.assertAlmostEqual(line._dlm_recovery_value(), 20.0)


# =============================================================================
# _compute_effective_qty() / _compute_uom() / _compute_computed_quantity()
# (@api.depends -> gọi qua danh sách [rec], giống pattern _compute_amount ở
# Priority #1, vì code thật lặp `for rec in self:`)
# =============================================================================
class TestComputeFields(unittest.TestCase):
    def test_effective_qty_happy(self):
        """TC-UNIT-DlBomLineMixin-038"""
        line = _FakeBomLine(quantity=100.0, waste_rate=5.0)
        DlBomLineMixin._compute_effective_qty([line])
        self.assertAlmostEqual(line.effective_qty, 105.0)

    def test_effective_qty_zero_waste_boundary(self):
        """TC-UNIT-DlBomLineMixin-039"""
        line = _FakeBomLine(quantity=100.0, waste_rate=0.0)
        DlBomLineMixin._compute_effective_qty([line])
        self.assertAlmostEqual(line.effective_qty, 100.0)

    def test_uom_from_material(self):
        """TC-UNIT-DlBomLineMixin-040"""
        material = SimpleNamespace(uom_id="kg")
        line = _FakeBomLine(material_id=material)
        DlBomLineMixin._compute_uom([line])
        self.assertEqual(line.uom_id, "kg")

    def test_uom_no_material_is_false(self):
        """TC-UNIT-DlBomLineMixin-041"""
        line = _FakeBomLine(material_id=None)
        DlBomLineMixin._compute_uom([line])
        self.assertFalse(line.uom_id)

    def test_computed_quantity_mirrors_measurement_quantity(self):
        """TC-UNIT-DlBomLineMixin-042"""
        line = _FakeBomLine(measurement_shape_id=_shape("area_square"), dim_side=1000.0)
        DlBomLineMixin._compute_computed_quantity([line])
        self.assertAlmostEqual(line.computed_quantity, 1.0)

    def test_computed_quantity_zero_when_no_shape(self):
        """TC-UNIT-DlBomLineMixin-043"""
        line = _FakeBomLine(measurement_shape_id=None)
        DlBomLineMixin._compute_computed_quantity([line])
        self.assertEqual(line.computed_quantity, 0.0)


# =============================================================================
# Constraints: _check_quantity / _check_waste_rate / _check_override_reason
# =============================================================================
class TestConstraints(unittest.TestCase):
    def test_check_quantity_zero_raises(self):
        """TC-UNIT-DlBomLineMixin-044"""
        line = _FakeBomLine(quantity=0.0)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_quantity([line])

    def test_check_quantity_negative_raises(self):
        """TC-UNIT-DlBomLineMixin-045"""
        line = _FakeBomLine(quantity=-1.0)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_quantity([line])

    def test_check_quantity_positive_passes(self):
        """TC-UNIT-DlBomLineMixin-046"""
        line = _FakeBomLine(quantity=0.001)
        DlBomLineMixin._check_quantity([line])  # không raise

    def test_check_waste_rate_negative_raises(self):
        """TC-UNIT-DlBomLineMixin-047"""
        line = _FakeBomLine(waste_rate=-0.01)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_waste_rate([line])

    def test_check_waste_rate_zero_boundary_passes(self):
        """TC-UNIT-DlBomLineMixin-048"""
        line = _FakeBomLine(waste_rate=0.0)
        DlBomLineMixin._check_waste_rate([line])  # 0 hợp lệ, không raise

    def test_check_override_reason_missing_raises(self):
        """TC-UNIT-DlBomLineMixin-049"""
        line = _FakeBomLine(is_override=True, override_reason=False)
        with self.assertRaises(ValidationError):
            DlBomLineMixin._check_override_reason([line])

    def test_check_override_reason_present_passes(self):
        """TC-UNIT-DlBomLineMixin-050"""
        line = _FakeBomLine(is_override=True, override_reason="Điều chỉnh theo thực tế đo đạc")
        DlBomLineMixin._check_override_reason([line])  # không raise

    def test_check_override_reason_not_overriding_ignores_missing_reason(self):
        """TC-UNIT-DlBomLineMixin-051"""
        line = _FakeBomLine(is_override=False, override_reason=False)
        DlBomLineMixin._check_override_reason([line])  # không raise vì is_override=False


# =============================================================================
# Sheet: DlMeasurementShapeCodeCheck (_inherit = "dl.measurement.shape",
# cùng file dl_bom_line_mixin.py nhưng khác class thật -> tách sheet riêng)
# =============================================================================
class TestCheckCodeKnown(unittest.TestCase):
    def test_known_code_passes(self):
        """TC-UNIT-DlMeasurementShapeCodeCheck-001"""
        shape = SimpleNamespace(code="flat_plate")
        DlMeasurementShapeCodeCheck._check_code_known([shape])  # không raise

    def test_unknown_nonempty_code_raises(self):
        """TC-UNIT-DlMeasurementShapeCodeCheck-002"""
        shape = SimpleNamespace(code="hinh_thoi_la")
        with self.assertRaises(ValidationError):
            DlMeasurementShapeCodeCheck._check_code_known([shape])

    def test_empty_code_passes(self):
        """TC-UNIT-DlMeasurementShapeCodeCheck-003"""
        shape = SimpleNamespace(code=False)
        DlMeasurementShapeCodeCheck._check_code_known([shape])  # code rỗng -> bỏ qua, không raise


if __name__ == "__main__":
    unittest.main()
