# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.quotation.request /
dl.quotation.request.line. Sheet nguồn: DlQuotationRequest,
DlQuotationRequestLine.

Chỉ test compute/constraint thuần Python, không đụng self.env. Các method
dùng self.env (_compute_received_info, _compute_is_technician,
_check_product_has_bom, write, action_receive, action_cancel...) là L2,
không test ở đây.
"""
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import ValidationError

from ..models.dl_quotation_request import DlQuotationRequest, DlQuotationRequestLine


class FakeLineRS(list):
    """Mini stand-in cho recordset dl.quotation.request.line — hỗ trợ
    .filtered()/.mapped() vì đó là 2 API mà các method header cần trên
    line_ids, không kéo theo self.env/ORM."""

    def filtered(self, func):
        return FakeLineRS(x for x in self if func(x))

    def mapped(self, field):
        return [getattr(rec, field) for rec in self]

    def __bool__(self):
        return len(self) > 0


class _RQS(list):
    """Stand-in cho recordset RFQ — hỗ trợ for rec in self + set self._TECH_
    STAGE_BY_STATUS/_OPEN_DEADLINE_STATES (đọc ở cấp self, mượn nguyên hằng
    thật để không lệch khi code đổi)."""

    _TECH_STAGE_BY_STATUS = DlQuotationRequest._TECH_STAGE_BY_STATUS
    _OPEN_DEADLINE_STATES = DlQuotationRequest._OPEN_DEADLINE_STATES


def _line(**kw):
    base = dict(is_infeasible=False, resolved_product_id=None, resolved_bom_id=None,
                needs_review=False, product_type="manufactured", supplement_note=False,
                supplement_done=False, quantity=1.0, product_name="", quotation_request_id=None,
                infeasible_reason=False, id=1)
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec.ensure_one = lambda: rec
    # _recompute_status_from_lines() gọi line._is_resolved() trên từng dòng —
    # mượn nguyên method thật (đã test riêng ở TestIsResolved) thay vì suy
    # đoán lại logic ở đây.
    rec._is_resolved = lambda: DlQuotationRequestLine._is_resolved(rec)
    return rec


def _rfq(**kw):
    base = dict(status="new", line_ids=FakeLineRS(), return_reason=False, deadline=False,
                requested_date=False, received_by=None)
    base.update(kw)
    return SimpleNamespace(**base)


# =============================================================================
# DlQuotationRequestLine — compute/constraint thuần
# =============================================================================
class TestComputePriceSubtotal(unittest.TestCase):
    def test_happy(self):
        """TC-UNIT-DlQuotationRequestLine-001"""
        line = _line(product_price=1500.0, quantity=10.0)
        DlQuotationRequestLine._compute_price_subtotal([line])
        self.assertEqual(line.price_subtotal, 15000.0)

    def test_missing_price_treated_as_zero(self):
        """TC-UNIT-DlQuotationRequestLine-002"""
        line = _line(product_price=False, quantity=10.0)
        DlQuotationRequestLine._compute_price_subtotal([line])
        self.assertEqual(line.price_subtotal, 0.0)


class TestComputeTechnicalStatus(unittest.TestCase):
    def test_trading_not_required(self):
        """TC-UNIT-DlQuotationRequestLine-003"""
        line = _line(product_type="trading")
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "not_required")

    def test_infeasible(self):
        """TC-UNIT-DlQuotationRequestLine-004"""
        line = _line(is_infeasible=True)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "infeasible")

    def test_resolved_needs_review(self):
        """TC-UNIT-DlQuotationRequestLine-005"""
        line = _line(resolved_product_id=SimpleNamespace(id=1),
                     resolved_bom_id=SimpleNamespace(id=2), needs_review=True)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "review")

    def test_resolved_done(self):
        """TC-UNIT-DlQuotationRequestLine-006"""
        line = _line(resolved_product_id=SimpleNamespace(id=1),
                     resolved_bom_id=SimpleNamespace(id=2), needs_review=False)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "done")

    def test_supplement_waiting(self):
        """TC-UNIT-DlQuotationRequestLine-007"""
        line = _line(supplement_note="cần thêm ảnh", supplement_done=False)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "waiting")

    def test_supplement_supplemented(self):
        """TC-UNIT-DlQuotationRequestLine-008"""
        line = _line(supplement_note="cần thêm ảnh", supplement_done=True)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "supplemented")

    def test_supplement_done_note_cleared(self):
        """TC-UNIT-DlQuotationRequestLine-009"""
        line = _line(supplement_note=False, supplement_done=True)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "supplemented")

    def test_partially_processing(self):
        """TC-UNIT-DlQuotationRequestLine-010"""
        line = _line(resolved_product_id=SimpleNamespace(id=1), resolved_bom_id=None)
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "processing")

    def test_pending_default(self):
        """TC-UNIT-DlQuotationRequestLine-011"""
        line = _line()
        DlQuotationRequestLine._compute_technical_status([line])
        self.assertEqual(line.technical_status, "pending")


class TestIsResolved(unittest.TestCase):
    def test_infeasible_is_resolved(self):
        """TC-UNIT-DlQuotationRequestLine-012"""
        line = _line(is_infeasible=True)
        self.assertTrue(DlQuotationRequestLine._is_resolved(line))

    def test_no_product_not_resolved(self):
        """TC-UNIT-DlQuotationRequestLine-013"""
        line = _line(resolved_product_id=None)
        self.assertFalse(DlQuotationRequestLine._is_resolved(line))

    def test_needs_review_not_resolved(self):
        """TC-UNIT-DlQuotationRequestLine-014"""
        line = _line(resolved_product_id=SimpleNamespace(id=1), needs_review=True)
        self.assertFalse(DlQuotationRequestLine._is_resolved(line))

    def test_trading_with_product_resolved(self):
        """TC-UNIT-DlQuotationRequestLine-015"""
        line = _line(product_type="trading", resolved_product_id=SimpleNamespace(id=1))
        self.assertTrue(DlQuotationRequestLine._is_resolved(line))

    def test_manufactured_needs_bom(self):
        """TC-UNIT-DlQuotationRequestLine-016"""
        line = _line(product_type="manufactured", resolved_product_id=SimpleNamespace(id=1),
                     resolved_bom_id=None)
        self.assertFalse(DlQuotationRequestLine._is_resolved(line))

    def test_manufactured_with_bom_resolved(self):
        """TC-UNIT-DlQuotationRequestLine-017"""
        line = _line(product_type="manufactured", resolved_product_id=SimpleNamespace(id=1),
                     resolved_bom_id=SimpleNamespace(id=2))
        self.assertTrue(DlQuotationRequestLine._is_resolved(line))


class TestCheckQuantity(unittest.TestCase):
    def test_zero_raises(self):
        """TC-UNIT-DlQuotationRequestLine-018"""
        line = _line(quantity=0.0)
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_quantity([line])

    def test_negative_raises(self):
        """TC-UNIT-DlQuotationRequestLine-019"""
        line = _line(quantity=-1.0)
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_quantity([line])

    def test_positive_passes(self):
        """TC-UNIT-DlQuotationRequestLine-020"""
        line = _line(quantity=5.0)
        DlQuotationRequestLine._check_quantity([line])  # không raise


class TestCheckResolvedBom(unittest.TestCase):
    def test_no_bom_skips(self):
        """TC-UNIT-DlQuotationRequestLine-021"""
        line = _line(resolved_bom_id=None)
        DlQuotationRequestLine._check_resolved_bom([line])  # không raise

    def test_trading_with_bom_raises(self):
        """TC-UNIT-DlQuotationRequestLine-022"""
        line = _line(product_type="trading", resolved_bom_id=SimpleNamespace(
            product_id=SimpleNamespace(id=1), status="confirmed"))
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_resolved_bom([line])

    def test_bom_product_mismatch_raises(self):
        """TC-UNIT-DlQuotationRequestLine-023"""
        product_a = SimpleNamespace(id=1)
        product_b = SimpleNamespace(id=2)
        line = _line(product_type="manufactured", resolved_product_id=product_a,
                     resolved_bom_id=SimpleNamespace(product_id=product_b, status="confirmed"))
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_resolved_bom([line])

    def test_bom_not_confirmed_raises(self):
        """TC-UNIT-DlQuotationRequestLine-024"""
        product_a = SimpleNamespace(id=1)
        line = _line(product_type="manufactured", resolved_product_id=product_a,
                     resolved_bom_id=SimpleNamespace(product_id=product_a, status="draft"))
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_resolved_bom([line])

    def test_happy_confirmed_bom_matching_product_passes(self):
        """TC-UNIT-DlQuotationRequestLine-025"""
        product_a = SimpleNamespace(id=1)
        line = _line(product_type="manufactured", resolved_product_id=product_a,
                     resolved_bom_id=SimpleNamespace(product_id=product_a, status="locked"))
        DlQuotationRequestLine._check_resolved_bom([line])  # không raise


class TestCheckProductTypeRequired(unittest.TestCase):
    def test_trading_without_product_raises(self):
        """TC-UNIT-DlQuotationRequestLine-026"""
        line = _line(product_type="trading", resolved_product_id=None)
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_product_type_required([line])

    def test_manufactured_without_name_raises(self):
        """TC-UNIT-DlQuotationRequestLine-027"""
        line = _line(product_type="manufactured", product_name="")
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_product_type_required([line])

    def test_trading_with_product_passes(self):
        """TC-UNIT-DlQuotationRequestLine-028"""
        line = _line(product_type="trading", resolved_product_id=SimpleNamespace(id=1))
        DlQuotationRequestLine._check_product_type_required([line])  # không raise

    def test_manufactured_with_name_passes(self):
        """TC-UNIT-DlQuotationRequestLine-029"""
        line = _line(product_type="manufactured", product_name="Khung thép A")
        DlQuotationRequestLine._check_product_type_required([line])  # không raise


class TestCheckUniqueNameInRequest(unittest.TestCase):
    def test_duplicate_name_raises(self):
        """TC-UNIT-DlQuotationRequestLine-030"""
        rfq = SimpleNamespace()
        l1 = _line(id=1, product_type="manufactured", product_name="Khung thép A")
        l2 = _line(id=2, product_type="manufactured", product_name="khung thép a  ")
        rfq.line_ids = FakeLineRS([l1, l2])
        l1.quotation_request_id = rfq
        l2.quotation_request_id = rfq
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_unique_name_in_request([l1])

    def test_trading_type_exempt(self):
        """TC-UNIT-DlQuotationRequestLine-031"""
        line = _line(product_type="trading", product_name="")
        DlQuotationRequestLine._check_unique_name_in_request([line])  # không raise

    def test_unique_name_passes(self):
        """TC-UNIT-DlQuotationRequestLine-032"""
        rfq = SimpleNamespace()
        l1 = _line(id=1, product_type="manufactured", product_name="Khung thép A")
        l2 = _line(id=2, product_type="manufactured", product_name="Khung thép B")
        rfq.line_ids = FakeLineRS([l1, l2])
        l1.quotation_request_id = rfq
        l2.quotation_request_id = rfq
        DlQuotationRequestLine._check_unique_name_in_request([l1])  # không raise


class TestCheckResolution(unittest.TestCase):
    def test_both_product_and_infeasible_raises(self):
        """TC-UNIT-DlQuotationRequestLine-033"""
        line = _line(resolved_product_id=SimpleNamespace(id=1), is_infeasible=True)
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_resolution([line])

    def test_only_product_passes(self):
        """TC-UNIT-DlQuotationRequestLine-034"""
        line = _line(resolved_product_id=SimpleNamespace(id=1), is_infeasible=False)
        DlQuotationRequestLine._check_resolution([line])  # không raise


class TestCheckInfeasibleReason(unittest.TestCase):
    def test_infeasible_without_reason_raises(self):
        """TC-UNIT-DlQuotationRequestLine-035"""
        line = _line(is_infeasible=True, infeasible_reason=False)
        with self.assertRaises(ValidationError):
            DlQuotationRequestLine._check_infeasible_reason([line])

    def test_infeasible_with_reason_passes(self):
        """TC-UNIT-DlQuotationRequestLine-036"""
        line = _line(is_infeasible=True, infeasible_reason="Không đủ máy móc")
        DlQuotationRequestLine._check_infeasible_reason([line])  # không raise


# =============================================================================
# DlQuotationRequest — compute/constraint thuần header
# =============================================================================
class TestComputeSupplementCount(unittest.TestCase):
    def test_counts_waiting_and_ready(self):
        """TC-UNIT-DlQuotationRequest-001"""
        waiting = _line(supplement_note="a", supplement_done=False)
        ready = _line(supplement_note="b", supplement_done=True)
        untouched = _line(supplement_note=False)
        rec = _rfq(line_ids=FakeLineRS([waiting, ready, untouched]))
        DlQuotationRequest._compute_supplement_count([rec])
        self.assertEqual(rec.supplement_count, 1)
        self.assertEqual(rec.supplement_ready_count, 1)


class TestComputeInfeasibleStats(unittest.TestCase):
    def test_partial_infeasible(self):
        """TC-UNIT-DlQuotationRequest-002"""
        l1 = _line(is_infeasible=True)
        l2 = _line(is_infeasible=False)
        rec = _rfq(line_ids=FakeLineRS([l1, l2]))
        DlQuotationRequest._compute_infeasible_stats([rec])
        self.assertEqual(rec.infeasible_count, 1)
        self.assertFalse(rec.all_infeasible)

    def test_all_infeasible(self):
        """TC-UNIT-DlQuotationRequest-003"""
        l1 = _line(is_infeasible=True)
        l2 = _line(is_infeasible=True)
        rec = _rfq(line_ids=FakeLineRS([l1, l2]))
        DlQuotationRequest._compute_infeasible_stats([rec])
        self.assertTrue(rec.all_infeasible)

    def test_no_lines_not_all_infeasible(self):
        """TC-UNIT-DlQuotationRequest-004"""
        rec = _rfq(line_ids=FakeLineRS([]))
        DlQuotationRequest._compute_infeasible_stats([rec])
        self.assertFalse(rec.all_infeasible)


class TestComputeTechnicalProgress(unittest.TestCase):
    def test_no_manufactured_lines(self):
        """TC-UNIT-DlQuotationRequest-005"""
        rec = _rfq(line_ids=FakeLineRS([_line(product_type="trading")]))
        DlQuotationRequest._compute_technical_progress([rec])
        self.assertEqual(rec.technical_total_line_count, 0)
        self.assertEqual(rec.technical_progress_label, "Không có dòng gia công cần xử lý")

    def test_partial_progress_with_infeasible_noted(self):
        """TC-UNIT-DlQuotationRequest-006"""
        done = _line(product_type="manufactured", resolved_product_id=SimpleNamespace(id=1),
                     resolved_bom_id=SimpleNamespace(id=2))
        infeasible = _line(product_type="manufactured", is_infeasible=True)
        pending = _line(product_type="manufactured")
        rec = _rfq(line_ids=FakeLineRS([done, infeasible, pending]))
        DlQuotationRequest._compute_technical_progress([rec])
        self.assertEqual(rec.technical_total_line_count, 3)
        self.assertEqual(rec.technical_done_line_count, 2)
        self.assertAlmostEqual(rec.technical_progress_percent, 200.0 / 3)
        self.assertIn("2/3", rec.technical_progress_label)
        self.assertIn("1 không khả thi", rec.technical_progress_label)


class TestComputeDeadlineState(unittest.TestCase):
    _TODAY = date(2026, 8, 5)

    def test_open_state_overdue(self):
        """TC-UNIT-DlQuotationRequest-007"""
        rec = _rfq(status="processing", deadline=self._TODAY - timedelta(days=1))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            DlQuotationRequest._compute_deadline_state(_RQS([rec]))
        self.assertEqual(rec.deadline_state, "overdue")

    def test_open_state_soon(self):
        """TC-UNIT-DlQuotationRequest-008"""
        rec = _rfq(status="new", deadline=self._TODAY + timedelta(days=5))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            DlQuotationRequest._compute_deadline_state(_RQS([rec]))
        self.assertEqual(rec.deadline_state, "soon")

    def test_closed_state_always_ok(self):
        """TC-UNIT-DlQuotationRequest-009"""
        rec = _rfq(status="quoted", deadline=self._TODAY - timedelta(days=30))
        with patch("odoo.fields.Date.context_today", return_value=self._TODAY):
            DlQuotationRequest._compute_deadline_state(_RQS([rec]))
        self.assertEqual(rec.deadline_state, "ok")


class TestComputeTechStage(unittest.TestCase):
    def test_new_pending(self):
        """TC-UNIT-DlQuotationRequest-010"""
        rec = _rfq(status="new", received_by=None)
        DlQuotationRequest._compute_tech_stage(_RQS([rec]))
        self.assertEqual(rec.tech_stage, "pending")

    def test_new_but_already_received_is_processing(self):
        """TC-UNIT-DlQuotationRequest-011 — RFQ trả lại bổ sung, Sales gửi lại,
        KTV cũ đã tiếp nhận trước đó -> giữ 'Đang xử lý', không lùi Chưa nhận."""
        rec = _rfq(status="supplemented", received_by=SimpleNamespace(id=3))
        DlQuotationRequest._compute_tech_stage(_RQS([rec]))
        self.assertEqual(rec.tech_stage, "processing")

    def test_returned_is_waiting_sales(self):
        """TC-UNIT-DlQuotationRequest-012"""
        rec = _rfq(status="returned")
        DlQuotationRequest._compute_tech_stage(_RQS([rec]))
        self.assertEqual(rec.tech_stage, "waiting_sales")

    def test_cancelled_is_closed(self):
        """TC-UNIT-DlQuotationRequest-013"""
        rec = _rfq(status="cancelled")
        DlQuotationRequest._compute_tech_stage(_RQS([rec]))
        self.assertEqual(rec.tech_stage, "closed")


class TestCheckDeadline(unittest.TestCase):
    def test_deadline_before_requested_date_raises(self):
        """TC-UNIT-DlQuotationRequest-014"""
        rec = _rfq(deadline=date(2026, 1, 1), requested_date=date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            DlQuotationRequest._check_deadline([rec])

    def test_no_deadline_skips(self):
        """TC-UNIT-DlQuotationRequest-015"""
        rec = _rfq(deadline=False, requested_date=date(2026, 2, 1))
        DlQuotationRequest._check_deadline([rec])  # không raise

    def test_deadline_after_requested_date_passes(self):
        """TC-UNIT-DlQuotationRequest-016"""
        rec = _rfq(deadline=date(2026, 3, 1), requested_date=date(2026, 2, 1))
        DlQuotationRequest._check_deadline([rec])  # không raise


# =============================================================================
# _recompute_status_from_lines() — core state machine của RFQ (§1.6 issue #11
# đã dẫn chứng khác biệt PRD/code cho dl.quotation; đây là state machine RIÊNG
# của RFQ, đã khớp GB-25/PRD nhưng CHƯA có test tự động nào trước bản này).
# =============================================================================
class TestRecomputeStatusFromLines(unittest.TestCase):
    def test_closed_states_never_change(self):
        """TC-UNIT-DlQuotationRequest-017"""
        rec = _rfq(status="quoted", line_ids=FakeLineRS([_line(is_infeasible=True)]))
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.status, "quoted")

    def test_all_lines_resolved_becomes_confirmed(self):
        """TC-UNIT-DlQuotationRequest-018"""
        l1 = _line(is_infeasible=True)
        l2 = _line(product_type="trading", resolved_product_id=SimpleNamespace(id=1))
        rec = _rfq(status="processing", line_ids=FakeLineRS([l1, l2]))
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.status, "confirmed")

    def test_all_unresolved_waiting_supplement_becomes_returned(self):
        """TC-UNIT-DlQuotationRequest-019"""
        l1 = _line(supplement_note="cần thêm ảnh", product_name="SP A")
        rec = _rfq(status="processing", line_ids=FakeLineRS([l1]))
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.status, "returned")
        self.assertIn("SP A", rec.return_reason)
        self.assertIn("cần thêm ảnh", rec.return_reason)

    def test_partial_progress_stays_processing(self):
        """TC-UNIT-DlQuotationRequest-020"""
        l1 = _line(resolved_product_id=SimpleNamespace(id=1))  # có tiến triển nhưng chưa xong
        l2 = _line()  # chưa đụng gì, không supplement_note
        rec = _rfq(status="processing", line_ids=FakeLineRS([l1, l2]))
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.status, "processing")

    def test_untouched_new_stays_new(self):
        """TC-UNIT-DlQuotationRequest-021"""
        rec = _rfq(status="new", line_ids=FakeLineRS([_line()]))
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.status, "new")

    def test_no_status_change_does_not_touch_return_reason(self):
        """TC-UNIT-DlQuotationRequest-022"""
        rec = _rfq(status="new", line_ids=FakeLineRS([_line()]), return_reason="cũ")
        DlQuotationRequest._recompute_status_from_lines([rec])
        self.assertEqual(rec.return_reason, "cũ")  # không bị ghi đè khi status không đổi


# =============================================================================
# Field mới thêm 2026-08-10 (commit 549bcb9) — bổ sung 2026-08-11, trước đó
# 0% coverage (xác nhận bởi đối chiếu code-vs-doc lượt 2).
# =============================================================================
class _PriorityRQS(list):
    _SALES_PRIORITY_BY_STATUS = DlQuotationRequest._SALES_PRIORITY_BY_STATUS
    _TECH_PRIORITY_BY_STATUS = DlQuotationRequest._TECH_PRIORITY_BY_STATUS


class TestComputeSalesPriority(unittest.TestCase):
    def test_maps_status_to_priority(self):
        """TC-UNIT-DlQuotationRequest-023"""
        cases = {"returned": 10, "confirmed": 10, "new": 20, "quoted": 30,
                  "unknown_status": 20}
        for status, expected in cases.items():
            rec = _rfq(status=status)
            DlQuotationRequest._compute_sales_priority(_PriorityRQS([rec]))
            self.assertEqual(rec.sales_priority, expected, status)


class TestComputeTechPriority(unittest.TestCase):
    def test_maps_status_to_priority(self):
        """TC-UNIT-DlQuotationRequest-024"""
        cases = {"new": 10, "returned": 20, "confirmed": 25, "quoted": 30}
        for status, expected in cases.items():
            rec = _rfq(status=status)
            DlQuotationRequest._compute_tech_priority(_PriorityRQS([rec]))
            self.assertEqual(rec.tech_priority, expected, status)


class TestComputeTechQueueSince(unittest.TestCase):
    def test_received_date_wins_when_set(self):
        """TC-UNIT-DlQuotationRequest-025"""
        rec = _rfq(received_date=date(2026, 8, 1), requested_date=date(2026, 7, 1))
        DlQuotationRequest._compute_tech_queue_since([rec])
        self.assertEqual(rec.tech_queue_since, date(2026, 8, 1))

    def test_falls_back_to_requested_date(self):
        rec = _rfq(received_date=False, requested_date=date(2026, 7, 1))
        DlQuotationRequest._compute_tech_queue_since([rec])
        self.assertEqual(rec.tech_queue_since, date(2026, 7, 1))


class _WaitRQS(list):
    def __init__(self, records, aging_param):
        super().__init__(records)
        self.env = {
            "ir.config_parameter": SimpleNamespace(
                sudo=lambda: SimpleNamespace(
                    get_param=lambda key, default: aging_param)),
        }


class TestComputeTechWaiting(unittest.TestCase):
    NOW = SimpleNamespace()

    def test_overdue_when_pending_past_threshold(self):
        """TC-UNIT-DlQuotationRequest-026"""
        from odoo import fields as odoo_fields
        now = odoo_fields.Datetime.now()
        rec = _rfq(requested_date=now - timedelta(days=4))
        rec.tech_stage = "pending"
        rs = _WaitRQS([rec], aging_param=3)
        DlQuotationRequest._compute_tech_waiting(rs)
        self.assertEqual(rec.tech_waiting_days, 4)
        self.assertTrue(rec.tech_overdue)

    def test_invalid_config_param_falls_back_to_default_3(self):
        """TC-UNIT-DlQuotationRequest-027"""
        from odoo import fields as odoo_fields
        now = odoo_fields.Datetime.now()
        rec = _rfq(requested_date=now - timedelta(days=3))
        rec.tech_stage = "pending"
        rs = _WaitRQS([rec], aging_param="not_a_number")
        DlQuotationRequest._compute_tech_waiting(rs)
        self.assertEqual(rec.tech_waiting_days, 3)
        self.assertTrue(rec.tech_overdue)  # 3 >= fallback threshold 3

    def test_closed_stage_not_overdue(self):
        from odoo import fields as odoo_fields
        now = odoo_fields.Datetime.now()
        rec = _rfq(requested_date=now - timedelta(days=100))
        rec.tech_stage = "closed"
        rs = _WaitRQS([rec], aging_param=3)
        DlQuotationRequest._compute_tech_waiting(rs)
        self.assertEqual(rec.tech_waiting_days, 0)
        self.assertFalse(rec.tech_overdue)


class _EnvRS(list):
    def __init__(self, records, env):
        super().__init__(records)
        self.env = env


class TestComputeResolvableProductIds(unittest.TestCase):
    def test_domain_is_manufactured_only_no_material_processed(self):
        """TC-UNIT-DlQuotationRequest-028 (method thật nằm trên
        DlQuotationRequestLine — sheet gốc ghi nhầm dưới DlQuotationRequest,
        giữ nguyên ID cho khớp Report 5.1). Domain đổi 2026-08-08: CHỈ
        product_kind='manufactured', không còn 'in' (manufactured,
        material_processed) — bán thành phẩm chỉ chọn được ở dòng BOM."""
        captured = {}

        def _search(domain):
            captured["domain"] = domain
            return SimpleNamespace(ids=[])

        product_model = SimpleNamespace(search=_search)
        rec = _line(id=5, product_category_id=False)
        rs = _EnvRS([rec], {"product.product": product_model})
        DlQuotationRequestLine._compute_resolvable_product_ids(rs)
        self.assertIn(("product_kind", "=", "manufactured"), captured["domain"])
        self.assertNotIn(("product_kind", "in", ("manufactured", "material_processed")),
                          captured["domain"])


if __name__ == "__main__":
    unittest.main()
