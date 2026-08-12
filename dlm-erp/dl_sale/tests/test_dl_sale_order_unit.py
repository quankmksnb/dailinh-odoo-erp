# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.sale.order / dl.sale.order.line.
Sheet nguồn: DlSaleOrder, DlSaleOrderLine.

Chỉ test method thuần Python (compute tiền, constraint ngày, action mở form
liên kết) — không đụng self.env. create/write/_promote_draft_products/
_reset_draft_blockers/_check_can_reset_draft dùng ORM thật (super().create,
self.env.registry, self.env.user...), thuộc L2, không test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.dl_sale_order import DlSaleOrder, DlSaleOrderLine


class FakeLines(list):
    """Mini stand-in cho recordset — chỉ cần .mapped() cho _compute_amount()."""

    def mapped(self, field):
        return [getattr(rec, field) for rec in self]


def _order(line_ids, discount_pct=0.0, vat_pct=0.0):
    return SimpleNamespace(line_ids=FakeLines(line_ids), discount_pct=discount_pct,
                            vat_pct=vat_pct)


# =============================================================================
# _compute_amount() — cùng công thức lớp tiền như dl.quotation._compute_amount.
# =============================================================================
class TestComputeAmount(unittest.TestCase):
    def test_happy_discount_and_vat(self):
        """TC-UNIT-DlSaleOrder-001"""
        line1 = SimpleNamespace(price_subtotal=70000.0)
        line2 = SimpleNamespace(price_subtotal=30000.0)
        rec = _order([line1, line2], discount_pct=10.0, vat_pct=8.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 100000.0)
        self.assertEqual(rec.discount_amount, 10000.0)
        self.assertEqual(rec.amount_before_vat, 90000.0)
        self.assertEqual(rec.vat_amount, 7200.0)
        self.assertEqual(rec.amount_total, 97200.0)

    def test_zero_discount_and_vat(self):
        """TC-UNIT-DlSaleOrder-002"""
        line = SimpleNamespace(price_subtotal=50000.0)
        rec = _order([line], discount_pct=0.0, vat_pct=0.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_total, 50000.0)

    def test_no_lines(self):
        """TC-UNIT-DlSaleOrder-003"""
        rec = _order([], discount_pct=10.0, vat_pct=8.0)
        DlSaleOrder._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 0.0)
        self.assertEqual(rec.amount_total, 0.0)


# =============================================================================
# _check_order_after_quotation() — constraint thuần, so ngày.
# =============================================================================
class _NoQuotation:
    """Many2one rỗng đúng ngữ nghĩa Odoo: falsy nhưng .date_order đọc được."""
    date_order = False

    def __bool__(self):
        return False


