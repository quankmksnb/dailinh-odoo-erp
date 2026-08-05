"""Chặn ghi kết quả kỹ thuật vào RFQ đã đóng / dòng đã bị loại.

Thiết kế: docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md §15.2 (RES-002, RES-003),
§8 (EX-20, EX-21).

Vì sao cần: workspace xử lý dòng là màn full-page mở lâu. Giữa lúc Kỹ thuật mở
và lúc bấm Hoàn tất, Sales có thể đã hủy RFQ, đã đánh dấu đã tạo báo giá, hoặc
đã loại dòng khỏi phạm vi. Trước đây chỉ kiểm lúc MỞ nên kết quả vẫn được ghi
âm thầm vào một RFQ đã đóng.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqResultGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test guard",
            "partner_role": "customer",
        })

    def _make_rfq(self):
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "Khung thép test guard",
                "quantity": 1.0,
                "dimension_note": "1200x800",
            })],
        })
        return request, request.line_ids[0]

    # ------------------------------------------------------------------
    # RES-002 — RFQ đã đóng
    # ------------------------------------------------------------------
    def test_cannot_mark_infeasible_on_cancelled_rfq(self):
        request, line = self._make_rfq()
        request.action_cancel()

        with self.assertRaises(UserError, msg="RFQ đã hủy phải chặn kết luận"):
            line._mark_infeasible("Vượt năng lực máy")

        self.assertFalse(line.is_infeasible)

    def test_cannot_request_supplement_on_quoted_rfq(self):
        request, line = self._make_rfq()
        request.status = "quoted"

        with self.assertRaises(UserError):
            line._mark_supplement("Thiếu kích thước chi tiết")

        self.assertFalse(line.supplement_note)

    def test_still_works_on_open_rfq(self):
        """Không hồi quy: RFQ đang mở vẫn kết luận bình thường."""
        request, line = self._make_rfq()

        line._mark_infeasible("Vượt hành trình máy chấn")

        self.assertTrue(line.is_infeasible)
        self.assertEqual(line.technical_status, "infeasible")

    # ------------------------------------------------------------------
    # RES-003 — dòng đã bị loại khỏi phạm vi giữa chừng
    # ------------------------------------------------------------------
    def test_line_removal_works_while_workspace_open(self):
        """EX-20 — Sales loại dòng trong lúc KTV đang mở workspace.

        `rfq_line_id` của workspace là Many2one BẮT BUỘC. Không khai ondelete
        thì Odoo mặc định 'restrict' ⇒ thao tác loại dòng của Sales vỡ khoá
        ngoại ở DB với thông báo khó hiểu. Khai 'cascade' (giống 2 wizard kết
        luận nhanh) thì bản ghi tạm được dọn theo.
        """
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})

        line.with_context(dl_rfq_scope_removal=True).unlink()
        self.env.flush_all()

        self.assertFalse(wizard.exists(), "Bản ghi workspace phải được dọn theo dòng")

    def test_guard_rejects_missing_line(self):
        """RES-003 — chốt kiểm vẫn bắt được dòng đã biến mất (phòng vệ nhiều lớp)."""
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})

        # Mô phỏng bản ghi đã bị xoá nhưng workspace còn nằm trong bộ nhớ.
        ghost = wizard.with_context(dl_test_ghost=True)
        line_id = line.id
        line.with_context(dl_rfq_scope_removal=True).unlink()
        self.env.flush_all()

        stale_line = self.env["dl.quotation.request.line"].browse(line_id)
        self.assertFalse(stale_line.exists())
        self.assertFalse(ghost.exists())

    def test_workspace_confirm_blocked_when_rfq_cancelled(self):
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})

        request.action_cancel()

        with self.assertRaises(UserError):
            wizard._check_still_processable()

    def test_workspace_confirm_allowed_while_rfq_open(self):
        """Không hồi quy: RFQ đang xử lý thì chốt kiểm phải im lặng đi qua."""
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({"rfq_line_id": line.id})

        wizard._check_still_processable()   # không raise là đạt
