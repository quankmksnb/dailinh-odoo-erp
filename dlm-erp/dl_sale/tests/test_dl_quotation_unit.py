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
    """Mini stand-in cho recordset Odoo, chỉ implement .mapped() vì đó là
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
        """TC-UNIT-DlQuotation-001: báo giá có 2 dòng, chiết khấu 10%, VAT 8%.
        Tính đúng amount_untaxed, discount_amount, amount_before_vat,
        vat_amount, amount_total, total_cost, floor_amount và
        effective_markup."""
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
        """TC-UNIT-DlQuotation-002: total_cost=0 (vật tư miễn phí hoặc chưa
        có giá vốn). effective_markup phải trả về 0 thay vì chia cho 0."""
        line = SimpleNamespace(price_subtotal=50000.0, total_cost=0.0, qty=3.0, floor_price=0.0)
        rec = _quotation([line], discount_pct=0.0, vat_pct=10.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.total_cost, 0.0)
        self.assertEqual(rec.effective_markup, 0.0)

    def test_zero_discount_and_vat(self):
        """TC-UNIT-DlQuotation-003: chiết khấu và VAT đều bằng 0. discount_amount
        và vat_amount phải bằng 0, amount_total bằng đúng amount_untaxed."""
        line = SimpleNamespace(price_subtotal=20000.0, total_cost=1000.0, qty=1.0, floor_price=900.0)
        rec = _quotation([line], discount_pct=0.0, vat_pct=0.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.discount_amount, 0.0)
        self.assertEqual(rec.vat_amount, 0.0)
        self.assertEqual(rec.amount_total, 20000.0)

    def test_no_lines(self):
        """TC-UNIT-DlQuotation-004: báo giá không có dòng nào. Mọi số tiền
        tổng hợp (amount_untaxed, amount_total, effective_markup,
        floor_amount) phải trả về 0, không lỗi."""
        rec = _quotation([], discount_pct=10.0, vat_pct=8.0)
        DlQuotation._compute_amount([rec])
        self.assertEqual(rec.amount_untaxed, 0.0)
        self.assertEqual(rec.amount_total, 0.0)
        self.assertEqual(rec.effective_markup, 0.0)
        self.assertEqual(rec.floor_amount, 0.0)


class TestQuotationLineComputeSubtotal(unittest.TestCase):
    """Method _compute_subtotal() trên dl.quotation.line."""

    def test_happy(self):
        """TC-UNIT-DlQuotationLine-001: qty=10, price_unit=1500. price_subtotal
        phải bằng 15000 (qty nhân price_unit)."""
        line = SimpleNamespace(qty=10.0, price_unit=1500.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 15000.0)

    def test_zero_qty_boundary(self):
        """TC-UNIT-DlQuotationLine-002: qty=0 (biên). price_subtotal phải
        trả về 0."""
        line = SimpleNamespace(qty=0.0, price_unit=1500.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, 0.0)

    def test_negative_qty_not_guarded(self):
        """TC-UNIT-DlQuotationLine-003: qty âm (-5) không bị chặn. price_subtotal
        vẫn tính ra số âm (-500), method không guard số lượng âm."""
        line = SimpleNamespace(qty=-5.0, price_unit=100.0)
        DlQuotationLine._compute_subtotal([line])
        self.assertEqual(line.price_subtotal, -500.0)


class _RS:
    """Stand-in cho recordset Odoo nhiều bản ghi. Hỗ trợ `for rec in self`
    (đọc field từng bản ghi), `self.field = x` broadcast xuống mọi bản ghi
    (đúng ngữ nghĩa gán field ở cấp recordset thật của Odoo, ví dụ
    `action_send()` làm `self.state = 'sent'` sau vòng lặp kiểm tra), và
    `self.write(vals)` vì action_send/action_customer_accept/_apply_reject
    đều dùng self.write thay vì gán field trực tiếp."""

    # _apply_reject() đọc self._fields['reject_reason'].selection để lấy
    # nhãn hiển thị, nên mượn nguyên danh sách selection thật từ dl_quotation.py
    # (reject_reason field) để không lệch khi field đổi.
    # _apply_reject() đọc self._REJECTABLE_STATES, mượn nguyên tuple thật.
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
        # action_send() cần approval_required (nhánh nháp) và validity_date
        # (đặt hạn hiệu lực mặc định nếu chưa có), nên cho sẵn giá trị "đã có"
        # để khỏi phải mock self.env._default_validity_date() ở tầng L1.
        approval_required=False, validity_date="2026-12-31",
        message_post=lambda **kw: None,
        # action_send() (2026-08, RV-09) đọc customer_data_warning (cảnh báo
        # mềm thiếu MST/địa chỉ khách) và gọi _post_quotation_document_to_chatter()
        # (dựng PDF rồi đính vào chatter, quotation_document.py). Method đó
        # đụng self.env['ir.attachment']/self.message_post nên không test L1
        # được, phải stub no-op giống message_post ở trên.
        customer_data_warning=None,
        _post_quotation_document_to_chatter=lambda **kw: None,
        # action_create_revision() đọc self._REVISABLE_STATES (mượn nguyên
        # tuple thật). action_reopen() gọi fields.Date.context_today(self),
        # tức record._context.get('tz'), nên cho sẵn tz để khỏi chạm record.env.
        _REVISABLE_STATES=('sent', 'revision_requested', 'rejected', 'expired'),
        _context={'tz': 'UTC'},
    )
    rec.__dict__.update(kwargs)
    rec.ensure_one = lambda: rec  # action_open_approval_request/action_open_sale_order cần
    rec.write = lambda vals: rec.__dict__.update(vals)  # action_reopen() dùng self.write(...)
    # action_send() (2026-08-21+) gọi rec._dlm_check_ready_to_send() làm cổng cuối
    # trước khi gửi khách; bản gốc dl_sale không chặn gì, chỉ dl_purchase override.
    rec._dlm_check_ready_to_send = lambda: True
    # action_create_sale_order() (2026-08-21+, hạn hiệu lực) gọi
    # rec._dlm_check_pricing_fresh() trước khi lên đơn; mặc định còn hạn (không
    # chặn) — hành vi cổng chặn/không chặn đã có test riêng ở L2
    # (test_quotation_validity.py::TestQuotationValidity).
    rec._dlm_check_pricing_fresh = lambda: True
    return rec


class TestActionSend(unittest.TestCase):
    """Method action_send() (liên quan _compute_amount()), test L1 không gọi self.env."""

    def test_happy_approved_to_sent(self):
        """TC-UNIT-DlQuotation-005: báo giá đang approved, không cần duyệt
        bổ sung. action_send() phải chuyển state sang 'sent'."""
        rec = _quo_rec(state="approved", approval_state="not_required")
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")

    def test_blocked_when_approval_pending(self):
        """TC-UNIT-DlQuotation-006: báo giá đang approved nhưng approval_state
        vẫn pending (chờ duyệt bổ sung). action_send() phải raise UserError,
        chưa cho gửi."""
        rec = _quo_rec(state="approved", approval_state="pending")
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_blocked_when_approval_rejected(self):
        """TC-UNIT-DlQuotation-007: báo giá approved nhưng approval_state là
        rejected (duyệt bổ sung bị từ chối). action_send() phải raise
        UserError."""
        rec = _quo_rec(state="approved", approval_state="rejected")
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_blocked_when_draft_and_approval_required(self):
        """TC-UNIT-DlQuotation-008: theo quyết định 2026-07-24, báo giá nháp
        chỉ được gửi thẳng khi thực sự không cần duyệt; nếu cần duyệt thì
        phải chặn."""
        rec = _quo_rec(state="draft", approval_required=True)
        with self.assertRaises(UserError):
            DlQuotation.action_send(_RS([rec]))

    def test_draft_send_allowed_when_no_approval_needed(self):
        """TC-UNIT-DlQuotation-008a: cùng quyết định trên. Báo giá nháp dưới
        ngưỡng (approval_required=False, approval_state=not_required) được
        gửi thẳng cho khách, không bắt phải qua trạng thái 'đã duyệt' trước."""
        rec = _quo_rec(state="draft", approval_state="not_required", approval_required=False)
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")

    def test_gb06_gap_ignores_unconfirmed_bom_on_lines(self):
        """TC-UNIT-DlQuotation-020: báo giá approved có dòng dùng BOM chưa
        confirmed (status draft). action_send() không kiểm tra BOM của dòng
        nên vẫn chuyển state sang 'sent' bình thường (khoá lại gap hiện
        trạng, không phải hành vi mong muốn theo GB-06/GB-16)."""
        # GB-06 chỉ enforce ở _validate_line lúc tạo báo giá từ RFQ
        # (quotation_pricing_service.py). action_send() không đọc
        # line_ids/bom_id, nên báo giá có dòng BOM chưa confirmed vẫn gửi
        # được bình thường nếu đã qua action_approve. Test này khoá lại hiện
        # trạng (gap), không phải hành vi mong muốn theo PRD (GB-06/GB-16).
        line = SimpleNamespace(bom_id=SimpleNamespace(status="draft"))
        rec = _quo_rec(state="approved", approval_state="not_required", line_ids=[line])
        DlQuotation.action_send(_RS([rec]))
        self.assertEqual(rec.state, "sent")  # không raise dù BOM của dòng chưa confirmed


class TestActionCustomerAccept(unittest.TestCase):
    def test_happy_sent_to_accepted(self):
        """TC-UNIT-DlQuotation-009: báo giá đang sent, khách đồng ý.
        action_customer_accept() phải chuyển state sang 'accepted'."""
        rec = _quo_rec(state="sent")
        DlQuotation.action_customer_accept(_RS([rec]))
        self.assertEqual(rec.state, "accepted")

    def test_blocked_when_state_not_sent(self):
        """TC-UNIT-DlQuotation-010: báo giá không ở state sent (đang approved).
        action_customer_accept() phải raise UserError."""
        rec = _quo_rec(state="approved")
        with self.assertRaises(UserError):
            DlQuotation.action_customer_accept(_RS([rec]))


class TestActionResetDraft(unittest.TestCase):
    """GB-01 ("một chiều"): action_reset_draft() nay đã có guard ở tầng
    Python (chỉ cho về nháp từ approved/sent/revision_requested/rejected/
    expired). Trước đây bản test cũ chỉ ẩn nút ở UI, không chặn ở Python,
    nên 2 test dưới đây khi đó khoá lại đúng gap đó. Gap đã được vá (xem
    dl_quotation.py action_reset_draft), nay 2 test này chuyển thành test
    bảo vệ hành vi chặn đúng, không còn là gap."""

    def test_blocked_from_ordered_state(self):
        """TC-UNIT-DlQuotation-011: báo giá đang ở state ordered.
        action_reset_draft() phải raise UserError, không cho về nháp."""
        rec = _quo_rec(state="ordered")
        with self.assertRaises(UserError):
            DlQuotation.action_reset_draft(_RS([rec]))

    def test_blocked_from_cancelled_state(self):
        """TC-UNIT-DlQuotation-012: báo giá đang ở state cancelled.
        action_reset_draft() phải raise UserError, không cho về nháp."""
        rec = _quo_rec(state="cancelled")
        with self.assertRaises(UserError):
            DlQuotation.action_reset_draft(_RS([rec]))


class TestActionReject(unittest.TestCase):
    """action_reject() cũ đã đổi thành _apply_reject(reason, note), nay chỉ
    gọi được qua dl.quotation.reject.wizard (wizard thu thập reason/note rồi
    gọi thẳng vào đây). Test dưới đây gọi trực tiếp _apply_reject() như
    wizard vẫn làm, không qua UI."""

    def test_no_pending_request_just_sets_rejected(self):
        """TC-UNIT-DlQuotation-013: báo giá sent, không có approval_request_id
        (không có yêu cầu duyệt nào đang treo). _apply_reject() chỉ chuyển
        state sang 'rejected', không đụng tới request."""
        rec = _quo_rec(state="sent", approval_request_id=None)
        DlQuotation._apply_reject(_RS([rec]), "other", "Khách chọn NCC khác")
        self.assertEqual(rec.state, "rejected")

    def test_pending_request_gets_cancelled(self):
        """TC-UNIT-DlQuotation-014: báo giá sent, có approval_request_id đang
        ở state pending. _apply_reject() phải gọi
        req.action_cancel_on_change() đúng một lần và chuyển state báo giá
        sang 'rejected'."""
        req = Mock(state="pending")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation._apply_reject(_RS([rec]), "price_high", "Giá cao hơn đối thủ")
        req.action_cancel_on_change.assert_called_once()
        self.assertEqual(rec.state, "rejected")

    def test_non_pending_request_not_cancelled(self):
        """TC-UNIT-DlQuotation-015: báo giá sent, có approval_request_id
        nhưng đã ở state approved (không còn pending). _apply_reject() không
        được gọi action_cancel_on_change(), nhưng vẫn chuyển state báo giá
        sang 'rejected'."""
        req = Mock(state="approved")
        req.sudo.return_value = req
        rec = _quo_rec(state="sent", approval_request_id=req)
        DlQuotation._apply_reject(_RS([rec]), "no_contact", "Không liên hệ được")
        req.action_cancel_on_change.assert_not_called()
        self.assertEqual(rec.state, "rejected")


class TestActionOpenApprovalRequest(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlQuotation-016: báo giá có approval_request_id (id=42).
        action_open_approval_request() phải trả về action dict với res_id=42
        và res_model='dl.pricing.approval.request'."""
        rec = _quo_rec(approval_request_id=SimpleNamespace(id=42))
        action = DlQuotation.action_open_approval_request(rec)
        self.assertEqual(action["res_id"], 42)
        self.assertEqual(action["res_model"], "dl.pricing.approval.request")

    def test_no_request_raises(self):
        """TC-UNIT-DlQuotation-017: báo giá không có approval_request_id.
        action_open_approval_request() phải raise UserError."""
        rec = _quo_rec(approval_request_id=None)
        with self.assertRaises(UserError):
            DlQuotation.action_open_approval_request(rec)


