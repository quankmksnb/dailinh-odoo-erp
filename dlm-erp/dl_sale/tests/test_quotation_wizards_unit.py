# -*- coding: utf-8 -*-
"""L2 Integration test cho các wizard chưa từng có test: dl.quotation.reject.
wizard, dl.quotation.revision.wizard, dl.sale.order.reset.draft.wizard,
dl.quotation.export.wizard. Sheet nguồn: TestUntestedWizards trong
Report_5_2_IntegrationTests_L2.xlsx."""
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationWizards(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "KH test quotation wizards", "partner_role": "customer",
            "partner_type": "individual",
        })

    def _quotation(self, state="sent", **kw):
        vals = {"partner_id": self.customer.id, "state": state}
        vals.update(kw)
        return self.env["dl.quotation"].create(vals)

    # ---------------------------------------------------------- reject wizard
    def test_reject_wizard_other_reason_without_note_raises(self):
        """TC-INT-TestUntestedWizards-003: báo giá đang sent, wizard từ chối
        chọn reason "other" nhưng note rỗng thì action_confirm báo lỗi
        UserError."""
        quotation = self._quotation(state="sent")
        wizard = self.env["dl.quotation.reject.wizard"].create({
            "quotation_id": quotation.id, "reason": "other", "note": "",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    # --------------------------------------------------------- revision wizard
    def test_revision_wizard_empty_note_raises(self):
        """TC-INT-TestUntestedWizards-004: wizard yêu cầu chỉnh sửa với note
        chỉ toàn khoảng trắng thì action_confirm báo lỗi UserError."""
        quotation = self._quotation(state="sent")
        wizard = self.env["dl.quotation.revision.wizard"].create({
            "quotation_id": quotation.id, "adjust_type": "commercial", "note": "  ",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_revision_wizard_happy_delegates_to_apply_revision_request(self):
        """TC-INT-TestUntestedWizards-005: wizard yêu cầu chỉnh sửa kỹ thuật
        với note hợp lệ thì action_confirm chuyển báo giá sang state
        revision_requested, lưu đúng loại và nội dung yêu cầu, đồng thời trả
        về action đóng cửa sổ (ir.actions.act_window_close)."""
        quotation = self._quotation(state="sent")
        wizard = self.env["dl.quotation.revision.wizard"].create({
            "quotation_id": quotation.id, "adjust_type": "technical",
            "note": "Khách đổi vật liệu",
        })
        result = wizard.action_confirm()
        self.assertEqual(quotation.state, "revision_requested")
        self.assertEqual(quotation.revision_request_type, "technical")
        self.assertEqual(quotation.revision_request_note, "Khách đổi vật liệu")
        self.assertEqual(result.get("type"), "ir.actions.act_window_close")

    # --------------------------------------------------------- reset-draft wizard
    def test_sale_order_reset_draft_wizard_empty_reason_raises(self):
        """TC-INT-TestUntestedWizards-006: đơn hàng đang confirmed, wizard
        chuyển về nháp với lý do chỉ toàn khoảng trắng thì action_confirm báo
        lỗi ValidationError."""
        order = self.env["dl.sale.order"].create({
            "partner_id": self.customer.id, "state": "confirmed"})
        wizard = self.env["dl.sale.order.reset.draft.wizard"].create({
            "order_id": order.id, "reason": "   ",
        })
        with self.assertRaises(ValidationError):
            wizard.action_confirm()

    # --------------------------------------------------------- export wizard
    def test_export_wizard_email_blocked_when_customer_has_no_email(self):
        """TC-INT-TestUntestedWizards-007: khách hàng của báo giá chưa có
        email thì wizard xuất báo giá gọi action_email báo lỗi UserError."""
        quotation = self._quotation(state="sent")
        self.assertFalse(quotation.partner_id.email)
        wizard = self.env["dl.quotation.export.wizard"].create({
            "quotation_id": quotation.id, "doc_format": "pdf",
        })
        with self.assertRaises(UserError):
            wizard.action_email()

    def test_export_wizard_email_happy_builds_composer_action(self):
        """TC-INT-TestUntestedWizards-008: khách hàng đã có email, wizard
        xuất báo giá gọi action_email trả về action mở mail.compose.message
        với context đúng model/res_ids của báo giá, có đính kèm file và đúng
        partner_ids của khách hàng."""
        quotation = self._quotation(state="sent")
        quotation.partner_id.email = "khach_test_export@dailinh.vn"
        wizard = self.env["dl.quotation.export.wizard"].create({
            "quotation_id": quotation.id, "doc_format": "pdf",
        })
        action = wizard.action_email()
        self.assertEqual(action["res_model"], "mail.compose.message")
        ctx = action["context"]
        self.assertEqual(ctx["default_model"], "dl.quotation")
        self.assertEqual(ctx["default_res_ids"], quotation.ids)
        self.assertTrue(ctx["default_attachment_ids"])
        self.assertEqual(ctx["default_partner_ids"], [(6, 0, quotation.partner_id.ids)])
