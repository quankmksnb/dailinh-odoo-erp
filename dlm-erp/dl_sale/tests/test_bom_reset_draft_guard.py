# -*- coding: utf-8 -*-
"""L2 Integration test cho dl.bom._check_can_reset_draft() override TỪ
dl_sale (dl_sale/models/dl_bom_ext.py, DlBom._inherit='dl.bom') — chặn
hạ-nháp/sửa 1 BOM đã được đơn hàng/báo giá chốt tham chiếu. Sheet nguồn:
DlBomHeaderMixin trong Report_5_1_UnitTests_L1.xlsx (TC-017/018, method
thật nằm ở dl_sale nhưng gộp vào sheet BOM gốc — cùng cơ chế
_check_can_reset_draft()).

Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage)."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_sale")
class TestBomResetDraftGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "KH test reset draft guard", "partner_role": "customer"})
        cls.product = cls.env["product.product"].create({
            "name": "SP test reset draft guard", "product_kind": "manufactured"})
        cls.material = cls.env["product.product"].create({
            "name": "VT test reset draft guard", "product_kind": "material"})

    def _make_confirmed_bom(self):
        bom = self.env["dl.bom"].create({
            "product_id": self.product.id,
            "bom_type": "quotation",
            "product_qty": 1.0,
            "line_ids": [(0, 0, {"material_id": self.material.id, "quantity": 1.0})],
        })
        bom.action_confirm()
        return bom

    def test_bom_used_by_confirmed_sale_order_blocks_reset_draft(self):
        """TC-UNIT-DlBomHeaderMixin-017 — tạo đơn THẲNG ở state='confirmed'
        lúc create() (không đi qua write({'state':'confirmed'})) để không bị
        _promote_draft_products() khoá BOM trước khi kịp test guard riêng
        của dl_sale — cô lập đúng nhánh đang test (BOM đã Đã xác nhận, bị
        1 dòng đơn Đã xác nhận tham chiếu)."""
        bom = self._make_confirmed_bom()
        order = self.env["dl.sale.order"].create({
            "partner_id": self.customer.id, "state": "confirmed",
        })
        self.env["dl.sale.order.line"].create({
            "order_id": order.id, "name": "Dòng test", "bom_id": bom.id,
        })
        with self.assertRaises(UserError):
            bom.action_reset_draft()
        self.assertEqual(bom.status, "confirmed", "Không được đổi khi bị chặn")

    def test_bom_used_by_accepted_quotation_blocks_reset_draft(self):
        """TC-UNIT-DlBomHeaderMixin-018"""
        bom = self._make_confirmed_bom()
        quotation = self.env["dl.quotation"].create({
            "partner_id": self.customer.id,
            "line_ids": [(0, 0, {"name": "Dòng test", "bom_id": bom.id})],
        })
        quotation.state = "accepted"
        with self.assertRaises(UserError):
            bom.action_reset_draft()
        self.assertEqual(bom.status, "confirmed")

    def test_bom_not_referenced_can_reset_draft(self):
        """Không nghi ngờ chặn oan: BOM không bị ai tham chiếu vẫn hạ nháp
        bình thường."""
        bom = self._make_confirmed_bom()
        bom.action_reset_draft()
        self.assertEqual(bom.status, "draft")