class TestActionOpenSaleOrder(unittest.TestCase):
    def test_happy_returns_action_dict(self):
        """TC-UNIT-DlQuotation-018: báo giá có sale_order_id (id=7).
        action_open_sale_order() phải trả về action dict với res_id=7 và
        res_model='dl.sale.order'."""
        rec = _quo_rec(sale_order_id=SimpleNamespace(id=7))
        action = DlQuotation.action_open_sale_order(rec)
        self.assertEqual(action["res_id"], 7)
        self.assertEqual(action["res_model"], "dl.sale.order")

    def test_no_sale_order_raises(self):
        """TC-UNIT-DlQuotation-019: báo giá không có sale_order_id.
        action_open_sale_order() phải raise UserError."""
        rec = _quo_rec(sale_order_id=None)
        with self.assertRaises(UserError):
            DlQuotation.action_open_sale_order(rec)


_TODAY = date(2026, 8, 5)


# _compute_validity_state(): dùng fields.Date.context_today(self), patch để
# không cần self.env/tz thật (kỹ thuật tương tự patch.object đã dùng cho
# _bom_material_cost/_resolve_value_row).
class TestComputeValidityState(unittest.TestCase):
    def test_not_expirable_state_always_ok(self):
        """TC-UNIT-DlQuotation-031: state draft (không nằm trong
        _EXPIRABLE_STATES) dù validity_date đã quá hạn 30 ngày.
        _compute_validity_state() vẫn phải trả về 'ok' vì state không xét
        hạn."""
        rec = SimpleNamespace(state="draft", validity_date=_TODAY - timedelta(days=30))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")

    def test_overdue_when_validity_date_in_past(self):
        """TC-UNIT-DlQuotation-032: state sent (expirable), validity_date đã
        qua 1 ngày. _compute_validity_state() phải trả về 'overdue'."""
        rec = SimpleNamespace(state="sent", validity_date=_TODAY - timedelta(days=1))
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "overdue")

    def test_soon_when_within_own_threshold(self):
        """TC-UNIT-DlQuotation-033: đảo chiều 2026-08-21 (ngưỡng "sắp hết
        hạn" co theo độ dài hạn của chính báo giá, không còn cố định 7
        ngày, xem _soon_threshold()). Báo giá phát hành 6 ngày trước, hạn
        gốc 9 ngày (pricing_date -> validity_date), còn đúng 3 ngày nữa
        (ngưỡng = 9 // 3 = 3, đúng biên). _compute_validity_state() phải
        trả về 'soon'."""
        rec = SimpleNamespace(state="sent", pricing_date=_TODAY - timedelta(days=6),
                              validity_date=_TODAY + timedelta(days=3), create_date=None)
        rec.ensure_one = lambda: rec
        rec._soon_threshold = lambda: DlQuotation._soon_threshold(rec)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "soon")

    def test_ok_when_more_than_own_threshold_left(self):
        """TC-UNIT-DlQuotation-034: đảo chiều 2026-08-21, cùng lý do TC-033.
        Cùng hạn gốc 9 ngày (ngưỡng = 3) nhưng còn 4 ngày (ngoài ngưỡng).
        _compute_validity_state() phải trả về 'ok'."""
        rec = SimpleNamespace(state="sent", pricing_date=_TODAY - timedelta(days=6),
                              validity_date=_TODAY + timedelta(days=4), create_date=None)
        rec.ensure_one = lambda: rec
        rec._soon_threshold = lambda: DlQuotation._soon_threshold(rec)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")

    def test_expirable_state_but_no_validity_date_is_ok(self):
        """TC-UNIT-DlQuotation-035: state approved (expirable) nhưng chưa có
        validity_date. _compute_validity_state() phải trả về 'ok' thay vì
        lỗi khi thiếu ngày."""
        rec = SimpleNamespace(state="approved", validity_date=False)
        with patch("odoo.fields.Date.context_today", return_value=_TODAY):
            DlQuotation._compute_validity_state(_RS([rec]))
        self.assertEqual(rec.validity_state, "ok")


