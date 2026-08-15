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
    """Instance thuần, không qua __init__ của models.AbstractModel. Các
    method dưới đây không đụng self.env nên không cần registry/cursor thật."""
    return object.__new__(DlQuotationPricingService)


class FakeRecordset:
    """Mini stand-in cho recordset Odoo (ví dụ seller_ids đã filtered/sliced).
    Model thật dùng slice `[:1]` rồi đọc field ngay trên kết quả (hành vi
    recordset 0/1 phần tử: field rỗng trả về False, có 1 bản ghi trả về giá
    trị thật). Một `list` Python thường không hỗ trợ việc này nên cần double
    riêng."""

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
    """Method _round_price(): staticmethod thuần."""

    def test_round_price_half_up_down(self):
        """TC-UNIT-DlQuotationPricingService-001: làm tròn 123456 theo bước 1000
        (round half up), kỳ vọng kết quả làm tròn xuống 123000."""
        self.assertEqual(DlQuotationPricingService._round_price(123456, 1000), 123000)

    def test_round_price_half_up_boundary(self):
        """TC-UNIT-DlQuotationPricingService-002: giá trị 123500 đúng ranh giới nửa
        đơn vị với bước làm tròn 1000, kỳ vọng làm tròn lên 124000."""
        self.assertEqual(DlQuotationPricingService._round_price(123500, 1000), 124000)

    def test_round_price_no_rounding_when_zero(self):
        """TC-UNIT-DlQuotationPricingService-003: bước làm tròn bằng 0, kỳ vọng
        không làm tròn, giữ nguyên 123456.789."""
        self.assertEqual(DlQuotationPricingService._round_price(123456.789, 0), 123456.789)

    def test_round_price_no_rounding_when_negative(self):
        """TC-UNIT-DlQuotationPricingService-004: bước làm tròn âm (-100), kỳ vọng
        cũng không làm tròn, giữ nguyên 123456.789."""
        self.assertEqual(DlQuotationPricingService._round_price(123456.789, -100), 123456.789)


class TestPriceTrading(unittest.TestCase):
    """Method _price_trading()."""

    def test_price_trading_happy(self):
        """TC-UNIT-DlQuotationPricingService-005: sản phẩm thương mại list_price=25000,
        số lượng 10, kỳ vọng price_unit=25000, total_cost/material_cost/floor_price
        đều bằng 0, thành phần giá đầu tiên có amount=250000."""
        product = SimpleNamespace(id=7, display_name="Bu lông M8", list_price=25000)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=10)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 25000)
        self.assertEqual(vals["total_cost"], 0.0)
        self.assertEqual(vals["material_cost"], 0.0)
        self.assertEqual(vals["floor_price"], 0.0)
        self.assertEqual(comps[0]["amount"], 250000)

    def test_price_trading_small_qty_no_rounding(self):
        """TC-UNIT-DlQuotationPricingService-006: số lượng rất nhỏ (0.001), kỳ vọng
        price_unit vẫn giữ nguyên 25000 và thành phần giá xấp xỉ 25.0, không bị lỗi
        làm tròn."""
        product = SimpleNamespace(id=7, display_name="Keo dán", list_price=25000)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=0.001)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 25000)
        self.assertAlmostEqual(comps[0]["amount"], 25.0)

    def test_price_trading_zero_base_price_not_guarded(self):
        """TC-UNIT-DlQuotationPricingService-007: sản phẩm có list_price=0 (giá lỗi),
        kỳ vọng method không có guard chặn, price_unit và amount thành phần đều
        bằng 0."""
        product = SimpleNamespace(id=7, display_name="SP lỗi giá", list_price=0)
        rfq_line = SimpleNamespace(resolved_product_id=product, quantity=5)
        vals, comps = _svc()._price_trading(rfq_line, context={})
        self.assertEqual(vals["price_unit"], 0)
        self.assertEqual(comps[0]["amount"], 0)


