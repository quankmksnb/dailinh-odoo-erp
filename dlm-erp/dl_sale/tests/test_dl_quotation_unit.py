"""Unit test L1 (thuần, không ORM/DB) cho dl.quotation / dl.quotation.line.
Sheet nguồn: DlQuotation, DlQuotationLine trong Report_5_1_UnitTests_L1.xlsx.
"""
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.exceptions import UserError, ValidationError

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
    (đọc field từng bản ghi), `self.field = x` broadcast xuống MỌI bản ghi
    (đúng ngữ nghĩa gán field ở cấp recordset thật của Odoo, vd
    `action_send()` làm `self.state = 'sent'` sau vòng lặp kiểm tra), và
    `self.write(vals)` (action_send/action_customer_accept/_apply_reject đều
    dùng self.write thay vì gán field trực tiếp)."""

    # _apply_reject() đọc self._fields['reject_reason'].selection để lấy
    # nhãn hiển thị — mượn nguyên danh sách selection thật từ dl_quotation.py
    # (reject_reason field) để không lệch khi field đổi.
    # _apply_reject() đọc self._REJECTABLE_STATES — mượn nguyên tuple thật.
    _REJECTABLE_STATES = ('draft', 'approved', 'sent', 'revision_requested')
    # _compute_validity_state()/action_expire() đọc self._EXPIRABLE_STATES.
    _EXPIRABLE_STATES = ('approved', 'sent', 'revision_requested')

    _fields = {
        "reject_reason": SimpleNamespace(selection=[
            ('price_high', 'Giá cao'),
            ('lead_time', 'Thời gian giao hàng lâu'),
            ('tech_not_met', 'Không đáp ứng kỹ thuật'),
            ('chose_competitor', 'Khách chọn nhà cung cấp khác'),
            ('demand_cancelled', 'Khách hủy nhu cầu'),
            ('no_contact', 'Không liên hệ được'),
            ('other', 'Lý do khác'),
        ]),
    }

    def __init__(self, records):
        object.__setattr__(self, "_records", list(records))

    def __iter__(self):
        return iter(self._records)

    def __setattr__(self, name, value):
        for r in self._records:
            setattr(r, name, value)

    def write(self, vals):
        for r in self._records:
            for k, v in vals.items():
                setattr(r, k, v)


def _quo_rec(**kwargs):
    rec = SimpleNamespace(
        state="draft", approval_state="not_required", approval_level="",
        approval_request_id=None, sale_order_id=None, name="BG0001",
        # action_send() cần approval_required (nhánh Nháp) và validity_date
        # (đặt hạn hiệu lực mặc định nếu chưa có) — cho giá trị "đã có sẵn"
        # để khỏi phải mock self.env._default_validity_date() ở tầng L1.
        approval_required=False, validity_date="2026-12-31",
        message_post=lambda **kw: None,
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

    def test_blocked_when_draft_and_approval_required(self):
        """TC-UNIT-DlQuotation-008 — quyết định 2026-07-24: Nháp chỉ gửi
        thẳng được khi THỰC SỰ không cần duyệt; còn cần duyệt thì phải chặn."""
        rec = _quo_rec(state="draft", approval_required=True)
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_draft_send_allowed_when_no_approval_needed(self):
        """TC-UNIT-DlQuotation-008a — cùng quyết định trên: báo giá Nháp dưới
        ngưỡng (approval_required=False, approval_state=not_required) được
        gửi THẲNG cho khách, không bắt phải qua trạng thái 'Đã duyệt' trước."""
        rec = _quo_rec(state="draft", approval_state="not_required", approval_required=False)
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")

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
    """GB-01 ("1 chiều"): action_reset_draft() giờ ĐÃ có guard ở tầng Python
    (chỉ cho về Nháp từ approved/sent/revision_requested/rejected/expired) —
    trước đây (bản test cũ) chỉ ẩn nút ở UI, không chặn ở Python, 2 test dưới
    đây khi đó khoá lại đúng "gap". Gap đã được vá (xem dl_quotation.py
    action_reset_draft) nên nay đổi thành test bảo vệ hành vi chặn đúng,
    không còn là gap."""

    def test_blocked_from_ordered_state(self):
        """TC-UNIT-DlQuotation-011"""
        rec = _quo_rec(state="ordered")
        with self.assertRaises(UserError):
            DlQuotation.action_reset_draft(_RS([rec]))

    def test_blocked_from_cancelled_state(self):
        """TC-UNIT-DlQuotation-012"""
        rec = _quo_rec(state="cancelled")
        with self.assertRaises(UserError):
            DlQuotation.action_reset_draft(_RS([rec]))


class TestActionReject(unittest.TestCase):
    """action_reject() cũ đã đổi thành _apply_reject(reason, note), giờ chỉ
    gọi được qua dl.quotation.reject.wizard (wizard thu thập reason/note rồi
    gọi thẳng vào đây) — test dưới đây gọi trực tiếp _apply_reject() như
    wizard vẫn làm, không qua UI."""

    def test_no_pending_request_just_sets_rejected(self):
        """TC-UNIT-DlQuotation-013"""
        rec = _quo_rec(state="sent", approval_request_id=None)
        DlQuotation._apply_reject(_RS([rec]), "other", "Khách chọn NCC khác")
        self.assertEqual(rec.state, "rejected")

    def test_pending_request_gets_cancelled(self):
        """TC-UNIT-DlQuotation-014"""
        req = Mock(state="pending")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation._apply_reject(_RS([rec]), "price_high", "Giá cao hơn đối thủ")
        req.action_cancel_on_change.assert_called_once()
        self.assertEqual(rec.state, "rejected")

    def test_non_pending_request_not_cancelled(self):
        """TC-UNIT-DlQuotation-015"""
        req = Mock(state="approved")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation._apply_reject(_RS([rec]), "no_contact", "Không liên hệ được")
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


_TODAY = date(2026, 8, 5)


# =============================================================================
# _compute_validity_state() — dùng fields.Date.context_today(self), patch để
# không cần self.env/tz thật (kỹ thuật boundary tương tự patch.object đã dùng
# ở Priority #1/#2 cho _bom_material_cost/_resolve_value_row).
# =============================================================================
class TestComputeValidityState(unittest.TestCase):
    def test_not_expirable_state_always_ok(self):
        """TC-UNIT-DlQuotation-031"""
        rec = SimpleNamespace(state="draft", validity_date=_TODAY - timedelta(days=30))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")

    def test_overdue_when_validity_date_in_past(self):
        """TC-UNIT-DlQuotation-032"""
        rec = SimpleNamespace(state="sent", validity_date=_TODAY - timedelta(days=1))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "overdue")

    def test_soon_when_within_7_days(self):
        """TC-UNIT-DlQuotation-033"""
        rec = SimpleNamespace(state="sent", validity_date=_TODAY + timedelta(days=7))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "soon")

    def test_ok_when_more_than_7_days_left(self):
        """TC-UNIT-DlQuotation-034"""
        rec = SimpleNamespace(state="sent", validity_date=_TODAY + timedelta(days=8))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")

    def test_expirable_state_but_no_validity_date_is_ok(self):
        """TC-UNIT-DlQuotation-035"""
        rec = SimpleNamespace(state="approved", validity_date=False)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")


# =============================================================================
# _check_validity_after_order() — constraint thuần, so 2 field ngày trên self.
# =============================================================================
class TestCheckValidityAfterOrder(unittest.TestCase):
    def test_validity_before_order_date_raises(self):
        """TC-UNIT-DlQuotation-036"""
        rec = SimpleNamespace(validity_date=date(2026, 1, 1), date_order=date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            DlQuotation._check_validity_after_order([rec])

    def test_validity_equal_order_date_passes(self):
        """TC-UNIT-DlQuotation-037"""
        rec = SimpleNamespace(validity_date=date(2026, 2, 1), date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # boundary, không raise

    def test_validity_after_order_date_passes(self):
        """TC-UNIT-DlQuotation-038"""
        rec = SimpleNamespace(validity_date=date(2026, 3, 1), date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # không raise

    def test_missing_validity_date_skips_check(self):
        """TC-UNIT-DlQuotation-039"""
        rec = SimpleNamespace(validity_date=False, date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # không raise, không so sánh


# =============================================================================
# _compute_status_banner() — thuần Python + self._fields['reject_reason']
# (mượn danh sách selection thật, cùng kỹ thuật _RS._fields ở TestActionReject).
# =============================================================================
class _BannerRec(SimpleNamespace):
    _fields = {
        "reject_reason": SimpleNamespace(selection=[
            ('price_high', 'Giá cao'), ('lead_time', 'Thời gian giao hàng lâu'),
            ('tech_not_met', 'Không đáp ứng kỹ thuật'),
            ('chose_competitor', 'Khách chọn nhà cung cấp khác'),
            ('demand_cancelled', 'Khách hủy nhu cầu'), ('no_contact', 'Không liên hệ được'),
            ('other', 'Lý do khác'),
        ]),
    }

    def __init__(self, **kw):
        base = dict(state="draft", approval_required=False, approval_state="not_required",
                    approval_level="", approval_reasons="", reject_reason=False,
                    reject_reason_note=False, revision_request_type=False,
                    revision_request_note=False, line_ids=[])
        base.update(kw)
        super().__init__(**base)


class TestComputeStatusBanner(unittest.TestCase):
    def test_rejected_state(self):
        """TC-UNIT-DlQuotation-040"""
        rec = _BannerRec(state="rejected", reject_reason="price_high")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "danger")
        self.assertIn("Giá cao", rec.status_banner_message)

    def test_approval_rejected(self):
        """TC-UNIT-DlQuotation-041"""
        rec = _BannerRec(state="draft", approval_state="rejected")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "danger")

    def test_pending_approval(self):
        """TC-UNIT-DlQuotation-042"""
        rec = _BannerRec(state="draft", approval_required=True, approval_state="pending",
                          approval_level="ceo")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")
        self.assertIn("ceo", rec.status_banner_message)

    def test_expired_state(self):
        """TC-UNIT-DlQuotation-043"""
        rec = _BannerRec(state="expired")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")

    def test_revision_requested_technical(self):
        """TC-UNIT-DlQuotation-044"""
        rec = _BannerRec(state="revision_requested", revision_request_type="technical")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")
        self.assertIn("Kỹ thuật sửa BOM", rec.status_banner_message)

    def test_revision_requested_terms(self):
        """TC-UNIT-DlQuotation-045"""
        rec = _BannerRec(state="revision_requested", revision_request_type="terms")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "info")

    def test_revision_requested_price_default(self):
        """TC-UNIT-DlQuotation-046"""
        rec = _BannerRec(state="revision_requested", revision_request_type=False)
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "info")
        self.assertIn("giá / chiết khấu", rec.status_banner_message)

    def test_superseded_state(self):
        """TC-UNIT-DlQuotation-047"""
        rec = _BannerRec(state="superseded")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "secondary")

    def test_approved_ready_to_send(self):
        """TC-UNIT-DlQuotation-048"""
        rec = _BannerRec(state="draft", approval_state="approved")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "success")

    def test_draft_no_approval_needed_with_lines_ready(self):
        """TC-UNIT-DlQuotation-049"""
        rec = _BannerRec(state="draft", approval_required=False,
                          approval_state="not_required", line_ids=[object()])
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "success")
        self.assertIn("sẵn sàng gửi khách", rec.status_banner_message)

    def test_draft_no_lines_no_banner(self):
        """TC-UNIT-DlQuotation-050"""
        rec = _BannerRec(state="draft", approval_required=False,
                          approval_state="not_required", line_ids=[])
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertFalse(rec.status_banner_level)
        self.assertFalse(rec.status_banner_message)


# =============================================================================
# _compute_discount_hint() — thuần Python + self._fields['partner_group'].
# _description_selection(env) mượn/mock để không cần self.env thật.
# =============================================================================
class _HintRec(SimpleNamespace):
    _fields = {
        "partner_group": SimpleNamespace(
            _description_selection=lambda env: [
                ("new", "Khách mới"), ("existing", "Khách cũ"), ("loyal", "Khách thân thiết"),
            ]
        ),
    }

    def __init__(self, **kw):
        base = dict(state="draft", partner_group="existing", discount_default_rate=5.0,
                    discount_max_rate=15.0, discount_above_max=False,
                    discount_above_default=False, env=None)
        base.update(kw)
        super().__init__(**base)


class TestComputeDiscountHint(unittest.TestCase):
    def test_not_draft_no_hint(self):
        """TC-UNIT-DlQuotation-051"""
        rec = _HintRec(state="sent")
        DlQuotation._compute_discount_hint([rec])
        self.assertFalse(rec.discount_hint_level)
        self.assertFalse(rec.discount_hint_message)

    def test_no_partner_group_no_hint(self):
        """TC-UNIT-DlQuotation-052"""
        rec = _HintRec(state="draft", partner_group=False)
        DlQuotation._compute_discount_hint([rec])
        self.assertFalse(rec.discount_hint_level)

    def test_above_max_warning(self):
        """TC-UNIT-DlQuotation-053"""
        rec = _HintRec(discount_above_max=True)
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "warning")
        self.assertIn("vượt trần", rec.discount_hint_message)

    def test_above_default_secondary(self):
        """TC-UNIT-DlQuotation-054"""
        rec = _HintRec(discount_above_default=True)
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "secondary")

    def test_within_default_info(self):
        """TC-UNIT-DlQuotation-055"""
        rec = _HintRec()
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "info")
        self.assertIn("Khách cũ", rec.discount_hint_message)


if __name__ == "__main__":
    unittest.main()
