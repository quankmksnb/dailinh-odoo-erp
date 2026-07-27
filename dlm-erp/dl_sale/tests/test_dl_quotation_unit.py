"""Unit test L1 (thuần, không ORM/DB) cho dl.quotation / dl.quotation.line.
Sheet nguồn: DlQuotation, DlQuotationLine trong Report_5_1_UnitTests_L1.xlsx.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from odoo.exceptions import UserError

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


class _RS:
    """Stand-in cho recordset Odoo nhiều bản ghi — hỗ trợ `for rec in self`
    (đọc field từng bản ghi) và `self.field = x` broadcast xuống MỌI bản ghi
    (đúng ngữ nghĩa gán field ở cấp recordset thật của Odoo, vd
    `action_send()` làm `self.state = 'sent'` sau vòng lặp kiểm tra)."""

    def __init__(self, records):
        object.__setattr__(self, "_records", list(records))

    def __iter__(self):
        return iter(self._records)

    def __setattr__(self, name, value):
        for r in self._records:
            setattr(r, name, value)


def _quo_rec(**kwargs):
    rec = SimpleNamespace(
        state="draft", approval_state="not_required", approval_level="",
        approval_request_id=None, sale_order_id=None, name="BG0001",
    )
    rec.__dict__.update(kwargs)
    rec.ensure_one = lambda: rec  # action_open_approval_request/action_open_sale_order cần
    return rec


class TestActionSend(unittest.TestCase):
    """Method _compute_amount()-adjacent: action_send() — L1 (không gọi self.env)."""

    def test_happy_approved_to_sent(self):
        """TC-UNIT-DlQuotation-005"""
        rec = _quo_rec(state="approved", approval_state="not_required")
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")

    def test_blocked_when_approval_pending(self):
        """TC-UNIT-DlQuotation-006"""
        rec = _quo_rec(state="approved", approval_state="pending")
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_blocked_when_approval_rejected(self):
        """TC-UNIT-DlQuotation-007"""
        rec = _quo_rec(state="approved", approval_state="rejected")
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_blocked_when_state_not_approved(self):
        """TC-UNIT-DlQuotation-008"""
        rec = _quo_rec(state="draft", approval_state="not_required")
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_gb06_gap_ignores_unconfirmed_bom_on_lines(self):
        """TC-UNIT-DlQuotation-020"""
        # GB-06 chỉ enforce ở _validate_line lúc tạo báo giá từ RFQ
        # (quotation_pricing_service.py) — action_send() không hề đọc
        # line_ids/bom_id, nên báo giá có dòng BOM chưa Confirmed vẫn gửi
        # được bình thường nếu đã qua được action_approve. Test này khoá lại
        # hiện trạng (gap), không phải hành vi mong muốn theo PRD (GB-06/GB-16).
        line = SimpleNamespace(bom_id=SimpleNamespace(status="draft"))
        rec = _quo_rec(state="approved", approval_state="not_required", line_ids=[line])
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")  # không raise dù BOM dòng chưa Confirmed


class TestActionCustomerAccept(unittest.TestCase):
    def test_happy_sent_to_accepted(self):
        """TC-UNIT-DlQuotation-009"""
        rec = _quo_rec(state="sent")
        DlQuotation.action_customer_accept(_RS([rec]))
        self.assertEqual(rec.state, "accepted")

    def test_blocked_when_state_not_sent(self):
        """TC-UNIT-DlQuotation-010"""
        rec = _quo_rec(state="approved")
        with self.assertRaises(UserError):
            DlQuotation.action_customer_accept(_RS([rec]))


class TestActionResetDraft(unittest.TestCase):
    """GB-01 ("1 chiều") gap: action_reset_draft() không có guard nào trong
    Python — chỉ ẩn nút ở UI (quotation_views.xml) khi state không thuộc
    approved/sent/rejected. Test dưới đây khoá lại đúng hiện trạng code thật,
    không phải hành vi PRD mong muốn."""

    def test_callable_from_ordered_state_gb01_gap(self):
        """TC-UNIT-DlQuotation-011"""
        rec = _quo_rec(state="ordered")
        DlQuotation.action_reset_draft(_RS([rec]))
        self.assertEqual(rec.state, "draft")  # không raise — đúng gap GB-01

    def test_callable_from_cancelled_state_gb01_gap(self):
        """TC-UNIT-DlQuotation-012"""
        rec = _quo_rec(state="cancelled")
        DlQuotation.action_reset_draft(_RS([rec]))
        self.assertEqual(rec.state, "draft")  # không raise — đúng gap GB-01


class TestActionReject(unittest.TestCase):
    def test_no_pending_request_just_sets_rejected(self):
        """TC-UNIT-DlQuotation-013"""
        rec = _quo_rec(state="sent", approval_request_id=None)
        DlQuotation.action_reject(_RS([rec]))
        self.assertEqual(rec.state, "rejected")

    def test_pending_request_gets_cancelled(self):
        """TC-UNIT-DlQuotation-014"""
        req = Mock(state="pending")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation.action_reject(_RS([rec]))
        req.action_cancel_on_change.assert_called_once()
        self.assertEqual(rec.state, "rejected")

    def test_non_pending_request_not_cancelled(self):
        """TC-UNIT-DlQuotation-015"""
        req = Mock(state="approved")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation.action_reject(_RS([rec]))
        req.action_cancel_on_change.assert_not_called()
        self.assertEqual(rec.state, "rejected")


class TestActionOpenApprovalRequest(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlQuotation-016"""
        rec = _quo_rec(approval_request_id=SimpleNamespace(id=42))
        action = DlQuotation.action_open_approval_request(rec)
        self.assertEqual(action["res_id"], 42)
        self.assertEqual(action["res_model"], "dl.pricing.approval.request")

    def test_no_request_raises(self):
        """TC-UNIT-DlQuotation-017"""
        rec = _quo_rec(approval_request_id=None)
        with self.assertRaises(UserError):
            DlQuotation.action_open_approval_request(rec)


class TestActionOpenSaleOrder(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlQuotation-018"""
        rec = _quo_rec(sale_order_id=SimpleNamespace(id=7))
        action = DlQuotation.action_open_sale_order(rec)
        self.assertEqual(action["res_id"], 7)
        self.assertEqual(action["res_model"], "dl.sale.order")

    def test_no_sale_order_raises(self):
        """TC-UNIT-DlQuotation-019"""
        rec = _quo_rec(sale_order_id=None)
        with self.assertRaises(UserError):
            DlQuotation.action_open_sale_order(rec)


if __name__ == "__main__":
    unittest.main()