class TestPriceManufactured(unittest.TestCase):
    """Method _price_manufactured(): mock _manufactured_direct_cost() (lớp cache
    chi phí trực tiếp theo rfq_line.id) để cô lập logic markup/floor khỏi phần
    đệ quy BOM/công đoạn thật (phần đó đụng self.env, xem TestBomUnitCost)."""

    @staticmethod
    def _rfq_line(qty=3, line_id=1):
        product = SimpleNamespace(id=42, display_name="Khung thép A")
        # _price_manufactured() nay stamp thêm dấu vết BOM (version/approved_by/
        # approved_date) vào vals (§5.2), nên bom giả phải có đủ 3 field này.
        bom = SimpleNamespace(id=555, version=2,
                               approved_by=SimpleNamespace(id=8),
                               approved_date="2026-07-01")
        # _price_manufactured() nay đọc context['direct_cache'].get(rfq_line.id)
        # trước tiên (lớp cache), nên cần .id.
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
        """TC-UNIT-DlQuotationPricingService-008: mock direct cost material_unit=100000
        cho qty=3, profit_rule target_markup=20%/min_markup=5%, kỳ vọng
        total_cost=100000, base_price/price_unit=120000, floor_price=105000, thành
        phần markup cuối cùng có amount=60000."""
        rfq_line = self._rfq_line(qty=3)
        profit_rule = SimpleNamespace(id=99, revision=1, target_markup=20.0, min_markup=5.0)
        context = {"rounding_to": 0, "profit_rule": profit_rule}
        dc = self._direct_cost(
            rfq_line.resolved_bom_id, qty=3, material_unit=100000.0, unit_specs=[
                {"component_type": "material", "source_model": "product.supplierinfo",
                 "source_id": 1, "source_revision": 0, "material_id": 9,
                 "qty": 2.0, "unit_price": 50000.0, "amount": 100000.0},
            ])
        # DlQuotationPricingService là models.AbstractModel (dùng __slots__),
        # không gán được method trên instance nên phải patch ở cấp class.
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
        """TC-UNIT-DlQuotationPricingService-009: rounding_to=1000 khiến price_unit
        sau làm tròn (1000) rơi xuống dưới floor_price (1050), xác nhận việc làm
        tròn có thể đẩy giá vượt xuống dưới floor."""
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
        """TC-UNIT-DlQuotationPricingService-010: không có profit_rule (None), kỳ
        vọng raise UserError với thông báo QTE_005."""
        rfq_line = self._rfq_line(qty=1)
        context = {"rounding_to": 0, "profit_rule": None}
        dc = self._direct_cost(rfq_line.resolved_bom_id, qty=1, material_unit=1000.0)
        with patch.object(DlQuotationPricingService, "_manufactured_direct_cost",
                           return_value=dc):
            with self.assertRaises(UserError) as ctx:
                _svc()._price_manufactured(rfq_line, context)
        self.assertEqual(str(ctx.exception), QTE_005)


class TestBomUnitCost(unittest.TestCase):
    """Method _bom_unit_cost(): trả về (material_unit, op_var_unit, specs). Chỉ
    test nhánh vật tư thô (L1); nhánh material_processed đụng self.env nên thuộc
    L2. Hai test happy patch _bom_operation_variable_cost() (chạm self.env) để cô
    lập phần vật tư/thu hồi phế liệu đang test khỏi phần công đoạn thật; 3 test
    raise sớm (thiếu seller / cycle guard / BOM rỗng) không cần patch vì raise
    trước khi chạm tới đoạn công đoạn."""

    @staticmethod
    def _seller(price=50.0, currency="VND", id=1):
        return SimpleNamespace(id=id, price=price, currency_id=currency, is_applied=True)

    @staticmethod
    def _bom_line(material, effective_qty, quantity, recovery_value=0.0, line_id=101):
        # _bom_unit_cost() nay dùng bl.id làm khoá cho line_net{} (cơ sở % vật
        # liệu của công đoạn theo dòng đã chọn), nên cần .id dù nhánh công
        # đoạn bị patch no-op ở đây.
        bl = SimpleNamespace(id=line_id, material_id=material, effective_qty=effective_qty,
                              quantity=quantity)
        bl._dlm_recovery_value = Mock(return_value=recovery_value)
        return bl

    def _unit_cost_no_operations(self, bom, context, visited):
        """Gọi _bom_unit_cost() thật với _bom_operation_variable_cost() đã
        patch trả về (0.0, []), cô lập khỏi self.env, giữ nguyên phần vật
        tư/thu hồi thật đang muốn test."""
        with patch.object(DlQuotationPricingService, "_bom_operation_variable_cost",
                           return_value=(0.0, [])):
            return _svc()._bom_unit_cost(bom, context=context, visited=visited)

    def test_happy_raw_material_no_recovery(self):
        """TC-UNIT-DlQuotationPricingService-011: vật tư thô không có thu hồi phế
        liệu, seller giá 50 VND, effective_qty=10, bom.product_qty=2, kỳ vọng
        material_unit=250, op_var_unit=0, 1 dòng spec với amount=250, qty=5."""
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
        """TC-UNIT-DlQuotationPricingService-012: xác nhận GB-10."""
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
        # effective_qty=10 đã bao gồm hao hụt (quantity gốc=8), method không
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
        """TC-UNIT-DlQuotationPricingService-013: vật tư không có seller nào
        đang áp dụng giá thì báo lỗi UserError QTE_003 kèm tên vật tư."""
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
        """TC-UNIT-DlQuotationPricingService-014: BOM (id=5) đã nằm trong tập
        visited, tức đang bị đệ quy vòng lặp, kỳ vọng raise UserError QTE_004 kèm
        tên BOM."""
        bom = SimpleNamespace(id=5, product_qty=1.0, line_ids=[], display_name="BOM vòng lặp")
        with self.assertRaises(UserError) as ctx:
            _svc()._bom_unit_cost(bom, context={}, visited=frozenset({5}))
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM vòng lặp")

    def test_empty_bom_raises_qte004(self):
        """TC-UNIT-DlQuotationPricingService-015: BOM rỗng (product_qty=0, không có
        dòng vật tư), kỳ vọng raise UserError QTE_004 kèm tên BOM."""
        bom = SimpleNamespace(id=6, product_qty=0.0, line_ids=[], display_name="BOM rỗng")
        with self.assertRaises(UserError) as ctx:
            _svc()._bom_unit_cost(bom, context={}, visited=frozenset())
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM rỗng")


