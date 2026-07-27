"""Unit test L1 (thuần, không ORM/DB) cho dl.quotation / dl.quotation.line.
Sheet nguồn: DlQuotation, DlQuotationLine trong Report_5_1_UnitTests_L1.xlsx.
"""
import unittest
from types import SimpleNamespace

from ..models.dl_quotation import DlQuotation, DlQuotationLine


class FakeLines(list):
    """Mini stand-in cho recordset Odoo — chỉ implement .mapped() vì đó là
    API duy nhất _compute_amount() cần, không kéo theo self.env/ORM."""

    def mapped(self, field):
        return [getattr(rec, field) for rec in self]


def _quotation(line_ids, discount_pct=0.0, vat_pct=0.0):
    return SimpleNamespace(
        line_ids=FakeLines(line_ids),
        discount_pct=discount_pct,
        vat_pct=vat_pct,
    )


class TestQuotationComputeAmount(unittest.TestCase):
    """Method _compute_amount() trên dl.quotation."""

    def test_happy_discount_and_vat(self):
        """TC-UNIT-DlQuotation-001"""
        line1 = SimpleNamespace(price_subtotal=70000.0, total_cost=5000.0, qty=2.0, floor_price=4000.0)
        line2 = SimpleNamespace(price_subtotal=30000.0, total_cost=3000.0, qty=1.0, floor_price=2500.0)
        rec = _quotation([line1, line2], discount_pct=10.0, vat_pct=8.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 100000.0)
        self.assertEqual(rec.discount_amount, 10000.0)
        self.assertEqual(rec.amount_before_vat, 90000.0)
        self.assertEqual(rec.vat_amount, 7200.0)
        self.assertEqual(rec.amount_total, 97200.0)
        self.assertEqual(rec.total_cost, 13000.0)
        self.assertEqual(rec.floor_amount, 10500.0)
        self.assertAlmostEqual(rec.effective_markup, (90000.0 - 13000.0) / 13000.0 * 100.0)

    def test_zero_total_cost_no_zero_division(self):
        """TC-UNIT-DlQuotation-002"""
        line = SimpleNamespace(price_subtotal=50000.0, total_cost=0.0, qty=3.0, floor_price=0.0)
        rec = _quotation([line], discount_pct=0.0, vat_pct=10.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.total_cost, 0.0)
        self.assertEqual(rec.effective_markup, 0.0)

    def test_zero_discount_and_vat(self):
        """TC-UNIT-DlQuotation-003"""
        line = SimpleNamespace(price_subtotal=20000.0, total_cost=1000.0, qty=1.0, floor_price=900.0)
        rec = _quotation([line], discount_pct=0.0, vat_pct=0.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.discount_amount, 0.0)
        self.assertEqual(rec.vat_amount, 0.0)
        self.assertEqual(rec.amount_total, 20000.0)

    def test_no_lines(self):
        """TC-UNIT-DlQuotation-004"""
        rec = _quotation([], discount_pct=10.0, vat_pct=8.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 0.0)
        self.assertEqual(rec.amount_total, 0.0)
        self.assertEqual(rec.effective_markup, 0.0)
        self.assertEqual(rec.floor_amount, 0.0)


class TestQuotationLineComputeSubtotal(unittest.TestCase):
    """Method _compute_subtotal() trên dl.quotation.line."""

    def test_happy(self):
        """TC-UNIT-DlQuotationLine-001"""
        line = SimpleNamespace(qty=10.0, price_unit=1500.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 15000.0)

    def test_zero_qty_boundary(self):
        """TC-UNIT-DlQuotationLine-002"""
        line = SimpleNamespace(qty=0.0, price_unit=1500.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 0.0)

    def test_negative_qty_not_guarded(self):
        """TC-UNIT-DlQuotationLine-003"""
        line = SimpleNamespace(qty=-5.0, price_unit=100.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, -500.0)


if __name__ == "__main__":
    unittest.main()
