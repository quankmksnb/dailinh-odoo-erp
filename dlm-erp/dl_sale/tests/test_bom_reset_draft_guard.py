# -*- coding: utf-8 -*-
"""L2 Integration test cho dl.bom._check_can_reset_draft() override từ
dl_sale (dl_sale/models/dl_bom_ext.py, DlBom._inherit='dl.bom'). Test này
kiểm tra việc chặn hạ nháp hoặc sửa một BOM đã được đơn hàng/báo giá đã
chốt tham chiếu.

Sheet nguồn: DlBomHeaderMixin trong Report_5_1_UnitTests_L1.xlsx (TC-017/018).
Method thật nằm ở dl_sale nhưng gộp vào sheet BOM gốc vì dùng chung cơ chế
_check_can_reset_draft()."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_sale")
class TestBomResetDraftGuard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "KH test reset draft guard", "partner_role": "customer", "mobile": "0900001008"})
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
        """TC-UNIT-DlBomHeaderMixin-017: tạo đơn trực tiếp ở state='confirmed'
        ngay lúc create() (không đi qua write({'state':'confirmed'})) để
        tránh _promote_draft_products() khoá BOM trước khi guard của dl_sale
        kịp chạy. Nhờ vậy test cô lập đúng nhánh cần kiểm: BOM đã xác nhận,
        bị một dòng đơn đã xác nhận tham chiếu."""
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
        """TC-UNIT-DlBomHeaderMixin-018: BOM đã xác nhận bị một báo giá ở
        trạng thái accepted tham chiếu thì action_reset_draft() phải raise
        UserError và giữ nguyên status='confirmed'."""
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