class TestCheckMeasureCompatibility(unittest.TestCase):
    """Method _check_measure_compatibility()."""

    def test_happy_compatible(self):
        """TC-UNIT-DlQuotationPricingService-016: đơn vị mua (uom_po_id) trùng đơn
        vị vật tư và tiền tệ seller trùng tiền tệ context, kỳ vọng không raise
        (trả về None)."""
        seller = SimpleNamespace(currency_id="VND")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="kg")
        self.assertIsNone(_svc()._check_measure_compatibility(
            SimpleNamespace(), material, seller, {"currency": "VND"}))

    def test_uom_mismatch_raises_qte007(self):
        """TC-UNIT-DlQuotationPricingService-017: đơn vị mua (uom_po_id="m") khác đơn
        vị vật tư (uom_id="kg"), kỳ vọng raise UserError QTE_007 kèm tên vật tư."""
        seller = SimpleNamespace(currency_id="VND")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="m")
        with self.assertRaises(UserError) as ctx:
            _svc()._check_measure_compatibility(SimpleNamespace(), material, seller, {"currency": "VND"})
        self.assertEqual(str(ctx.exception), QTE_007 % "Thép tấm")

    def test_currency_mismatch_raises_qte007(self):
        """TC-UNIT-DlQuotationPricingService-018: tiền tệ seller (USD) khác tiền tệ
        context (VND), kỳ vọng raise UserError QTE_007 kèm tên vật tư."""
        seller = SimpleNamespace(currency_id="USD")
        material = SimpleNamespace(display_name="Thép tấm", uom_id="kg", uom_po_id="kg")
        with self.assertRaises(UserError) as ctx:
            _svc()._check_measure_compatibility(SimpleNamespace(), material, seller, {"currency": "VND"})
        self.assertEqual(str(ctx.exception), QTE_007 % "Thép tấm")

    def test_uom_po_id_falsy_skips_uom_check(self):
        """TC-UNIT-DlQuotationPricingService-019: uom_po_id là giá trị falsy (False),
        kỳ vọng bỏ qua bước kiểm tra đơn vị đo, không raise."""
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
        """TC-UNIT-DlQuotationPricingService-020: giá bán sau chiết khấu vẫn không
        thấp hơn floor_price của dòng, kỳ vọng trả về False."""
        line = self._line("manufactured", 10, 1000, 800)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=0, line_ids=[line])
        self.assertFalse(_svc()._below_floor(quotation))

    def test_discount_pushes_below_floor(self):
        """TC-UNIT-DlQuotationPricingService-021: chiết khấu lớn (discount_amount=1000)
        kéo giá bán thực tế xuống dưới floor_price của dòng, kỳ vọng trả về True."""
        line = self._line("manufactured", 10, 1000, 950)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=1000, line_ids=[line])
        self.assertTrue(_svc()._below_floor(quotation))

    def test_trading_or_zero_floor_line_skipped(self):
        """TC-UNIT-DlQuotationPricingService-022: dòng trading và dòng manufactured có
        floor_price=0 đều bị bỏ qua khi kiểm tra, kỳ vọng dù chiết khấu lớn vẫn trả
        về False."""
        trading_line = self._line("trading", 10, 1000, 0)
        zero_floor_line = self._line("manufactured", 10, 1000, 0)
        quotation = SimpleNamespace(amount_untaxed=10000, discount_amount=5000,
                                     line_ids=[trading_line, zero_floor_line])
        self.assertFalse(_svc()._below_floor(quotation))

    def test_zero_untaxed_no_zero_division(self):
        """TC-UNIT-DlQuotationPricingService-023: amount_untaxed=0 (tránh chia cho 0),
        kỳ vọng vẫn trả về True (coi như dưới floor) mà không lỗi."""
        line = self._line("manufactured", 5, 0, 100)
        quotation = SimpleNamespace(amount_untaxed=0, discount_amount=0, line_ids=[line])
        self.assertTrue(_svc()._below_floor(quotation))