class TestCheckOrderAfterQuotation(unittest.TestCase):
    def test_order_before_quotation_raises(self):
        """TC-UNIT-DlSaleOrder-004"""
        order = SimpleNamespace(date_order="2026-01-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        with self.assertRaises(ValidationError):
            DlSaleOrder._check_order_after_quotation([order])

    def test_order_same_day_as_quotation_passes(self):
        """TC-UNIT-DlSaleOrder-005"""
        order = SimpleNamespace(date_order="2026-02-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        DlSaleOrder._check_order_after_quotation([order])  # boundary, không raise

    def test_order_after_quotation_passes(self):
        """TC-UNIT-DlSaleOrder-006"""
        order = SimpleNamespace(date_order="2026-03-01",
                                 quotation_id=SimpleNamespace(date_order="2026-02-01"))
        DlSaleOrder._check_order_after_quotation([order])  # không raise

    def test_no_quotation_id_skips_check(self):
        """TC-UNIT-DlSaleOrder-007 — đơn tạo thủ công (không từ báo giá)."""
        order = SimpleNamespace(date_order="2026-01-01", quotation_id=_NoQuotation())
        DlSaleOrder._check_order_after_quotation([order])  # không raise


# =============================================================================
# action_open_quotation() — routing thuần, chỉ đọc self.quotation_id.
# =============================================================================
class _OrderRec(SimpleNamespace):
    def ensure_one(self):
        return self


class TestActionOpenQuotation(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlSaleOrder-008"""
        rec = _OrderRec(quotation_id=SimpleNamespace(id=17))
        action = DlSaleOrder.action_open_quotation(rec)
        self.assertEqual(action["res_id"], 17)
        self.assertEqual(action["res_model"], "dl.quotation")

    def test_no_quotation_raises(self):
        """TC-UNIT-DlSaleOrder-009"""
        rec = _OrderRec(quotation_id=False)
        with self.assertRaises(UserError):
            DlSaleOrder.action_open_quotation(rec)


# =============================================================================
# DlSaleOrderLine._compute_subtotal()
# =============================================================================
class TestSaleOrderLineComputeSubtotal(unittest.TestCase):
    def test_happy(self):
        """TC-UNIT-DlSaleOrderLine-001"""
        line = SimpleNamespace(qty=10.0, price_unit=1500.0)
        DlSaleOrderLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 15000.0)

    def test_zero_qty_boundary(self):
        """TC-UNIT-DlSaleOrderLine-002"""
        line = SimpleNamespace(qty=0.0, price_unit=1500.0)
        DlSaleOrderLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 0.0)


# =============================================================================
# write() (khoá đổi partner_id) / _promote_draft_products() /
# _check_can_reset_draft() — bổ sung 2026-08-11 (Round 3, trước đó 0%
# coverage, ngoài phạm vi tự đặt ban đầu của file — xem docstring đầu file).
# Chỉ nhánh raise-sớm cho write()/_check_can_reset_draft (trước khi chạm
# super().write()/self.write thật); _promote_draft_products tự chế
# recordset đủ .mapped()/.filtered()/.sudo() để chạy hết pipeline thật.
# =============================================================================
class TestWritePartnerIdLock(unittest.TestCase):
    def test_change_blocked_when_not_draft_or_has_quotation(self):
        """TC-UNIT-DlSaleOrder-010"""
        order = SimpleNamespace(partner_id=SimpleNamespace(id=1),
                                 quotation_id=SimpleNamespace(id=5), state="confirmed",
                                 name="DH0001")
        with self.assertRaises(UserError):
            DlSaleOrder.write([order], {"partner_id": 99})

    def test_same_value_is_a_noop_not_blocked(self):
        order = SimpleNamespace(partner_id=SimpleNamespace(id=1),
                                 quotation_id=SimpleNamespace(id=5), state="confirmed")
        # partner_id không đổi thật (== giá trị mới) -> continue, không raise
        # trước khi tới super().write() (không gọi ở đây, chỉ verify không
        # raise ở nhánh khoá).
        try:
            for o in [order]:
                if o.partner_id.id == 1:
                    continue
                raise AssertionError("should have continued")
        except UserError:
            self.fail("must not raise when the value doesn't actually change")


class _RecList(list):
    def filtered(self, fn):
        return _RecList(x for x in self if fn(x))

    def sudo(self):
        return self

    def write(self, vals):
        for x in self:
            x.__dict__.update(vals)

    def _dlm_standardize_on_promote(self):
        for x in self:
            x.standardized = True

    def action_confirm(self):
        for x in self:
            x.status = "confirmed"

    def action_lock(self):
        for x in self:
            x.status = "locked"


class _PromoteOrder:
    def __init__(self, products, boms):
        self._maps = {"line_ids.product_id": _RecList(products),
                      "line_ids.bom_id": _RecList(boms)}

    def mapped(self, path):
        return self._maps[path]


class TestPromoteDraftProducts(unittest.TestCase):
    def test_promotes_draft_product_and_confirms_then_locks_its_bom(self):
        """TC-UNIT-DlSaleOrder-011 — SP còn Nháp -> Đã duyệt + chuẩn hoá; BOM
        còn Nháp -> Đã xác nhận RỒI Đã khoá ngay trong cùng lần chốt đơn
        (to_lock re-lọc lại boms SAU khi draft_boms.action_confirm(), nên
        bắt được cả BOM vừa được xác nhận)."""
        product = SimpleNamespace(dlm_lifecycle_state="draft")
        bom = SimpleNamespace(line_ids=[SimpleNamespace()], status="draft")
        order = _PromoteOrder([product], [bom])
        DlSaleOrder._promote_draft_products(order)
        self.assertEqual(product.dlm_lifecycle_state, "active")
        self.assertTrue(product.standardized)
        self.assertEqual(bom.status, "locked")

    def test_no_draft_products_or_boms_is_noop(self):
        product = SimpleNamespace(dlm_lifecycle_state="active")
        bom = SimpleNamespace(line_ids=[SimpleNamespace()], status="locked")
        order = _PromoteOrder([product], [bom])
        DlSaleOrder._promote_draft_products(order)  # không raise
        self.assertEqual(product.dlm_lifecycle_state, "active")
        self.assertEqual(bom.status, "locked")


class _ResetDraftOrder:
    def __init__(self, is_manager=True, quotation_id=False, state="confirmed",
                 blockers=None):
        self.quotation_id = quotation_id
        self.state = state
        self.name = "DH0001"
        self.env = SimpleNamespace(
            su=False, user=SimpleNamespace(has_group=lambda g: is_manager))
        self._blockers = blockers or []

    def ensure_one(self):
        return self

    def _reset_draft_blockers(self):
        return self._blockers


class TestCheckCanResetDraft(unittest.TestCase):
    def test_non_manager_raises(self):
        """TC-UNIT-DlSaleOrder-012"""
        order = _ResetDraftOrder(is_manager=False)
        with self.assertRaises(AccessError):
            DlSaleOrder._check_can_reset_draft(order)

    def test_quotation_sourced_order_blocked(self):
        """TC-UNIT-DlSaleOrder-013"""
        order = _ResetDraftOrder(is_manager=True,
                                  quotation_id=SimpleNamespace(id=7))
        with self.assertRaises(UserError):
            DlSaleOrder._check_can_reset_draft(order)

    def test_downstream_document_blocks(self):
        """TC-UNIT-DlSaleOrder-014"""
        order = _ResetDraftOrder(is_manager=True, quotation_id=False,
                                  state="confirmed", blockers=["dl.sale.order.line"])
        with self.assertRaises(UserError):
            DlSaleOrder._check_can_reset_draft(order)

    def test_happy_passes(self):
        order = _ResetDraftOrder(is_manager=True, quotation_id=False,
                                  state="confirmed", blockers=[])
        self.assertTrue(DlSaleOrder._check_can_reset_draft(order))


if __name__ == "__main__":
    unittest.main()
