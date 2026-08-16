# -*- coding: utf-8 -*-
"""K21 — Duyệt đơn mua theo ngưỡng tiền (U-3)."""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseApproval(DlPurchaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `sudo()` KHÔNG đổi `env.user`, mà `_check_can_resolve` soi đúng user
        # đó. Muốn test đường duyệt thì phải có một Giám đốc thật.
        cls.giam_doc = cls.env["res.users"].create({
            "name": "Giám đốc (mua hàng)", "login": "ceo_purchase_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })

    def _set_threshold(self, value):
        self.env["ir.config_parameter"].sudo().set_param(
            "dl_purchase.approval_threshold", str(value))

    def test_duoi_nguong_thi_mua_hang_tu_chot(self):
        """Mua lặt vặt (que hàn, bulong) không được tạo nút cổ chai."""
        self._set_threshold(20000000)
        order = self._mk_po([(self.thep, 10.0, 200000.0)])   # 2 triệu

        self.assertFalse(order.dlm_needs_approval)
        order.action_dlm_confirm()

        self.assertEqual(order.state, "confirmed")

    def test_vuot_nguong_thi_khong_chot_thang_duoc(self):
        """🔴 MH-07 — lá chắn tầng SERVER, không chỉ ẩn nút.

        Đỏ = ngưỡng chi tiêu thành trang trí: mọi đường ghi khác (RPC, import,
        script) vẫn chốt được đơn trăm triệu.
        """
        self._set_threshold(20000000)
        order = self._mk_po([(self.thep, 200.0, 220000.0)])  # 44 triệu

        self.assertTrue(order.dlm_needs_approval)
        with self.assertRaises(UserError):
            order.action_dlm_confirm()

    def test_trinh_duyet_tao_yeu_cau_trong_hom_duyet_san_co(self):
        """Giám đốc chỉ có MỘT hòm duyệt cho cả báo giá lẫn đơn mua.

        Đỏ = dựng hòm thứ hai ⇒ chỗ thứ hai là chỗ bị quên.
        """
        self._set_threshold(20000000)
        order = self._mk_po([(self.thep, 200.0, 220000.0)])

        order.action_dlm_submit_approval()

        self.assertEqual(order.state, "to_approve")
        request = self.env["dl.pricing.approval.request"].search([
            ("res_model", "=", "dl.purchase.order"),
            ("res_id", "=", order.id),
        ])
        self.assertEqual(len(request), 1)
        self.assertEqual(request.request_type, "purchase_over_threshold")
        self.assertEqual(request.state, "pending")

    def test_duyet_xong_thi_don_tu_chot_va_sinh_phieu_nhan(self):
        """Duyệt trong hòm ⇒ đơn đi tiếp, không bắt Mua hàng quay lại bấm lần nữa.

        Đỏ = đơn nằm mãi ở "Chờ duyệt" dù Giám đốc đã đồng ý.
        """
        self._set_threshold(20000000)
        order = self._mk_po([(self.thep, 200.0, 220000.0)])
        order.action_dlm_submit_approval()
        request = self.env["dl.pricing.approval.request"].search([
            ("res_model", "=", "dl.purchase.order"), ("res_id", "=", order.id)])

        request.with_user(self.giam_doc).action_approve()

        self.assertEqual(order.state, "confirmed")
        self.assertEqual(len(order.dlm_picking_ids), 1)

    def test_duoi_nguong_ma_trinh_duyet_thi_bi_chan(self):
        """Không để Mua hàng đẩy việc lên Giám đốc cho chắc — hòm duyệt loãng
        là hòm duyệt không ai đọc."""
        self._set_threshold(20000000)
        order = self._mk_po([(self.thep, 10.0, 200000.0)])

        with self.assertRaises(UserError):
            order.action_dlm_submit_approval()
