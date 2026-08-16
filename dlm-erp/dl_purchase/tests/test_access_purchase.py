# -*- coding: utf-8 -*-
"""Ranh giới vai trò — thứ dễ rò nhất của phân hệ này là GIÁ MUA."""

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestPurchaseAccess(DlPurchaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.thu_kho = cls.env["res.users"].create({
            "name": "Thủ kho (mua hàng)", "login": "thukho_purchase_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })
        cls.mua_hang = cls.env["res.users"].create({
            "name": "Mua hàng (test)", "login": "muahang_purchase_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })

    def test_thu_kho_khong_doc_duoc_gia_tren_lo(self):
        """TC-INT-TestPurchaseAccess-001: MH-15 — thủ kho mở màn Lô và Tồn kho hằng ngày.

        Đỏ = giá mua rò ra cho vai trò không được biết, mà không ai phát hiện vì cột vẫn
        hiện bình thường với người có quyền.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self._receive_po(order)
        lot = self._lot_of(self.thep)

        with self.assertRaises(AccessError):
            lot.with_user(self.thu_kho).read(["dlm_unit_cost"])

    def test_thu_kho_khong_mo_duoc_don_mua(self):
        """TC-INT-TestPurchaseAccess-002: Kiểm soát chéo: người nhận hàng không phải người
        đặt hàng.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])

        with self.assertRaises(AccessError):
            order.with_user(self.thu_kho).read(["name"])

    def test_thu_kho_van_thay_so_don_mua_tren_phieu_nhan(self):
        """TC-INT-TestPurchaseAccess-003: Nhưng vẫn phải biết phiếu nhận này thuộc đơn mua
        nào.

        Đỏ = thủ kho cầm phiếu không đối chiếu được với giấy tờ NCC mang tới. Field
        related dùng sudo nên đọc được số mà không đọc được giá.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        order.action_dlm_confirm()
        picking = order.dlm_picking_ids

        so_don = picking.with_user(self.thu_kho).read(["dlm_purchase_name"])

        self.assertEqual(so_don[0]["dlm_purchase_name"], order.name)

    def test_mua_hang_khong_xac_nhan_duoc_phieu_kiem(self):
        """TC-INT-TestPurchaseAccess-004: Đối xứng: người mua không tự nghiệm thu hàng mình
        mua.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        order.action_dlm_confirm()
        picking = order.dlm_picking_ids

        # `assertRaises` của Odoo không nhận tuple (nó gọi issubclass trên
        # tham số). Bắt tay để chấp nhận cả hai loại chặn: ACL hay guard vai trò
        # đều là kết quả đúng — điều phải sai là "chạy trót lọt".
        try:
            picking.with_user(self.mua_hang).button_validate()
        except (AccessError, UserError):
            return
        self.fail("Mua hàng xác nhận được phiếu kiểm — mất kiểm soát chéo.")
