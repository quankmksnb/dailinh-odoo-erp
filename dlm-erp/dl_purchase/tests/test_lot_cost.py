# -*- coding: utf-8 -*-
"""K20 — Giá theo lô & giá vốn thực tế FIFO.

Phép thử xương sống là ``test_vi_du_fifo_lo_cu_truoc``: nó dựng lại ĐÚNG ví dụ
bằng số ở ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §6.4. Nếu con số đi ra
khác 21.400.000 thì hoặc thiết kế sai, hoặc code sai — và cả hai đều phải dừng
lại trước khi ai đó dùng số này để quyết định giá.
"""

from odoo import fields
from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestLotCost(DlPurchaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fg_type = cls.env.ref("dl_inventory.picking_type_mo_receipt")
        cls.loc_production = cls.env["stock.location"]._dlm_virtual_location(
            "production")
        cls.ban = cls.env["product.product"].create({
            "name": "Bàn học sinh (giá vốn)", "product_kind": "manufactured"})
        cls.ban.tracking = "none"

    # ------------------------------------------------------------------
    def _consume_batch(self, order, qty):
        """Phiếu [8] khai vật tư ĐÃ DÙNG — nơi vật tư thật sự rời sổ."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "dlm_sale_order_id": order.id,
            "move_ids": [
                (0, 0, {
                    "product_id": self.ban.id,
                    "product_uom_qty": 1.0,
                    "product_uom": self.ban.uom_id.id,
                    "dlm_move_kind": "output",
                }),
                (0, 0, {
                    "product_id": self.thep.id,
                    "product_uom_qty": qty,
                    "product_uom": self.thep.uom_id.id,
                    "dlm_move_kind": "consume",
                }),
            ],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()
        return picking

    def _mk_order(self):
        return self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": self.ban.display_name,
                "product_id": self.ban.id,
                "qty": 1.0,
                "line_type": "manufactured",
            })],
        })

    def _move_to_workshop(self, qty):
        """Đưa vật tư từ Kho vật tư ra Xưởng — hai chữ ký như K15.

        Đây cũng chính là chỗ FIFO chọn lô: phiếu giữ chỗ ở Kho nguyên vật liệu.
        """
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
            "move_ids": [(0, 0, {
                "name": self.thep.display_name,
                "product_id": self.thep.id,
                "product_uom_qty": qty,
                "product_uom": self.thep.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.loc_xuong.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()
        return picking

    # ------------------------------------------------------------------ tests
    def test_gia_dong_len_lo_khi_nhan_hang(self):
        """TC-INT-TestLotCost-001: Lô mang giá của chính đơn mua đã chốt.

        Đỏ = lô truy được về NCC nhưng không truy được về tiền thì câu "đơn đó lãi bao
        nhiêu" chỉ trả lời được bằng giá bảng hôm nay, tức giá của lô khác.
        """
        order = self._mk_po([(self.thep, 30.0, 200000.0)])
        self._receive_po(order)

        lot = self._lot_of(self.thep)
        self.assertEqual(len(lot), 1)
        self.assertAlmostEqual(lot.dlm_unit_cost, 200000.0, places=2)
        self.assertEqual(lot.dlm_purchase_order_id, order)
        self.assertFalse(lot.dlm_cost_is_estimated)

    def test_nhan_tay_khong_don_mua_thi_gan_co_uoc_tinh(self):
        """TC-INT-TestLotCost-002: MH-16 — không có đơn mua thì vẫn phải có giá, và phải
        nói là ước tính.

        Đỏ = báo cáo giá vốn im lặng tính lô đó bằng 0 thì đơn hàng trông lãi hơn thực
        tế.
        """
        self._apply_price(self.thep, self.vendor, 205000.0)
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": self.vendor.id,
            "location_id": self.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": self.loc_qc.id,
            "move_ids": [(0, 0, {
                "name": self.thep.display_name,
                "product_id": self.thep.id,
                "product_uom_qty": 10.0,
                "product_uom": self.thep.uom_id.id,
                "location_id": self.env.ref(
                    "stock.stock_location_suppliers").id,
                "location_dest_id": self.loc_qc.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 10.0
        picking.move_ids.picked = True
        picking.button_validate()

        lot = picking.move_line_ids.lot_id
        self.assertAlmostEqual(lot.dlm_unit_cost, 205000.0, places=2)
        self.assertTrue(lot.dlm_cost_is_estimated)

    def test_kho_vat_tu_lay_hang_theo_fifo(self):
        """TC-INT-TestLotCost-003: Chiến lược lấy hàng hiệu lực ở Kho vật tư phải là FIFO.

        Odoo mặc định 'fifo' nên hôm nay không cần cấu hình gì — nhưng
        `categ_id.removal_strategy_id` được kiểm trước vị trí, nên chỉ cần ai đó đặt
        chiến lược ở nhóm sản phẩm là toàn bộ giá vốn thực tế đổi nghĩa mà không có màn
        nào báo. Đây là lá chắn cho đúng ca đó.
        """
        method = self.env["stock.quant"]._get_removal_strategy(
            self.thep, self.loc_kho)

        self.assertEqual(method, "fifo")

    def test_vi_du_fifo_lo_cu_truoc(self):
        """TC-INT-TestLotCost-004: đúng ví dụ §6.4: 30 cây @200k + 90 cây @220k, dùng 100.

        30 × 200.000 + 70 × 220.000 = 21.400.000 (tính hết theo giá mới sẽ là 22.000.000
        thì báo lỗ oan 600.000)

        Đỏ = mọi báo cáo lãi/lỗ theo đơn sai, và sai theo hướng bi quan khi giá đang lên
        — tức là đúng lúc doanh nghiệp cần con số nhất.
        """
        cu = self._mk_po([(self.thep, 30.0, 200000.0)])
        self._receive_po(cu)
        moi = self._mk_po([(self.thep, 90.0, 220000.0)])
        self._receive_po(moi)

        order = self._mk_order()
        self._move_to_workshop(100.0)
        self._consume_batch(order, 100.0)

        self.assertAlmostEqual(
            order.dlm_actual_material_cost, 21400000.0, places=0)
        self.assertFalse(order.dlm_cost_is_estimated)

    def test_vat_tu_tra_lai_kho_thi_tru_ra(self):
        """TC-INT-TestLotCost-005: Vật tư bàn giao thừa trả lại kho không được tính vào giá
        vốn.

        Đỏ = đơn gánh tiền của thép chưa hề dùng tới thì càng trả lại nhiều càng trông
        lỗ.
        """
        po = self._mk_po([(self.thep, 50.0, 200000.0)])
        self._receive_po(po)
        order = self._mk_order()
        self._move_to_workshop(40.0)

        picking = self.env["stock.picking"].create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "dlm_sale_order_id": order.id,
            "move_ids": [
                (0, 0, {
                    "product_id": self.ban.id, "product_uom_qty": 1.0,
                    "product_uom": self.ban.uom_id.id,
                    "dlm_move_kind": "output"}),
                (0, 0, {
                    "product_id": self.thep.id, "product_uom_qty": 30.0,
                    "product_uom": self.thep.uom_id.id,
                    "dlm_move_kind": "consume"}),
                (0, 0, {
                    "product_id": self.thep.id, "product_uom_qty": 10.0,
                    "product_uom": self.thep.uom_id.id,
                    "dlm_move_kind": "return"}),
            ],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()

        # Dùng 30, trả lại 10 thì gánh đúng 20 cây × 200.000.
        self.assertAlmostEqual(
            order.dlm_actual_material_cost, 4000000.0, places=0)