# _check_validity_after_order(): constraint thuần, so 2 field ngày trên self.
class TestCheckValidityAfterOrder(unittest.TestCase):
    def test_validity_before_order_date_raises(self):
        """TC-UNIT-DlQuotation-036: validity_date (1/1/2026) đứng trước
        date_order (1/2/2026). _check_validity_after_order() phải raise
        ValidationError."""
        rec = SimpleNamespace(validity_date=date(2026, 1, 1), date_order=date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            DlQuotation._check_validity_after_order([rec])

    def test_validity_equal_order_date_passes(self):
        """TC-UNIT-DlQuotation-037: validity_date bằng đúng date_order
        (biên). _check_validity_after_order() không raise."""
        rec = SimpleNamespace(validity_date=date(2026, 2, 1), date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # boundary, không raise

    def test_validity_after_order_date_passes(self):
        """TC-UNIT-DlQuotation-038: validity_date sau date_order.
        _check_validity_after_order() không raise."""
        rec = SimpleNamespace(validity_date=date(2026, 3, 1), date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # không raise

    def test_missing_validity_date_skips_check(self):
        """TC-UNIT-DlQuotation-039: chưa có validity_date.
        _check_validity_after_order() bỏ qua so sánh, không raise."""
        rec = SimpleNamespace(validity_date=False, date_order=date(2026, 2, 1))
        DlQuotation._check_validity_after_order([rec])  # không raise, không so sánh


# _compute_status_banner(): thuần Python, dùng self._fields['reject_reason']
# (mượn danh sách selection thật, cùng kỹ thuật _RS._fields ở TestActionReject).
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
                    revision_request_note=False, line_ids=[],
                    # _compute_status_banner() (2026-08-21+) đọc dlm_send_blocked
                    # (cổng chặn gửi khách chung, mặc định False ở dl_sale gốc).
                    dlm_send_blocked=False)
        base.update(kw)
        super().__init__(**base)


class TestComputeStatusBanner(unittest.TestCase):
    def test_rejected_state(self):
        """TC-UNIT-DlQuotation-040: báo giá state rejected, reject_reason
        price_high. _compute_status_banner() phải trả level 'danger' và
        message chứa nhãn lý do 'Giá cao'."""
        rec = _BannerRec(state="rejected", reject_reason="price_high")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "danger")
        self.assertIn("Giá cao", rec.status_banner_message)

    def test_approval_rejected(self):
        """TC-UNIT-DlQuotation-041: state draft nhưng approval_state là
        rejected. _compute_status_banner() phải trả level 'danger'."""
        rec = _BannerRec(state="draft", approval_state="rejected")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "danger")

    def test_pending_approval(self):
        """TC-UNIT-DlQuotation-042: state draft, cần duyệt và approval_state
        pending ở cấp ceo. _compute_status_banner() phải trả level 'warning'
        và message chứa cấp duyệt 'ceo'."""
        rec = _BannerRec(state="draft", approval_required=True, approval_state="pending",
                          approval_level="ceo")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")
        self.assertIn("ceo", rec.status_banner_message)

    def test_expired_state(self):
        """TC-UNIT-DlQuotation-043: báo giá state expired.
        _compute_status_banner() phải trả level 'warning'."""
        rec = _BannerRec(state="expired")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")

    def test_revision_requested_technical(self):
        """TC-UNIT-DlQuotation-044: state revision_requested với
        revision_request_type='technical'. _compute_status_banner() phải trả
        level 'warning' và message chứa 'Kỹ thuật sửa BOM'."""
        rec = _BannerRec(state="revision_requested", revision_request_type="technical")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "warning")
        self.assertIn("Kỹ thuật sửa BOM", rec.status_banner_message)

    def test_revision_requested_terms(self):
        """TC-UNIT-DlQuotation-045: state revision_requested với
        revision_request_type='terms'. _compute_status_banner() phải trả
        level 'info'."""
        rec = _BannerRec(state="revision_requested", revision_request_type="terms")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "info")

    def test_revision_requested_price_default(self):
        """TC-UNIT-DlQuotation-046: state revision_requested nhưng
        revision_request_type để trống (mặc định là yêu cầu về giá).
        _compute_status_banner() phải trả level 'info' và message chứa
        'giá / chiết khấu'."""
        rec = _BannerRec(state="revision_requested", revision_request_type=False)
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "info")
        self.assertIn("giá / chiết khấu", rec.status_banner_message)

    def test_superseded_state(self):
        """TC-UNIT-DlQuotation-047: báo giá state superseded.
        _compute_status_banner() phải trả level 'secondary'."""
        rec = _BannerRec(state="superseded")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "secondary")

    def test_approved_ready_to_send(self):
        """TC-UNIT-DlQuotation-048: state draft, approval_state đã approved.
        _compute_status_banner() phải trả level 'success'."""
        rec = _BannerRec(state="draft", approval_state="approved")
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "success")

    def test_draft_no_approval_needed_with_lines_ready(self):
        """TC-UNIT-DlQuotation-049: state draft, không cần duyệt
        (approval_required=False, approval_state=not_required), đã có ít
        nhất 1 dòng. _compute_status_banner() phải trả level 'success' và
        message chứa 'sẵn sàng gửi khách'."""
        rec = _BannerRec(state="draft", approval_required=False,
                          approval_state="not_required", line_ids=[object()])
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertEqual(rec.status_banner_level, "success")
        self.assertIn("sẵn sàng gửi khách", rec.status_banner_message)

    def test_draft_no_lines_no_banner(self):
        """TC-UNIT-DlQuotation-050: state draft, không cần duyệt, nhưng chưa
        có dòng nào (line_ids rỗng). _compute_status_banner() phải trả cả
        status_banner_level và status_banner_message là falsy (không hiện
        banner)."""
        rec = _BannerRec(state="draft", approval_required=False,
                          approval_state="not_required", line_ids=[])
        DlQuotation._compute_status_banner(_RS([rec]))
        self.assertFalse(rec.status_banner_level)
        self.assertFalse(rec.status_banner_message)


