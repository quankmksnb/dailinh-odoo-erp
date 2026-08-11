# -*- coding: utf-8 -*-
"""K6 — Đơn bán hàng ↔ phiếu giao hàng.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §9.1, §11.6, §12.1 (tiêu chí verify K6).

Ba bất biến đắt nhất nếu sai:

  1. Đơn CHƯA chốt không được sinh phiếu giao — phiếu giao giữ chỗ hàng cho một
     cam kết chưa tồn tại, hàng "biến mất" khỏi tồn khả dụng của đơn thật.
  2. SP dùng chung (Hạng A, ``consu``) KHÔNG lên phiếu giao — nó không có tồn,
     dòng sinh ra sẽ treo vĩnh viễn ở trạng thái chờ hàng.
  3. Đơn đã có phiếu giao KHÔNG đưa về nháp được — sửa lại đơn đã giao là làm
     lệch chứng từ kho với chứng từ bán.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestDeliveryLink(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách hàng (test)",
            "partner_role": "customer",
        })
        # Hàng thương mại: storable, KHÔNG theo lô (§3.4) — giao thẳng, không
        # phải khai lô ở mỗi bước, giữ test tập trung vào mối nối đơn ↔ phiếu.
        cls.goods = cls.env["product.product"].create({
            "name": "Bản lề inox (test)",
            "product_kind": "trading",
        })
        cls.goods.tracking = "none"

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _make_order(self, product=None, qty=10.0, state="confirmed"):
        product = product or self.goods
        order = self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": state,
            "line_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "qty": qty,
                "price_unit": 50000.0,
            })],
        })
        return order

    def _stock_up(self, product, qty, location):
        """Đặt tồn đầu kỳ mà không đi qua phiếu nhận — test này nói về GIAO
        hàng, không phải về nhập hàng (đã có test riêng)."""
        self.env["stock.quant"].with_context(
            inventory_mode=True).create({
                "product_id": product.id,
                "location_id": location.id,
                "inventory_quantity": qty,
            }).action_apply_inventory()

    def _delivery_of(self, order):
        return order.dlm_picking_ids[:1]

    # ── Ca test ──────────────────────────────────────────────────────────────
    def test_don_nhap_khong_tao_duoc_phieu_giao(self):
        """§11.6 — Chặn tạo phiếu giao khi đơn còn Nháp, nêu rõ lý do."""
        order = self._make_order(state="draft")
        with self.assertRaises(UserError) as caught:
            order.action_dlm_create_delivery()
        self.assertIn("Nháp", str(caught.exception))
        self.assertFalse(order.dlm_picking_ids)

    def test_tao_phieu_giao_tu_don_da_xac_nhan(self):
        """Đơn confirmed ⇒ [Tạo phiếu giao] ra đúng một phiếu, đúng số lượng."""
        order = self._make_order(qty=10.0)
        order.action_dlm_create_delivery()

        picking = self._delivery_of(order)
        self.assertTrue(picking, "Phải sinh ra phiếu giao.")
        self.assertEqual(picking.picking_type_id.code, "outgoing")
        self.assertEqual(picking.partner_id, self.customer)
        self.assertEqual(picking.dlm_sale_order_id, order)
        self.assertEqual(len(picking.move_ids), 1)
        self.assertEqual(picking.move_ids.product_uom_qty, 10.0)
        self.assertEqual(
            picking.location_id, self.loc_tp,
            "Phiếu giao lấy hàng từ Kho thành phẩm (§5.3).")

    def test_khong_tao_hai_phieu_cho_cung_mot_luong_hang(self):
        """Bấm nút hai lần KHÔNG được nhân đôi số hàng phải giao.

        Không chặn thì kho nhận hai phiếu cùng 10 cái và giao 20 — không chứng
        từ nào cảnh báo, chỉ tồn kho âm mới lộ ra.
        """
        order = self._make_order(qty=10.0)
        order.action_dlm_create_delivery()
        with self.assertRaises(UserError):
            order.action_dlm_create_delivery()
        self.assertEqual(len(order.dlm_picking_ids), 1)

    def test_sp_dung_chung_khong_len_phieu_giao(self):
        """§3.5 + §9.1 — Dòng SP generic (consu) đi thẳng từ xưởng, không qua kho."""
        categ = self.env["product.category"].create({"name": "Bàn thép (K6)"})
        generic = self.env["product.product"].create({
            "name": "Bàn thép khung hộp (K6)",
            "categ_id": categ.id,
            "product_kind": "manufactured",
        })
        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép (K6)",
            "product_category_id": categ.id,
            "generic_product_id": generic.id,
        })
        generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(generic.detailed_type, "consu", "Bối cảnh §3.5.")

        order = self._make_order(product=generic, qty=3.0)
        self.assertFalse(
            order.dlm_has_deliverable,
            "Đơn toàn SP dùng chung thì không có gì đi qua kho.")
        with self.assertRaises(UserError) as caught:
            order.action_dlm_create_delivery()
        self.assertIn("không có mặt hàng nào đi qua kho",
                      str(caught.exception))

    def test_giao_du_thi_don_chuyen_sang_da_giao_du(self):
        """Tiêu chí verify K6: giao xong ⇒ dlm_delivery_state = 'done'."""
        order = self._make_order(qty=10.0)
        self.assertEqual(order.dlm_delivery_state, "nothing")

        self._stock_up(self.goods, 10.0, self.loc_tp)
        order.action_dlm_create_delivery()
        picking = self._delivery_of(order)
        picking.move_ids.quantity = 10.0
        picking.move_ids.picked = True
        picking.button_validate()

        order.invalidate_recordset(["dlm_delivery_state"])
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.dlm_delivery_state, "done")
        self.assertEqual(self._qty_at(self.loc_tp, self.goods), 0.0)

    def test_giao_mot_phan_thi_don_o_trang_thai_giao_mot_phan(self):
        """Giao 6/10 ⇒ 'partial' — KHÔNG được báo 'done' khi còn nợ khách 4."""
        order = self._make_order(qty=10.0)
        self._stock_up(self.goods, 6.0, self.loc_tp)
        order.action_dlm_create_delivery()

        picking = self._delivery_of(order)
        picking.move_ids.quantity = 6.0
        picking.move_ids.picked = True
        # skip_backorder: phần còn thiếu tự tách sang phiếu mới, không hỏi modal.
        picking.with_context(skip_backorder=True).button_validate()

        order.invalidate_recordset(["dlm_delivery_state"])
        self.assertEqual(order.dlm_delivery_state, "partial")

    def test_don_da_co_phieu_giao_thi_khong_ve_nhap_duoc(self):
        """Tiêu chí verify K6 — khoá này do `_reset_draft_blockers` tự dò qua
        metadata (dl_sale), `dlm_sale_order_id` là thứ kích hoạt nó."""
        order = self._make_order(qty=10.0)
        order.action_dlm_create_delivery()

        blockers = order._reset_draft_blockers()
        self.assertTrue(
            blockers,
            "Phiếu giao phải xuất hiện trong danh sách chứng từ hạ nguồn.")
        with self.assertRaises(UserError):
            order._check_can_reset_draft()

    def test_preset_chuyen_kho_dat_dung_hai_dau_tuyen(self):
        """§11.5 — Preset phải đổi vị trí trên CẢ phiếu lẫn dòng hàng.

        Chỉ đổi trên phiếu thì hàng vẫn chạy theo vị trí cũ ghi ở dòng — phiếu
        nói một đằng, tồn kho đi một nẻo.
        """
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
            "move_ids": [(0, 0, {
                "name": self.goods.name,
                "product_id": self.goods.id,
                "product_uom_qty": 5.0,
                "product_uom": self.goods.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.loc_xuong.id,
            })],
        })
        picking.action_dlm_preset_to_fg()

        self.assertEqual(picking.location_dest_id, self.loc_tp)
        self.assertEqual(picking.move_ids.location_dest_id, self.loc_tp)
        self.assertEqual(picking.move_ids.location_id, self.loc_kho)
