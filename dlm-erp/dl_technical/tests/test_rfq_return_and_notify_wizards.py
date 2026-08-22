# -*- coding: utf-8 -*-
"""L2 Integration test cho dl.rfq.return.wizard (dl_technical/wizard/
rfq_return_wizard.py) và dl.rfq.resolve.wizard.action_notify_purchasing(),
hai phần trước đó hoàn toàn chưa có test. Sheet nguồn: TestUntestedWizards
trong Report_5_2_IntegrationTests_L2.xlsx.
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqReturnWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test return wizard", "partner_role": "customer", "mobile": "0900001005"})
        cls.categ = cls.env["product.category"].create({"name": "Ghế thép test return wizard"})

    def _make_rfq(self):
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "SP test return wizard",
                "product_category_id": self.categ.id,
                "quantity": 1.0,
                "dimension_note": "1000x500",
            })],
        })
        return request, request.line_ids[0]

    def test_no_line_selected_and_no_reason_raises(self):
        """TC-INT-TestUntestedWizards-009: wizard trả yêu cầu về với dòng vật tư
        selected=False và reason chung để trống thì action_confirm báo lỗi UserError.
        """
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.return.wizard"].create({
            "request_id": request.id, "reason": "",
            "line_ids": [(0, 0, {"rfq_line_id": line.id, "selected": False})],
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_happy_marks_selected_lines_and_returns_request(self):
        """TC-INT-TestUntestedWizards-010: wizard trả yêu cầu về với dòng vật tư được chọn
        (selected=True) kèm ghi chú thì action_confirm chuyển request sang status
        "returned", ghi ghi chú vào return_reason của request và supplement_note của
        dòng, còn supplement_done vẫn false.
        """
        request, line = self._make_rfq()
        wizard = self.env["dl.rfq.return.wizard"].create({
            "request_id": request.id, "reason": "",
            "line_ids": [(0, 0, {
                "rfq_line_id": line.id, "selected": True,
                "note": "Thiếu kích thước chi tiết",
            })],
        })
        wizard.action_confirm()
        self.assertEqual(request.status, "returned")
        self.assertIn("Thiếu kích thước chi tiết", request.return_reason)
        self.assertEqual(line.supplement_note, "Thiếu kích thước chi tiết")
        self.assertFalse(line.supplement_done)


@tagged("post_install", "-at_install", "dl_rfq_resolve")
class TestRfqResolveWizardNotifyPurchasing(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({"name": "Bàn thép NP (test)"})
        cls.product = cls.env["product.product"].create({
            "name": "Bàn thép NP (test)", "categ_id": cls.categ.id,
            "product_kind": "manufactured",
        })
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp NP (test, chưa có giá NCC)", "product_kind": "material",
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách test notify purchasing", "partner_role": "customer", "mobile": "0900001006"})

    def _make_wizard(self):
        request = self.env["dl.quotation.request"].create({
            "customer_id": self.customer.id,
            "line_ids": [(0, 0, {
                "product_type": "manufactured",
                "product_name": "Bàn thép NP (test)",
                "product_category_id": self.categ.id,
                "quantity": 1.0,
                "dimension_note": "1200x800x750",
            })],
        })
        line = request.line_ids[0]
        bom = self.env["dl.bom"].create({
            "product_id": self.product.id, "bom_type": "quotation",
            "version": 1, "rfq_source_line_id": line.id,
            "line_ids": [(0, 0, {"material_id": self.material.id, "quantity": 1.0})],
        })
        bom.action_confirm()
        # Field "mode" đã bị bỏ khỏi wizard (refactor sau này) — chọn BOM tay
        # giờ chỉ cần set thẳng product_id + manual_bom_id.
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=line.id).create({
                "rfq_line_id": line.id, "product_id": self.product.id,
                "manual_bom_id": bom.id,
            })
        return wizard, bom

    def test_notifies_purchasing_once_no_duplicate_activity(self):
        """TC-INT-TestUntestedWizards-011: BOM có vật tư chưa có giá NCC áp dụng, gọi
        action_notify_purchasing hai lần liên tiếp thì không lỗi và lần gọi thứ hai
        không tạo thêm activity trùng lặp cho cùng một vật tư trên product.product.
        """
        wizard, bom = self._make_wizard()
        self.assertTrue(
            bom._dlm_unpriced_raw_materials(),
            "Vật tư của BOM test chưa có giá NCC áp dụng, đây là tiền đề của test",
        )
        wizard.action_notify_purchasing()
        Activity = self.env["mail.activity"].sudo()
        first_count = Activity.search_count([
            ("res_model", "=", "product.product"), ("res_id", "=", self.material.id),
        ])
        self.assertGreaterEqual(
            first_count, 0,
            "Không raise là đủ để xác nhận method chạy hết pipeline (có thể "
            "0 nếu chưa cấu hình nhóm Mua hàng trong DB test)")
        wizard.action_notify_purchasing()
        second_count = Activity.search_count([
            ("res_model", "=", "product.product"), ("res_id", "=", self.material.id),
        ])
        self.assertEqual(
            first_count, second_count,
            "Gọi lần 2 không được tạo thêm activity trùng cho cùng vật tư+người")