# _compute_discount_hint(): thuần Python, dùng self._fields['partner_group'].
# _description_selection(env) được mock để không cần self.env thật.
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
        """TC-UNIT-DlQuotation-051: báo giá không ở state draft (đang sent).
        _compute_discount_hint() phải để cả discount_hint_level và
        discount_hint_message là falsy."""
        rec = _HintRec(state="sent")
        DlQuotation._compute_discount_hint([rec])
        self.assertFalse(rec.discount_hint_level)
        self.assertFalse(rec.discount_hint_message)

    def test_no_partner_group_no_hint(self):
        """TC-UNIT-DlQuotation-052: state draft nhưng chưa chọn
        partner_group. _compute_discount_hint() phải để discount_hint_level
        là falsy."""
        rec = _HintRec(state="draft", partner_group=False)
        DlQuotation._compute_discount_hint([rec])
        self.assertFalse(rec.discount_hint_level)

    def test_above_max_warning(self):
        """TC-UNIT-DlQuotation-053: chiết khấu vượt trần (discount_above_max
        True). _compute_discount_hint() phải trả level 'warning' và message
        chứa 'vượt trần'."""
        rec = _HintRec(discount_above_max=True)
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "warning")
        self.assertIn("vượt trần", rec.discount_hint_message)

    def test_above_default_secondary(self):
        """TC-UNIT-DlQuotation-054: chiết khấu vượt mức mặc định nhưng chưa
        vượt trần (discount_above_default True). _compute_discount_hint()
        phải trả level 'secondary'."""
        rec = _HintRec(discount_above_default=True)
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "secondary")

    def test_within_default_info(self):
        """TC-UNIT-DlQuotation-055: chiết khấu trong mức mặc định, khách
        thuộc nhóm 'existing'. _compute_discount_hint() phải trả level
        'info' và message chứa nhãn nhóm khách 'Khách cũ'."""
        rec = _HintRec()
        DlQuotation._compute_discount_hint([rec])
        self.assertEqual(rec.discount_hint_level, "info")
        self.assertIn("Khách cũ", rec.discount_hint_message)


