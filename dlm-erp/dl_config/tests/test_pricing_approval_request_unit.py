# -*- coding: utf-8 -*-
"""L2 Integration test (TransactionCase, DB thật) cho dl.pricing.approval.
request / dl.pricing.approval.setting (dl_config/models/pricing_approval.py)
— engine phê duyệt nội bộ (Màn hình 5). Sheet nguồn: DlPricingApprovalRequest
trong Report_5_2_IntegrationTests_L2.xlsx.

Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage)."""
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_config")
class TestPricingApprovalRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Request = cls.env["dl.pricing.approval.request"]
        cls.admin_user = cls.env["res.users"].create({
            "name": "Admin test PAR", "login": "admin_par_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        cls.sales_manager = cls.env["res.users"].create({
            "name": "TrKD test PAR", "login": "sm_par_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_sales_manager").id,
            ])],
        })
        cls.ceo_user = cls.env["res.users"].create({
            "name": "CEO test PAR", "login": "ceo_par_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_ceo").id,
            ])],
        })
        cls.sales_user = cls.env["res.users"].create({
            "name": "Sales test PAR", "login": "sales_par_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })
        # message_post() (nhánh tự duyệt) cần author resolve được email —
        # cho user test 1 email thật để không đụng cấu hình mail server.
        cls.admin_user.partner_id.email = "admin_par_test@dailinh.vn"

    def _req(self, **vals):
        base = dict(request_type="profit_config", reason="lý do test",
                    company_id=self.env.company.id)
        base.update(vals)
        return self.Request.create(base)

    def test_approving_already_resolved_request_raises(self):
        """TC-INT-DlPricingApprovalRequest-001"""
        req = self._req(state="approved")
        with self.assertRaises(UserError):
            self.Request.with_user(self.admin_user).browse(req.id).action_approve()

    def test_happy_approve_sets_state_and_clears_activities(self):
        """TC-INT-DlPricingApprovalRequest-002"""
        req = self._req()
        self.Request.with_user(self.admin_user).browse(req.id).action_approve()
        self.assertEqual(req.state, "approved")
        self.assertEqual(req.resolved_by_id, self.admin_user)
        self.assertFalse(req.activity_ids.filtered(
            lambda a: a.activity_type_id == self.env.ref(
                "mail.mail_activity_data_todo")))

    def test_self_approval_is_detected_and_logged(self):
        """TC-INT-DlPricingApprovalRequest-003"""
        req = self._req(requester_id=self.admin_user.id)
        self.Request.with_user(self.admin_user).browse(req.id).action_approve()
        self.assertTrue(req.is_self_approval)
        self.assertTrue(any(
            "tự duyệt" in (m.body or "") for m in req.message_ids))

    def test_admin_bypasses_commercial_but_not_quote_or_matrix(self):
        """TC-INT-DlPricingApprovalRequest-004"""
        commercial_req = self._req(request_type="profit_config")
        self.Request.with_user(self.admin_user).browse(
            commercial_req.id)._check_can_resolve()  # không raise

        quote_req = self._req(
            request_type="quote_over_threshold", approval_level="sales_manager")
        with self.assertRaises(AccessError):
            self.Request.with_user(self.admin_user).browse(
                quote_req.id)._check_can_resolve()

        matrix_req = self._req(request_type="matrix_config")
        with self.assertRaises(AccessError):
            self.Request.with_user(self.admin_user).browse(
                matrix_req.id)._check_can_resolve()

    def test_quote_over_threshold_only_allows_rank_at_or_above_level(self):
        """TC-INT-DlPricingApprovalRequest-005"""
        req = self._req(
            request_type="quote_over_threshold", approval_level="sales_manager")
        with self.assertRaises(AccessError):
            self.Request.with_user(self.sales_user).browse(req.id)._check_can_resolve()
        # Không raise cho Trưởng KD (đúng cấp) lẫn Giám đốc (cấp cao hơn).
        self.Request.with_user(self.sales_manager).browse(req.id)._check_can_resolve()
        self.Request.with_user(self.ceo_user).browse(req.id)._check_can_resolve()

    def test_reject_without_comment_raises(self):
        """TC-INT-DlPricingApprovalRequest-006"""
        req = self._req()
        with self.assertRaises(ValidationError):
            self.Request.with_user(self.admin_user).browse(req.id).action_reject()

    def test_open_reject_wizard_on_resolved_request_raises(self):
        """TC-INT-DlPricingApprovalRequest-007"""
        req = self._req(state="rejected")
        with self.assertRaises(UserError):
            self.Request.with_user(self.admin_user).browse(
                req.id).action_open_reject_wizard()

    def test_pending_approval_count_scoped_by_rank(self):
        """TC-INT-DlPricingApprovalRequest-008 — so lệch (delta) trước/sau,
        không giả định DB sạch tuyệt đối (có thể có request pending khác từ
        seed/test trước đó)."""
        before_sm = self.Request.with_user(
            self.sales_manager).get_pending_approval_count()
        before_ceo = self.Request.with_user(self.ceo_user).get_pending_approval_count()
        self._req(request_type="quote_over_threshold", approval_level="sales_manager")
        self._req(request_type="quote_over_threshold", approval_level="ceo")
        after_sm = self.Request.with_user(
            self.sales_manager).get_pending_approval_count()
        after_ceo = self.Request.with_user(self.ceo_user).get_pending_approval_count()
        self.assertEqual(
            after_sm - before_sm, 1,
            "Trưởng KD chỉ thấy thêm đúng 1 (mức của mình), không thấy mức Giám đốc")
        self.assertEqual(
            after_ceo - before_ceo, 2,
            "Giám đốc thấy thêm cả 2 (cấp cao hơn duyệt thay được cấp thấp)")

    def test_cancel_on_change_only_touches_pending_and_approved(self):
        """TC-INT-DlPricingApprovalRequest-009"""
        pending_req = self._req(state="pending")
        approved_req = self._req(state="approved")
        rejected_req = self._req(state="rejected")
        (pending_req + approved_req + rejected_req).action_cancel_on_change()
        self.assertEqual(pending_req.state, "cancelled")
        self.assertEqual(approved_req.state, "cancelled")
        self.assertEqual(rejected_req.state, "rejected", "Trạng thái đóng không bị đụng")

    def test_setting_allowed_user_ids_includes_specific_approver_and_higher_rank(self):
        """TC-INT-DlPricingApprovalRequest-010 — (request_type, company_id)
        unique nên xoá cấu hình mặc định đã seed cho 'discount_config' (nếu
        có) trước khi tạo bản test, tránh đụng ràng buộc unique."""
        Setting = self.env["dl.pricing.approval.setting"]
        Setting.sudo().search([
            ("request_type", "=", "discount_config"),
            ("company_id", "=", self.env.company.id),
        ]).unlink()
        setting = Setting.create({
            "request_type": "discount_config",
            "approver_role": "sales_manager",
            "approver_user_id": self.sales_manager.id,
            "company_id": self.env.company.id,
        })
        allowed = setting._allowed_user_ids()
        self.assertIn(self.sales_manager.id, allowed)
        self.assertIn(self.ceo_user.id, allowed,
                       "Cấp cao hơn (Giám đốc) luôn duyệt thay được")
        self.assertNotIn(self.sales_user.id, allowed)
