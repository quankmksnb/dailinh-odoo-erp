"""Unit test L1 (thuần, không ORM/DB) cho dl.quotation.pricing.service.
Sheet nguồn: DlQuotationPricingService trong Report_5_1_UnitTests_L1.xlsx.

Chạy standalone bằng `python -m unittest` (không cần Odoo server/DB, nhưng
cần package `odoo` import được trên PYTHONPATH vì các method dưới test nằm
trong file model thật, file đó import `odoo.fields/models/exceptions/tools`).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.exceptions import UserError

from ..models.quotation_pricing_service import (
    DlQuotationPricingService,
    QTE_002,
    QTE_003,
    QTE_004,
    QTE_005,
    QTE_007,
    QTE_009,
)


def _svc():
    """Instance thuần, không qua __init__ của models.AbstractModel — các
    method dưới đây không đụng self.env nên không cần registry/cursor thật."""
    return object.__new__(DlQuotationPricingService)


class FakeRecordset:
    """Mini stand-in cho recordset Odoo (vd seller_ids đã filtered/sliced) —
    model thật dùng slice `[:1]` rồi đọc field ngay trên kết quả (hành vi
    recordset 0/1 phần tử: field rỗng -> False, có 1 bản ghi -> giá trị thật).
    Một `list` Python thường không hỗ trợ việc này nên cần double riêng."""

    def __init__(self, records):
        self._records = list(records)

    def __getitem__(self, item):
        return FakeRecordset(self._records[item])

    def __bool__(self):
        return bool(self._records)

    def __getattr__(self, name):
        if not self._records:
            return False
        return getattr(self._records[0], name)


class TestRoundPrice(unittest.TestCase):
    """Method _round_price() — staticmethod thuần."""

    def test_round_price_half_up_down(self):
        """TC-UNIT-DlQuotationPricingService-001"""
        self.assertEqual(DlQuotationPricingService._round_price(123456, 1000), 123000)

    def test_round_price_half_up_boundary(self):
        """TC-UNIT-DlQuotationPricingService-002"""
        self.assertEqual(DlQuotationPricingService._round_price(123500, 1000), 124000)

    def test_round_price_no_rounding_when_zero(self):
        """TC-UNIT-DlQuotationPricingService-003"""
        self.assertEqual(DlQuotationPricingService._round_price(123456.789, 0), 123456.789)

    def test_round_price_no_rounding_when_negative(self):
        """TC-UNIT-DlQuotationPricingService-004"""
        self.assertEqual(DlQuotationPricingService._round_price(123456.789, -100), 123456.789)


class TestPriceTrading(unittest.TestCase):
    """Method _price_trading()."""

    def test_price_trading_happy(self):
        """TC-UNIT-DlQuotationPricingService-005"""
        product = SimpleNamespace(id=7, display_name="Bu lông M8", list_price=25000)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=10)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 25000)
        self.assertEqual(vals["total_cost"], 0.0)
        self.assertEqual(vals["material_cost"], 0.0)
        self.assertEqual(vals["floor_price"], 0.0)
        self.assertEqual(comps[0]["amount"], 250000)

    def test_price_trading_small_qty_no_rounding(self):
        """TC-UNIT-DlQuotationPricingService-006"""
        product = SimpleNamespace(id=7, display_name="Keo dán", list_price=25000)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=0.001)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 25000)
        self.assertAlmostEqual(comps[0]["amount"], 25.0)

    def test_price_trading_zero_base_price_not_guarded(self):
        """TC-UNIT-DlQuotationPricingService-007"""
        product = SimpleNamespace(id=7, display_name="SP lỗi giá", list_price=0)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=5)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 0)
        self.assertEqual(comps[0]["amount"], 0)


class TestPriceManufactured(unittest.TestCase):
    """Method _price_manufactured() — mock _manufactured_direct_cost() để cô
    lập logic markup/floor.

    **Sửa lại 2026-08-09**: bản cũ patch _bom_material_cost() trực tiếp —
    method đó không còn tồn tại. _price_manufactured() nay đọc chi phí trực
    tiếp qua lớp cache _manufactured_direct_cost() (context['direct_cache'],
    theo rfq_line.id) thay vì gọi BOM costing thẳng; đây mới là ranh giới mock
    đúng để cô lập logic markup/floor khỏi toàn bộ phần đệ quy BOM + công đoạn
    (mà bản thân phần đó giờ đụng self.env — xem TestBomUnitCost bên dưới)."""

    @staticmethod
    def _rfq_line(qty=3, line_id=1):
        product = SimpleNamespace(id=42, display_name="Khung thép A")
        # _price_manufactured() nay stamp thêm dấu vết BOM (version/approved_by/
        # approved_date) vào vals (§5.2) — bom giả phải có đủ 3 field này.
        bom = SimpleNamespace(id=555, version=2,
                               approved_by=SimpleNamespace(id=8),
                               approved_date="2026-07-01")
        # _price_manufactured() nay đọc context['direct_cache'].get(rfq_line.id)
        # trước tiên (lớp cache) — cần .id.
        return SimpleNamespace(id=line_id, resolved_product_id=product, quantity=qty,
                                resolved_bom_id=bom, product_name="Khung thép A")

    @staticmethod
    def _direct_cost(bom, qty, material_unit, operation_cost=0.0, unit_specs=None, batch_specs=None):
        return {
            "bom": bom, "qty": qty,
            "material_unit": material_unit, "operation_cost": operation_cost,
            "unit_specs": unit_specs or [], "batch_specs": batch_specs or [],
        }

    def test_price_manufactured_happy(self):
        """TC-UNIT-DlQuotationPricingService-008"""
        rfq_line = self._rfq_line(qty=3)
        profit_rule = SimpleNamespace(id=99, revision=1, target_markup=20.0, min_markup=5.0)
        context = {"rounding_to": 0, "profit_rule": profit_rule}
        dc = self._direct_cost(
            rfq_line.resolved_bom_id, qty=3, material_unit=100000.0, unit_specs=[
                {"component_type": "material", "source_model": "product.supplierinfo",
                 "source_id": 1, "source_revision": 0, "material_id": 9,
                 "qty": 2.0, "unit_price": 50000.0, "amount": 100000.0},
            ])
        # DlQuotationPricingService là models.AbstractModel (dùng __slots__) —
        # không gán được method trên instance, phải patch ở cấp class.
        with patch.object(DlQuotationPricingService, "_manufactured_direct_cost",
                           return_value=dc):
            vals, comps = _svc()._price_manufactured(rfq_line, context)
        self.assertEqual(vals["total_cost"], 100000.0)
        self.assertEqual(vals["base_price"], 120000.0)
        self.assertEqual(vals["price_unit"], 120000.0)
        self.assertEqual(vals["floor_price"], 105000.0)
        markup_comp = comps[-1]
        self.assertEqual(markup_comp["component_type"], "markup")
        self.assertEqual(markup_comp["amount"], 60000.0)

    def test_price_manufactured_rounding_can_cross_below_floor(self):
        """TC-UNIT-DlQuotationPricingService-009"""
        rfq_line = self._rfq_line(qty=1)
        profit_rule = SimpleNamespace(id=99, revision=1, target_markup=20.0, min_markup=5.0)
        context = {"rounding_to": 1000, "profit_rule": profit_rule}
        dc = self._direct_cost(rfq_line.resolved_bom_id, qty=1, material_unit=1000.0)
        with patch.object(DlQuotationPricingService, "_manufactured_direct_cost",
                           return_value=dc):
            vals, _comps = _svc()._price_manufactured(rfq_line, context)
        self.assertEqual(vals["price_unit"], 1000.0)
        self.assertEqual(vals["floor_price"], 1050.0)
        self.assertLess(vals["price_unit"], vals["floor_price"])

    def test_price_manufactured_no_profit_rule_raises_qte005(self):
        """TC-UNIT-DlQuotationPricingService-010"""
        rfq_line = self._rfq_line(qty=1)
        context = {"rounding_to": 0, "profit_rule": None}
        dc = self._direct_cost(rfq_line.resolved_bom_id, qty=1, material_unit=1000.0)
        with patch.object(DlQuotationPricingService, "_manufactured_direct_cost",
                           return_value=dc):
            with self.assertRaises(UserError) as ctx:
                _svc()._price_manufactured(rfq_line, context)
        self.assertEqual(str(ctx.exception), QTE_005)


class TestBomUnitCost(unittest.TestCase):
    """Method _bom_unit_cost() (đổi tên từ _bom_material_cost() — trả về
    thêm op_var_unit, xem docstring trong quotation_pricing_service.py) —
    chỉ nhánh vật tư thô (L1); nhánh material_processed gọi self.env, thuộc
    L2, không test ở đây.

    **Sửa lại 2026-08-09**: method thật nay LUÔN gọi thêm
    self._bom_operation_variable_cost() ở cuối (kể cả BOM không có công đoạn
    nào) — method đó chạm self.env["dl.pricing.operation.rule"] ngay ở dòng
    đầu, trước khi lặp bom.operation_line_ids. 2 test "happy" (đi hết được tới
    cuối method) nên phải patch riêng _bom_operation_variable_cost() để cô
    lập đúng phần đang muốn test (chi phí vật tư + thu hồi phế liệu); công
    đoạn biến đổi tự nó cần một bộ test riêng (chưa có, ngoài phạm vi đợt sửa
    lỗi này — xem Report 5 §1.6). 3 test còn lại (missing seller/cycle guard/
    BOM rỗng) raise TRƯỚC khi method chạm tới đoạn công đoạn nên không cần
    patch gì thêm."""

    @staticmethod
    def _seller(price=50.0, currency="VND", id=1):
        return SimpleNamespace(id=id, price=price, currency_id=currency, is_applied=True)

    @staticmethod
    def _bom_line(material, effective_qty, quantity, recovery_value=0.0, line_id=101):
        # _bom_unit_cost() nay dùng bl.id làm khoá cho line_net{} (cơ sở % vật
        # liệu của công đoạn theo dòng đã chọn) — cần .id dù nhánh công đoạn
        # bị patch no-op ở đây.
        bl = SimpleNamespace(id=line_id, material_id=material, effective_qty=effective_qty,
                              quantity=quantity)
        bl._dlm_recovery_value = Mock(return_value=recovery_value)
        return bl

    def _unit_cost_no_operations(self, bom, context, visited):
        """Gọi _bom_unit_cost() thật với _bom_operation_variable_cost() đã
        patch trả về (0.0, []) — cô lập khỏi self.env, giữ nguyên phần vật
        tư/thu hồi thật đang muốn test."""
        with patch.object(DlQuotationPricingService, "_bom_operation_variable_cost",
                           return_value=(0.0, [])):
            return _svc()._bom_unit_cost(bom, context=context, visited=visited)

    def test_happy_raw_material_no_recovery(self):
        """TC-UNIT-DlQuotationPricingService-011"""
        seller = self._seller(price=50.0, currency="VND")
        sellers = Mock()
        sellers.filtered.return_value = FakeRecordset([seller])
        material = SimpleNamespace(
            id=3, display_name="Thép tấm", product_kind="material",
            uom_id="kg", uom_po_id="kg", seller_ids=sellers,
            dlm_scrap_product_id=None,
        )
        bl = self._bom_line(material, effective_qty=10.0, quantity=10.0, recovery_value=0.0)
        bom = SimpleNamespace(id=1, product_qty=2.0, line_ids=[bl])
        material_unit, op_var_unit, specs = self._unit_cost_no_operations(
            bom, context={"currency": "VND", "pricing_date": "2026-07-01"}, visited=frozenset())
        self.assertEqual(material_unit, 250.0)
        self.assertEqual(op_var_unit, 0.0)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["amount"], 250.0)
        self.assertEqual(specs[0]["qty"], 5.0)

    def test_happy_raw_material_with_recovery_uses_effective_qty_as_is(self):
        """TC-UNIT-DlQuotationPricingService-012 — xác nhận GB-10."""
        seller = self._seller(price=100.0, currency="VND")
        sellers = Mock()
        sellers.filtered.return_value = FakeRecordset([seller])
        scrap = SimpleNamespace(id=55)
        material = SimpleNamespace(
            id=3, display_name="Thép tấm", product_kind="material",
            uom_id="kg", uom_po_id="kg", seller_ids=sellers,
            dlm_scrap_product_id=scrap, dlm_recovery_rate=50.0,
            _dlm_scrap_unit_price=Mock(return_value=20.0),
        )
        # effective_qty=10 đã bao gồm hao hụt (quantity gốc=8) — method KHÔNG
        # được cộng thêm hao hụt lần nữa (GB-10), chỉ tiêu thụ effective_qty.
        bl = self._bom_line(material, effective_qty=10.0, quantity=8.0, recovery_value=20.0)
        bom = SimpleNamespace(id=1, product_qty=1.0, line_ids=[bl])
        material_unit, op_var_unit, specs = self._unit_cost_no_operations(
            bom, context={"currency": "VND", "pricing_date": "2026-07-01"}, visited=frozenset())
        self.assertEqual(material_unit, 980.0)  # 10*100 - 20
        self.assertEqual(op_var_unit, 0.0)
        material_spec, recovery_spec = specs
        self.assertEqual(material_spec["qty"], 10.0)  # effective_qty nguyên vẹn
        self.assertEqual(recovery_spec["component_type"], "recovery")
        self.assertEqual(recovery_spec["amount"], -20.0)
        self.assertEqual(recovery_spec["qty"], 1.0)  # (10-8) * 50%

    def test_missing_applied_seller_raises_qte003(self):
        """TC-UNIT-DlQuotationPricingService-013"""
        sellers = Mock()
        sellers.filtered.return_value = FakeRecordset([])
        material = SimpleNamespace(
            id=3, display_name="Thép tấm", product_kind="material",
            uom_id="kg", uom_po_id="kg", seller_ids=sellers,
        )
        bl = self._bom_line(material, effective_qty=10.0, quantity=10.0)
        bom = SimpleNamespace(id=1, product_qty=1.0, line_ids=[bl])
        with self.assertRaises(UserError) as ctx:
            _svc()._bom_unit_cost(
                bom, context={"currency": "VND", "pricing_date": "2026-07-01"}, visited=frozenset())
        self.assertEqual(str(ctx.exception), QTE_003 % "Thép tấm")

    def test_cycle_guard_raises_qte004(self):
        """TC-UNIT-DlQuotationPricingService-014"""
        bom = SimpleNamespace(id=5, product_qty=1.0, line_ids=[], display_name="BOM vòng lặp")
        with self.assertRaises(UserError) as ctx:
            _svc()._bom_unit_cost(bom, context={}, visited=frozenset({5}))
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM vòng lặp")

    def test_empty_bom_raises_qte004(self):
        """TC-UNIT-DlQuotationPricingService-015"""
        bom = SimpleNamespace(id=6, product_qty=0.0, line_ids=[], display_name="BOM rỗng")
        with self.assertRaises(UserError) as ctx:
            _svc()._bom_unit_cost(bom, context={}, visited=frozenset())
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM rỗng")


class TestCheckMeasureCompatibility(unittest.TestCase):
    """Method _check_measure_compatibility()."""

    def test_happy_compatible(self):
        """TC-UNIT-DlQuotationPricingService-016"""
        seller = SimpleNamespace(currency_id="VND")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="kg")
        self.assertIsNone(_svc()._check_measure_compatibility(
            SimpleNamespace(), material, seller, {"currency": "VND"}))

    def test_uom_mismatch_raises_qte007(self):
        """TC-UNIT-DlQuotationPricingService-017"""
        seller = SimpleNamespace(currency_id="VND")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="m")
        with self.assertRaises(UserError) as ctx:
            _svc()._check_measure_compatibility(SimpleNamespace(), material, seller, {"currency": "VND"})
        self.assertEqual(str(ctx.exception), QTE_007 % "Thép tấm")

    def test_currency_mismatch_raises_qte007(self):
        """TC-UNIT-DlQuotationPricingService-018"""
        seller = SimpleNamespace(currency_id="USD")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="kg")
        with self.assertRaises(UserError) as ctx:
            _svc()._check_measure_compatibility(SimpleNamespace(), material, seller, {"currency": "VND"})
        self.assertEqual(str(ctx.exception), QTE_007 % "Thép tấm")

    def test_uom_po_id_falsy_skips_uom_check(self):
        """TC-UNIT-DlQuotationPricingService-019"""
        seller = SimpleNamespace(currency_id="VND")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id=False)
        self.assertIsNone(_svc()._check_measure_compatibility(
            SimpleNamespace(), material, seller, {"currency": "VND"}))


class TestBelowFloor(unittest.TestCase):
    """Method _below_floor()."""

    @staticmethod
    def _line(line_type, qty, price_unit, floor_price):
        return SimpleNamespace(line_type=line_type, qty=qty, price_unit=price_unit, floor_price=floor_price)

    def test_no_line_below_floor(self):
        """TC-UNIT-DlQuotationPricingService-020"""
        line = self._line("manufactured", 10, 1000, 800)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=0, line_ids=[line])
        self.assertFalse(_svc()._below_floor(quotation))

    def test_discount_pushes_below_floor(self):
        """TC-UNIT-DlQuotationPricingService-021"""
        line = self._line("manufactured", 10, 1000, 950)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=1000, line_ids=[line])
        self.assertTrue(_svc()._below_floor(quotation))

    def test_trading_or_zero_floor_line_skipped(self):
        """TC-UNIT-DlQuotationPricingService-022"""
        trading_line = self._line("trading", 10, 1000, 0)
        zero_floor_line = self._line("manufactured", 10, 1000, 0)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=5000,
                                     line_ids=[trading_line, zero_floor_line])
        self.assertFalse(_svc()._below_floor(quotation))

    def test_zero_untaxed_no_zero_division(self):
        """TC-UNIT-DlQuotationPricingService-023"""
        line = self._line("manufactured", 5, 0, 100)
        quotation = SimpleNamespace(amount_untaxed=0, discount_amount=0, line_ids=[line])
        self.assertTrue(_svc()._below_floor(quotation))


class TestValidateLine(unittest.TestCase):
    """Method _validate_line()."""

    def test_happy_trading(self):
        """TC-UNIT-DlQuotationPricingService-024"""
        product = SimpleNamespace(list_price=100.0, display_name="SP A")
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=product, product_name="SP A")
        _svc()._validate_line(rfq_line, context={})  # không raise

    def test_happy_manufactured(self):
        """TC-UNIT-DlQuotationPricingService-025"""
        bom = SimpleNamespace(status="confirmed", product_qty=1.0, line_ids=[object()], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        _svc()._validate_line(rfq_line, context={})  # không raise

    def test_zero_quantity_raises(self):
        """TC-UNIT-DlQuotationPricingService-026"""
        rfq_line = SimpleNamespace(quantity=0, product_type="trading", product_name="SP A")
        with self.assertRaises(UserError):
            _svc()._validate_line(rfq_line, context={})

    def test_trading_missing_product_raises(self):
        """TC-UNIT-DlQuotationPricingService-027"""
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=None, product_name="SP A")
        with self.assertRaises(UserError):
            _svc()._validate_line(rfq_line, context={})

    def test_trading_zero_price_raises_qte009(self):
        """TC-UNIT-DlQuotationPricingService-028"""
        product = SimpleNamespace(list_price=0.0, display_name="SP A")
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=product, product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_009 % "SP A")

    def test_manufactured_bom_not_confirmed_raises_qte002(self):
        """TC-UNIT-DlQuotationPricingService-029"""
        bom = SimpleNamespace(status="draft", product_qty=1.0, line_ids=[object()], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_002 % "SP A")

    def test_manufactured_empty_bom_raises_qte004(self):
        """TC-UNIT-DlQuotationPricingService-030"""
        bom = SimpleNamespace(status="confirmed", product_qty=0.0, line_ids=[], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM A")


if __name__ == "__main__":
    unittest.main()