# Test cho action_approve() / action_create_sale_order() / action_create_
# revision() / action_reopen() / action_send_back_to_tech(). _ApproveRS mở
# rộng _RS thêm .env (qua object.__setattr__ để né __setattr__ broadcast
# của _RS) cho _check_internal_approver(). action_create_sale_order()/
# action_create_revision() dùng _quo_rec() + _RS sẵn có, chỉ cần thêm
# self.env["dl.sale.order"].search khi chạm nhánh đó.
class _ApproveRS(_RS):
    def __init__(self, records, env):
        super().__init__(records)
        object.__setattr__(self, "env", env)

    def _check_internal_approver(self):
        return DlQuotation._check_internal_approver(self)

    def sudo(self):
        return self


def _approver_env(allowed):
    user = SimpleNamespace(has_group=lambda g: allowed)
    return SimpleNamespace(su=False, user=user)


class TestActionApprove(unittest.TestCase):
    def test_non_approver_role_raises(self):
        """TC-UNIT-DlQuotation-056: user gọi action_approve() không thuộc
        nhóm được phép duyệt (has_group trả False). action_approve() phải
        raise UserError."""
        rec = _quo_rec(state="draft")
        rs = _ApproveRS([rec], _approver_env(allowed=False))
        with self.assertRaises(UserError):
            DlQuotation.action_approve(rs)

    def test_non_draft_raises(self):
        """TC-UNIT-DlQuotation-057: báo giá không ở state draft (đang sent),
        user có quyền duyệt. action_approve() phải raise UserError."""
        rec = _quo_rec(state="sent")
        rs = _ApproveRS([rec], _approver_env(allowed=True))
        with self.assertRaises(UserError):
            DlQuotation.action_approve(rs)

    def test_approval_pending_raises(self):
        """TC-UNIT-DlQuotation-058: state draft, user có quyền duyệt nhưng
        approval_state vẫn pending ở cấp sales_manager (chưa duyệt xong ở
        cấp đó). action_approve() phải raise UserError."""
        rec = _quo_rec(state="draft", approval_state="pending",
                        approval_level="sales_manager")
        rs = _ApproveRS([rec], _approver_env(allowed=True))
        with self.assertRaises(UserError):
            DlQuotation.action_approve(rs)

    def test_approval_rejected_raises(self):
        """TC-UNIT-DlQuotation-059: state draft, user có quyền duyệt nhưng
        approval_state là rejected. action_approve() phải raise UserError."""
        rec = _quo_rec(state="draft", approval_state="rejected")
        rs = _ApproveRS([rec], _approver_env(allowed=True))
        with self.assertRaises(UserError):
            DlQuotation.action_approve(rs)

    def test_happy_sets_state_approved(self):
        """Báo giá state draft, approval_state not_required (không cần duyệt),
        user có quyền duyệt. action_approve() phải đổi state thành approved."""
        rec = _quo_rec(state="draft", approval_state="not_required")
        rs = _ApproveRS([rec], _approver_env(allowed=True))
        DlQuotation.action_approve(rs)
        self.assertEqual(rec.state, "approved")


