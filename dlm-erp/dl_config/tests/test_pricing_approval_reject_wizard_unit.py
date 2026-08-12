# -*- coding: utf-8 -*-
"""L2 Integration test cho dl.pricing.approval.reject.wizard (dl_config/
wizard/pricing_approval_reject_wizard.py). Sheet nguồn: TestUntestedWizards
trong Report_5_2_IntegrationTests_L2.xlsx.

Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage)."""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_config")
class TestPricingApprovalRejectWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env["res.users"].create({
            "name": "Admin test reject wizard", "login": "admin_rejectwiz_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })

    def _pending_request(self):
        return self.env["dl.pricing.approval.request"].create({
            "request_type": "profit_config", "reason": "lý do test wizard",
            "company_id": self.env.company.id,
        })

    def test_empty_reject_comment_raises(self):
        """TC-INT-TestUntestedWizards-001"""
        req = self._pending_request()
        wizard = self.env["dl.pricing.approval.reject.wizard"].with_user(
            self.admin_user).create({"request_id": req.id, "reject_comment": "   "})
        with self.assertRaises(ValidationError):
            wizard.action_confirm()

    def test_happy_writes_comment_and_delegates_to_action_reject(self):
        """TC-INT-TestUntestedWizards-002"""
        req = self._pending_request()
        wizard = self.env["dl.pricing.approval.reject.wizard"].with_user(
            self.admin_user).create({
                "request_id": req.id, "reject_comment": "Không đúng chính sách"})
        wizard.action_confirm()
        self.assertEqual(req.state, "rejected")
        self.assertEqual(req.reject_comment, "Không đúng chính sách")