class TestValidateLine(unittest.TestCase):
    """Method _validate_line()."""

    def test_happy_trading(self):
        """TC-UNIT-DlQuotationPricingService-024: dòng trading hợp lệ (quantity=5,
        có resolved_product_id với list_price>0), kỳ vọng không raise."""
        product = SimpleNamespace(list_price=100.0, display_name="SP A")
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=product, product_name="SP A")
        _svc()._validate_line(rfq_line, context={})  # không raise

    def test_happy_manufactured(self):
        """TC-UNIT-DlQuotationPricingService-025: dòng manufactured hợp lệ (BOM
        status="confirmed", có product_qty và ít nhất 1 dòng vật tư), kỳ vọng
        không raise."""
        bom = SimpleNamespace(status="confirmed", product_qty=1.0, line_ids=[object()], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        _svc()._validate_line(rfq_line, context={})  # không raise

    def test_zero_quantity_raises(self):
        """TC-UNIT-DlQuotationPricingService-026: quantity=0, kỳ vọng raise
        UserError."""
        rfq_line = SimpleNamespace(quantity=0, product_type="trading", product_name="SP A")
        with self.assertRaises(UserError):
            _svc()._validate_line(rfq_line, context={})

    def test_trading_missing_product_raises(self):
        """TC-UNIT-DlQuotationPricingService-027: dòng trading nhưng
        resolved_product_id=None (thiếu sản phẩm), kỳ vọng raise UserError."""
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=None, product_name="SP A")
        with self.assertRaises(UserError):
            _svc()._validate_line(rfq_line, context={})

    def test_trading_zero_price_raises_qte009(self):
        """TC-UNIT-DlQuotationPricingService-028: dòng trading nhưng list_price của
        sản phẩm bằng 0, kỳ vọng raise UserError QTE_009 kèm tên sản phẩm."""
        product = SimpleNamespace(list_price=0.0, display_name="SP A")
        rfq_line = SimpleNamespace(quantity=5, product_type="trading",
                                    resolved_product_id=product, product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_009 % "SP A")

    def test_manufactured_bom_not_confirmed_raises_qte002(self):
        """TC-UNIT-DlQuotationPricingService-029: dòng manufactured nhưng BOM có
        status="draft" (chưa confirmed), kỳ vọng raise UserError QTE_002 kèm tên
        sản phẩm."""
        bom = SimpleNamespace(status="draft", product_qty=1.0, line_ids=[object()], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_002 % "SP A")

    def test_manufactured_empty_bom_raises_qte004(self):
        """TC-UNIT-DlQuotationPricingService-030: dòng manufactured với BOM confirmed
        nhưng rỗng (product_qty=0, không có dòng vật tư), kỳ vọng raise UserError
        QTE_004 kèm tên BOM."""
        bom = SimpleNamespace(status="confirmed", product_qty=0.0, line_ids=[], display_name="BOM A")
        rfq_line = SimpleNamespace(quantity=5, product_type="manufactured",
                                    resolved_bom_id=bom, resolved_product_id=SimpleNamespace(display_name="SP A"),
                                    product_name="SP A")
        with self.assertRaises(UserError) as ctx:
            _svc()._validate_line(rfq_line, context={})
        self.assertEqual(str(ctx.exception), QTE_004 % "BOM A")


if __name__ == "__main__":
    unittest.main()