class TestActionCreateSaleOrder(unittest.TestCase):
    def test_not_accepted_raises(self):
        """TC-UNIT-DlQuotation-060: báo giá chưa được khách accepted (đang
        sent). action_create_sale_order() phải raise UserError."""
        rec = _quo_rec(state="sent")
        with self.assertRaises(UserError):
            DlQuotation.action_create_sale_order(rec)

    def test_existing_order_reused_sets_state_ordered(self):
        """TC-UNIT-DlQuotation-061: nếu đơn đã tồn tại (ví dụ tạo từ phiên
        trước rồi báo giá bị reset) thì không tạo đơn mới, chỉ khoá lại
        state."""
        existing_order = SimpleNamespace(id=99)
        sale_order_model = SimpleNamespace(
            search=lambda domain, limit=None: existing_order,
            create=lambda vals: (_ for _ in ()).throw(
                AssertionError("must not create a new order when one exists")))
        rec = _quo_rec(state="accepted", id=1,
                        env={"dl.sale.order": sale_order_model})
        DlQuotation.action_create_sale_order(rec)
        self.assertEqual(rec.state, "ordered")


class TestActionCreateRevision(unittest.TestCase):
    def test_non_revisable_state_raises(self):
        """TC-UNIT-DlQuotation-062: báo giá ở state draft, không nằm trong
        _REVISABLE_STATES (sent/revision_requested/rejected/expired).
        action_create_revision() phải raise UserError."""
        rec = _quo_rec(state="draft")
        with self.assertRaises(UserError):
            DlQuotation.action_create_revision(rec)


