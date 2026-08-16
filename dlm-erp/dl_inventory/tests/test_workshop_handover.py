# -*- coding: utf-8 -*-
"""K15 — Bàn giao vật tư ra xưởng: hai chữ ký, hai người.

Người dùng chốt 2026-08-13: hàng ra khỏi Kho nguyên vật liệu thì bên Xưởng
(trưởng Kỹ thuật) phải ký nhận, "để sau này còn truy vấn và truy cứu xem ai
nhận hàng".

Vì sao bộ test này đáng có: giá trị của chữ ký nằm TRỌN ở chỗ nó không bỏ qua
được. Một chữ ký mà thủ kho tự ký cả hai đầu, hoặc mà nút native đi vòng qua
được, thì nó không trả lời được câu hỏi nó sinh ra để trả lời — mà vẫn trông
như đang hoạt động trên màn hình.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestWorkshopHandover(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_warehouse = cls.env["res.users"].create({
            "name": "Thủ kho (test)", "login": "k15_thukho",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })
        cls.user_tech = cls.env["res.users"].create({
            "name": "Trưởng KT (test)", "login": "k15_kythuat",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _stock(self, location, qty=10.0):
        """Đặt sẵn tồn ở một khu, kèm lô.

        Vật tư của dự án là `tracking='lot'` thì quant không lô thì `action_assign`
        không giữ chỗ được, phiếu dừng ở `confirmed` và mọi test dưới đây hỏng vì lý do
        chẳng liên quan gì tới chữ ký.
        """
        lot = self.env["stock.lot"].create({
            "name": "LO-K15-%s" % location.id,
            "product_id": self.material.id,
            "company_id": self.env.company.id,
        })
        self.env["stock.quant"]._update_available_quantity(
            self.material, location, qty, lot_id=lot)

    def _transfer(self, dest=None, qty=5.0):
        """Phiếu chuyển kho đã giữ chỗ, sẵn sàng bàn giao."""
        dest = dest or self.loc_xuong
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": qty,
                "product_uom": self.material.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": dest.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    # ── Phạm vi: tuyến nào cần ký, tuyến nào không ───────────────────────────
    def test_chi_tuyen_ra_xuong_moi_can_ky(self):
        """TC-INT-TestWorkshopHandover-001: Chữ ký chỉ gắn với tuyến ra Xưởng — dán nó lên
        mọi phiếu chuyển kho là bắt trưởng KT ký cả những chuyến gom phế liệu họ không
        dính tới.
        """
        self._stock(self.loc_kho)
        ra_xuong = self._transfer(self.loc_xuong)
        self.assertTrue(ra_xuong.dlm_needs_receipt)
        self.assertEqual(ra_xuong.dlm_receipt_state, "ready")

        self._stock(self.loc_xuong, 10.0)
        gom_phe_lieu = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_xuong.id,
            "location_dest_id": self.loc_xuong_pl.id,
        })
        self.assertFalse(gom_phe_lieu.dlm_needs_receipt)
        self.assertEqual(gom_phe_lieu.dlm_receipt_state, "none")

    # ── Chặn cứng: đường tắt phải đóng ───────────────────────────────────────
    def test_khong_ky_thi_khong_xac_nhan_duoc(self):
        """TC-INT-TestWorkshopHandover-002: Bất biến lõi: `button_validate` native không đi
        vòng qua được.

        Đây là cả lý do guard nằm ở model chứ không chỉ ở `invisible` của nút.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        picking.move_ids.picked = True

        with self.assertRaises(UserError) as ctx:
            picking.button_validate()
        self.assertIn("chữ ký nhận hàng", str(ctx.exception))
        self.assertEqual(picking.state, "assigned",
                         "Phiếu vẫn phải treo — hàng chưa được rời sổ kho.")
        self.assertEqual(self._qty_at(self.loc_kho), 10.0,
                         "Hàng đã rời Kho nguyên vật liệu dù chưa ai ký nhận.")

    def test_ban_giao_roi_van_chua_du(self):
        """TC-INT-TestWorkshopHandover-003: Một chữ ký không thành hai: bàn giao xong vẫn
        phải chờ bên nhận.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        picking.action_dlm_handover()

        self.assertEqual(picking.dlm_receipt_state, "waiting")
        self.assertTrue(picking.dlm_handover_uid)
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_chua_ban_giao_thi_khong_ky_nhan_duoc(self):
        """TC-INT-TestWorkshopHandover-004: Thứ tự hai chữ ký không đảo được — ký nhận thứ
        chưa ai giao là ký khống.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        with self.assertRaises(UserError) as ctx:
            picking.action_dlm_confirm_receipt()
        self.assertIn("chưa bàn giao", str(ctx.exception))

    # ── Luồng đủ: hai chữ ký thì hàng chuyển ───────────────────────────────────
    def test_du_hai_chu_ky_thi_hang_di(self):
        """TC-INT-TestWorkshopHandover-005: Chiều thuận — không có nó thì mọi test trên vẫn
        xanh khi tính năng chết hẳn (chặn tất là cách dễ nhất để 'pass').
        """
        self._stock(self.loc_kho)
        picking = self._transfer(qty=5.0)
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()

        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.dlm_receipt_state, "received")
        self.assertTrue(picking.dlm_received_uid)
        self.assertTrue(picking.dlm_received_date)
        self.assertEqual(self._qty_at(self.loc_xuong), 5.0,
                         "Ký đủ rồi mà hàng không sang tới Xưởng.")
        self.assertEqual(self._qty_at(self.loc_kho), 5.0)

    def test_ky_hai_lan_bi_chan(self):
        """TC-INT-TestWorkshopHandover-006.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()
        with self.assertRaises(UserError):
            picking.action_dlm_confirm_receipt()

    # ── Truy cứu: ai giao, ai nhận ───────────────────────────────────────────
    def test_thu_kho_khong_tu_ky_nhan_duoc(self):
        """TC-INT-TestWorkshopHandover-007: Đúng lý do tính năng này tồn tại. Nếu thủ kho
        ký được cả hai đầu thì sáu tháng sau truy "ai nhận đống thép" lại ra chính người
        xuất — chữ ký có mặt trên màn hình nhưng không trả lời được gì.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        phieu_wh = picking.with_user(self.user_warehouse)
        phieu_wh.action_dlm_handover()

        with self.assertRaises(UserError) as ctx:
            phieu_wh.action_dlm_confirm_receipt()
        self.assertIn("bên NHẬN", str(ctx.exception))

    def test_ky_thuat_ky_duoc_du_chi_co_quyen_doc(self):
        """TC-INT-TestWorkshopHandover-008: Chiều ngược của test trên — và là chỗ dễ hỏng
        nhất.

        Nhóm Kỹ thuật chỉ có ACL `1,0,0,0` trên stock.picking. Nút ký nhận chạy sudo SAU
        khi kiểm vai trò; bỏ sudo thì test này nổ AccessError, còn nới ACL ghi cho cả
        nhóm thì họ sửa được mọi phiếu kho.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        picking.with_user(self.user_warehouse).action_dlm_handover()
        picking.with_user(self.user_tech).action_dlm_confirm_receipt()

        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.dlm_received_uid, self.user_tech,
                         "Chữ ký phải ghi đúng người bấm, không phải superuser.")
        self.assertEqual(picking.dlm_handover_uid, self.user_warehouse)

    def test_chu_ky_khong_theo_ban_sao(self):
        """TC-INT-TestWorkshopHandover-009: Nhân bản phiếu mà kéo theo chữ ký cũ là chế ra
        bằng chứng một lần nhận hàng chưa từng xảy ra.
        """
        self._stock(self.loc_kho)
        picking = self._transfer()
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()

        ban_sao = picking.copy()
        self.assertFalse(ban_sao.dlm_received_uid)
        self.assertFalse(ban_sao.dlm_handover_uid)
        self.assertEqual(ban_sao.dlm_receipt_state, "ready")
