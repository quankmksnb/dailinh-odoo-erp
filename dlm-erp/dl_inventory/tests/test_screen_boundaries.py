# -*- coding: utf-8 -*-
"""RS-02..RS-05 — Ranh giới giữa các màn: không rò ra native, không lẫn loại phiếu.

Rà soát: docs/Ra_soat_phan_he_kho_2026-08-12.md

Hai lớp bất biến ở đây, cả hai đều thuộc loại **sai lặng lẽ**:

  • Mọi đường mở phiếu kho phải ra form Đại Linh. App Inventory gốc đã bị ẩn nên
    các nút điều hướng là lối vào native DUY NHẤT còn lại — lọt một nút là thủ
    kho có nguyên bộ nút native, trong đó "Trả hàng" đi tắt qua cả luồng kiểm.
  • Mỗi màn chỉ hứng đúng loại phiếu của nó. Lọc bằng "trừ ra" thì mỗi loại
    phiếu thêm về sau là một lần rò rỉ mới — và rò rỉ chỉ lộ khi nghiệp vụ đó
    chạy thật (phiếu BPL đầu tiên, hoặc ngày B2 lên).
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged
from odoo.tools.safe_eval import safe_eval

from .common import DlInventoryCase


class DlScreenCase(DlInventoryCase):

    def _qc_ready(self, qty=100.0):
        receipt = self._receive(self._make_receipt(qty=qty), qty=qty)
        return receipt, self._qc_picking(receipt)

    def _reject_some(self, qc, passed=92.0, rejected=8.0):
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.write({
            "quantity": passed, "picked": True,
            "dlm_qty_rejected": rejected, "dlm_reject_reason": "defect"})
        qc.action_dlm_validate_qc()
        return qc._dlm_vendor_returns()[:1]

    def _forced_views(self, action):
        """View mà action ép dùng (rỗng = để Odoo tự chọn ⇒ form gốc)."""
        return [vid for vid, _mode in action.get("views") or []]

    def _pickings_of_screen(self, xmlid):
        domain = safe_eval(self.env.ref(xmlid).domain)
        return self.env["stock.picking"].search(domain)

    def _picking_type(self, sequence_code):
        return self.env["stock.picking.type"].search(
            [("sequence_code", "=", sequence_code)], limit=1)


@tagged("post_install", "-at_install", "dl_inventory")
class TestNavigationOpensDlForm(DlScreenCase):

    def test_nut_mo_phieu_kiem_ra_form_kiem_hang(self):
        receipt, qc = self._qc_ready()
        views = self._forced_views(receipt.action_dlm_open_qc_picking())
        self.assertTrue(views, "Không ép view ⇒ rơi về form gốc Odoo.")
        self.assertEqual(views[0], self.env.ref(
            "dl_inventory.view_dl_qc_form").id)

    def test_nut_phieu_nhan_goc_ra_form_nhan_hang(self):
        receipt, qc = self._qc_ready()
        views = self._forced_views(qc.action_dlm_open_source_receipt())
        self.assertEqual(views[:1], [self.env.ref(
            "dl_inventory.view_dl_receipt_form").id])

    def test_nut_phieu_tra_ncc_ra_form_tra_hang(self):
        receipt, qc = self._qc_ready()
        self._reject_some(qc)
        views = self._forced_views(qc.action_dlm_open_returns())
        self.assertEqual(views[:1], [self.env.ref(
            "dl_inventory.view_dl_vendor_return_form").id])

    def test_nut_phieu_nhan_cua_lo_ra_form_nhan_hang(self):
        """Chặng cuối chuỗi truy vết: lô → phiếu nhận → NCC."""
        receipt, qc = self._qc_ready()
        lot = receipt.move_ids.move_line_ids.lot_id[:1]
        self.assertTrue(lot, "Ca test cần lô tự sinh của K3.")
        views = self._forced_views(lot.action_dlm_open_receipt())
        self.assertEqual(views[:1], [self.env.ref(
            "dl_inventory.view_dl_receipt_form").id])

    def test_moi_view_bi_ep_deu_thuoc_dl_inventory(self):
        """Lưới chặn hồi quy: nút mới quên ép view, hoặc ép nhầm view native."""
        receipt, qc = self._qc_ready()
        self._reject_some(qc)
        actions = [
            receipt.action_dlm_open_qc_picking(),
            qc.action_dlm_open_source_receipt(),
            qc.action_dlm_open_returns(),
        ]
        for action in actions:
            views = self._forced_views(action)
            self.assertTrue(views, "Action %s không ép view." % action["name"])
            for view_id in views:
                xmlid = self.env["ir.ui.view"].browse(
                    view_id).get_external_id().get(view_id, "")
                self.assertTrue(
                    xmlid.startswith("dl_inventory."),
                    "View '%s' không thuộc dl_inventory — là màn native." % xmlid)


@tagged("post_install", "-at_install", "dl_inventory")
class TestScreenScope(DlScreenCase):

    def test_phieu_ban_phe_lieu_khong_lot_vao_man_giao_hang(self):
        """RS-04 — BPL cũng là outgoing; lọc "trừ TR" là để lọt."""
        scrap_type = self._picking_type("BPL")
        self.assertTrue(scrap_type, "Ca test cần loại hoạt động Bán phế liệu.")
        picking = self.env["stock.picking"].create({
            "picking_type_id": scrap_type.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
        })
        self.assertNotIn(picking, self._pickings_of_screen(
            "dl_inventory.action_dl_picking_delivery"),
            "Phiếu bán phế liệu hiện ở màn Giao hàng — mở ra là ngõ cụt vì form "
            "Giao hàng khoá bảng dòng tới khi chọn đơn bán.")

    def test_phieu_xuat_san_xuat_khong_lot_vao_man_chuyen_kho(self):
        """RS-05 — XSX/NTP của B2 đang active sẵn; lọc "trừ KC" là để lọt."""
        xsx_type = self._picking_type("XSX")
        self.assertTrue(xsx_type, "Ca test cần loại hoạt động Xuất vật tư SX.")
        picking = self.env["stock.picking"].create({
            "picking_type_id": xsx_type.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
        })
        self.assertNotIn(picking, self._pickings_of_screen(
            "dl_inventory.action_dl_picking_transfer"),
            "Phiếu xuất vật tư sản xuất đổ vào màn Chuyển kho của thủ kho.")

    def test_phieu_kiem_khong_lot_vao_man_chuyen_kho(self):
        receipt, qc = self._qc_ready()
        self.assertNotIn(qc, self._pickings_of_screen(
            "dl_inventory.action_dl_picking_transfer"))

    def test_whitelist_khong_siet_qua_tay(self):
        """Phiếu GH thật và phiếu CK thật vẫn phải hiện ở màn của chúng."""
        delivery = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.loc_tp.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
        })
        transfer = self.env["stock.picking"].create({
            "picking_type_id": self._picking_type("CK").id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
        })
        self.assertIn(delivery, self._pickings_of_screen(
            "dl_inventory.action_dl_picking_delivery"))
        self.assertIn(transfer, self._pickings_of_screen(
            "dl_inventory.action_dl_picking_transfer"))


@tagged("post_install", "-at_install", "dl_inventory")
class TestVendorReturnDecision(DlScreenCase):
    """RS-03 — Mô hình B: Mua hàng QUYẾT ĐỊNH, Thủ kho THI HÀNH."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_warehouse = cls.env["res.users"].create({
            "name": "thukho_rs03", "login": "thukho_rs03",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })
        cls.user_purchasing = cls.env["res.users"].create({
            "name": "muahang_rs03", "login": "muahang_rs03",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })

    def _vendor_return(self):
        receipt, qc = self._qc_ready()
        return self._reject_some(qc)

    def test_thu_kho_khong_chot_duoc_phieu_tra(self):
        with self.assertRaises(UserError):
            self._vendor_return().with_user(
                self.user_warehouse).action_confirm()

    def test_thu_kho_khong_huy_duoc_phieu_tra(self):
        with self.assertRaises(UserError):
            self._vendor_return().with_user(
                self.user_warehouse).action_cancel()

    def test_mua_hang_chot_duoc_phieu_tra(self):
        """Guard không được chặn nhầm chính chủ."""
        phieu = self._vendor_return()
        phieu.with_user(self.user_purchasing).action_confirm()
        self.assertNotEqual(phieu.state, "draft")

    def test_thu_kho_van_xac_nhan_duoc_phieu_da_chot(self):
        """Người trao hàng cho xe NCC ở cửa kho là Thủ kho, không phải Mua hàng."""
        phieu = self._vendor_return()
        phieu.with_user(self.user_purchasing).action_confirm()

        phieu_wh = phieu.with_user(self.user_warehouse)
        phieu_wh.action_assign()
        for move in phieu_wh.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        phieu_wh.button_validate()
        self.assertEqual(phieu.state, "done",
                         "Thủ kho phải giao được hàng trả cho xe NCC.")

    def test_guard_khong_cham_phieu_nhan(self):
        """Guard chỉ được chạm phiếu TR — phiếu nhận không dính."""
        picking = self.env["stock.picking"].with_user(
            self.user_warehouse).create({
                "picking_type_id": self.warehouse.in_type_id.id,
                "partner_id": self.vendor.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
                "move_ids": [(0, 0, {
                    "name": self.material.name,
                    "product_id": self.material.id,
                    "product_uom_qty": 5.0,
                    "product_uom": self.material.uom_id.id,
                    "location_id": self.loc_vendors.id,
                    "location_dest_id": self.loc_qc.id,
                })],
            })
        picking.action_confirm()
        self.assertNotEqual(picking.state, "draft")

    def test_thu_kho_khong_tao_duoc_phieu_tra(self):
        """ir.rule chặn tận gốc: không có phiếu TR thì không có gì để chốt."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env["stock.picking"].with_user(self.user_warehouse).create({
                "picking_type_id": self._picking_type("TR").id,
                "partner_id": self.vendor.id,
                "location_id": self.loc_tra.id,
                "location_dest_id": self.loc_vendors.id,
            })