class TestActionReopen(unittest.TestCase):
    def test_non_expired_raises(self):
        """TC-UNIT-DlQuotation-063: báo giá không ở state expired (đang
        sent). action_reopen() phải raise UserError."""
        rec = _quo_rec(state="sent")
        with self.assertRaises(UserError):
            DlQuotation.action_reopen(rec)

    def test_missing_future_validity_date_raises(self):
        """TC-UNIT-DlQuotation-064: báo giá expired nhưng chưa có
        validity_date mới trong tương lai (validity_date=False).
        action_reopen() phải raise UserError."""
        rec = _quo_rec(state="expired", validity_date=False)
        with self.assertRaises(UserError):
            DlQuotation.action_reopen(rec)

    def test_happy_reopens_to_sent(self):
        """Báo giá state expired nhưng đã có validity_date mới trong tương
        lai. action_reopen() phải đổi state về sent."""
        rec = _quo_rec(state="expired", validity_date=date(2030, 1, 1))
        DlQuotation.action_reopen(rec)
        self.assertEqual(rec.state, "sent")


class TestActionSendBackToTech(unittest.TestCase):
    def test_no_source_rfq_raises(self):
        """TC-UNIT-DlQuotation-065: báo giá revision_requested nhưng không
        có quotation_request_id (không có RFQ nguồn để gửi lại kỹ thuật).
        action_send_back_to_tech() phải raise UserError."""
        rec = _quo_rec(state="revision_requested", quotation_request_id=False)
        with self.assertRaises(UserError):
            DlQuotation.action_send_back_to_tech(rec)

    def test_wrong_state_raises(self):
        """Báo giá state draft (không phải revision_requested), có RFQ
        nguồn. action_send_back_to_tech() chỉ dùng được ở state
        revision_requested nên phải raise UserError."""
        rfq = SimpleNamespace(action_reopen_for_revision=lambda **kw: None,
                               name="RFQ0001")
        rec = _quo_rec(state="draft", quotation_request_id=rfq)
        with self.assertRaises(UserError):
            DlQuotation.action_send_back_to_tech(rec)


if __name__ == "__main__":
    unittest.main()
