# -*- coding: utf-8 -*-
"""K13 — Nhập thành phẩm (phiếu [8] NTP): đầu ra cho nhánh gia công.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §5.1, §9.1, §11.13.

Vì sao bộ test này đáng có: loại [8] là mắt xích khiến nghiệp vụ LÕI của Đại
Linh chạy được đầu-cuối. Nhưng nó cũng mở ra một ca sai IM LẶNG mới — phiếu [8]
gắn `dlm_sale_order_id` y như phiếu giao, nên nếu đếm chung thì nhập 10 cái bàn
VÀO kho bị tính là đã GIAO 10 cái cho khách. Trên màn hình đơn tự nhảy sang "Đã
giao đủ" trong khi hàng còn nằm nguyên trong Kho thành phẩm, và không có lỗi nào
nổ. Ca đó là `test_phieu_nhap_tp_khong_bi_dem_la_da_giao`.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestFgReceipt(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Khách hàng (K13)", "partner_role": "customer",
            "mobile": "0900000011",
        })
        cls.fg_type = cls.env.ref("dl_inventory.picking_type_mo_receipt")
        cls.loc_production = cls.fg_type.default_location_src_id
        # SP gia công đã thăng hạng (Hạng B): storable, có tồn thật.
        cls.finished = cls.env["product.product"].create({
            "name": "Bàn thép 1m2 (K13)", "product_kind": "manufactured",
        })
        cls.finished.tracking = "none"
        # Bán thành phẩm: theo lô (§3.4) — đường nhập lô KHÁC hẳn hàng NCC giao.
        cls.btp = cls.env["product.product"].create({
            "name": "Khung bàn đã hàn (K13)",
            "product_kind": "material_processed",
        })

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    # 🔴 K16 — KHÔNG khai `location_id`/`location_dest_id` cho dòng: đó chính là
    # bất biến đang test. Vị trí suy từ `dlm_move_kind` + mặt hàng, và `create`
    # đóng dấu chúng. Test mà tự điền vị trí là test một thứ khác.
    def _fg_picking(self, product=None, qty=10.0, order=None, materials=None):
        product = product or self.finished
        moves = []
        if product is not False:
            moves.append((0, 0, {
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "dlm_move_kind": "output",
            }))
        for mat, mat_qty, kind in (materials or []):
            moves.append((0, 0, {
                "product_id": mat.id,
                "product_uom_qty": mat_qty,
                "product_uom": mat.uom_id.id,
                "dlm_move_kind": kind,
            }))
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "dlm_sale_order_id": order.id if order else False,
            "move_ids": moves,
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _validate(self, picking, qty=None):
        """Hoàn tất phiếu ĐÚNG đường nghiệp vụ.

        Phiếu [8] không còn `button_validate` trực tiếp: xưởng bàn giao rồi thủ
        kho mới ký nhận (K16). Phiếu giao hàng thì vẫn xác nhận một bước.
        """
        for move in picking.move_ids:
            move.quantity = qty if qty is not None else move.product_uom_qty
            move.picked = True
        if picking.dlm_needs_receipt:
            picking.action_dlm_handover()
            picking.action_dlm_confirm_receipt()
        else:
            picking.button_validate()
        return picking

    def _order(self, product=None, qty=10.0):
        product = product or self.finished
        return self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "qty": qty,
                "price_unit": 1500000.0,
            })],
        })

    # ── Loại việc & định tuyến form ──────────────────────────────────────────
    def test_nhan_dung_loai_viec_va_form_rieng(self):
        """RS-02 — phiếu [8] KHÔNG được rơi vào form Chuyển kho.

        Cả hai đều `internal`; nhận nhầm là mở ra form cho sửa tự do hai ô vị trí
        và mất luôn dải "không trừ vật tư".
        """
        picking = self._fg_picking()
        self.assertEqual(picking.dlm_picking_kind, "fg_receipt")
        self.assertEqual(
            picking._dlm_form_view(),
            self.env.ref("dl_inventory.view_dl_fg_receipt_form"))

    # ── Luồng chính: hàng làm xong vào kho ───────────────────────────────────
    def test_nhap_thanh_pham_vao_kho_thanh_pham(self):
        """Đầu ra của nhánh gia công: xưởng báo xong ⇒ Kho thành phẩm có hàng."""
        picking = self._validate(self._fg_picking(qty=10.0))

        self.assertEqual(picking.state, "done")
        self.assertEqual(self._qty_at(self.loc_tp, self.finished), 10.0)

    def test_btp_vao_kho_nguyen_vat_lieu_va_tu_sinh_so_lo(self):
        """BTP theo lô: không tự sinh số lô thì màn này là ngõ cụt.

        Hàng chưa từng tồn tại trước phiếu này nên không có lô nào để tra ra —
        mà Odoo bắt buộc số lô lúc validate. Số do Đại Linh tự sinh (chốt K3).
        """
        self.assertEqual(self.btp.tracking, "lot", "Bối cảnh §3.4.")
        picking = self._validate(self._fg_picking(product=self.btp, qty=4.0))
        self.assertEqual(
            picking.move_ids.location_dest_id, self.loc_kho,
            "BTP về Kho nguyên vật liệu — suy từ mặt hàng, không ai chọn tay.")

        self.assertEqual(picking.state, "done")
        self.assertEqual(self._qty_at(self.loc_kho, self.btp), 4.0)
        lot = picking.move_line_ids.lot_id
        self.assertTrue(lot, "Phải có lô — BTP là mắt xích truy vết.")
        self.assertTrue(lot.name.startswith("LO/"),
                        "Số lô phải theo dải LO/ của Đại Linh: %s" % lot.name)

    # ── 🔴 Ca sai im lặng: nhập ≠ giao ───────────────────────────────────────
    def test_phieu_nhap_tp_khong_bi_dem_la_da_giao(self):
        """🔴 Phiếu [8] gắn đơn KHÔNG được tính vào số đã giao của đơn đó.

        Nếu tính chung, đơn nhảy sang "Đã giao đủ" ngay khi hàng vừa vào kho —
        Sales gọi khách báo đã giao, kho thì chưa ai chở đi.
        """
        order = self._order(qty=10.0)
        self._validate(self._fg_picking(qty=10.0, order=order))

        order.invalidate_recordset(
            ["dlm_delivery_state", "dlm_picking_count"])
        self.assertEqual(
            order.dlm_delivery_state, "nothing",
            "Hàng mới vào kho, chưa ai giao cho khách.")
        self.assertEqual(
            order.dlm_picking_count, 0,
            "Smart button 'Phiếu giao hàng' chỉ đếm phiếu GIAO.")

    def test_nhap_xong_roi_giao_thi_don_moi_bao_da_giao(self):
        """Chiều thuận của test trên — chặn tất là cách dễ nhất để 'pass'."""
        order = self._order(qty=10.0)
        self._validate(self._fg_picking(qty=10.0, order=order))

        order.action_dlm_create_delivery()
        delivery = order._dlm_delivery_pickings()
        self._validate(delivery)

        order.invalidate_recordset(["dlm_delivery_state"])
        self.assertEqual(order.dlm_delivery_state, "done")
        self.assertEqual(self._qty_at(self.loc_tp, self.finished), 0.0)

    # ── Lá chắn: chỉ thứ xưởng làm ra, chỉ vào hai chỗ ───────────────────────
    def test_vat_tu_khong_nhap_vao_kho_thanh_pham_duoc(self):
        """Luật §4.2 vẫn áp cho phiếu [8]: Kho thành phẩm là nơi phiếu Giao lấy
        hàng, thứ lọt vào đó sớm muộn cũng bị giao cho khách."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "move_ids": [(0, 0, {
                "product_id": self.material.id,
                "product_uom_qty": 5.0,
                "product_uom": self.material.uom_id.id,
                "dlm_move_kind": "output",
            })],
        })
        self.assertTrue(picking.dlm_blocked)
        with self.assertRaises(UserError) as caught:
            picking.action_confirm()
        self.assertIn("Kho thành phẩm", str(caught.exception))

    def test_danh_sach_mat_hang_thu_hep_theo_don(self):
        """§11.13 — gắn đơn ⇒ chỉ mời chọn thứ đơn đó đặt.

        Nhập nhầm thành phẩm của đơn khác vào phiếu đã gắn đơn làm
        `dlm_delivery_state` của CẢ HAI đơn nói sai.
        """
        khac = self.env["product.product"].create({
            "name": "Kệ thép 5 tầng (K13)", "product_kind": "manufactured",
        })
        picking = self._fg_picking()
        self.assertIn(khac, picking.dlm_fg_product_ids,
                      "Chưa gắn đơn thì mọi thứ xưởng làm ra đều chọn được.")
        self.assertNotIn(
            self.material, picking.dlm_fg_product_ids,
            "Vật tư mua về không phải thứ xưởng làm ra.")

        picking.dlm_sale_order_id = self._order(qty=10.0)
        picking.invalidate_recordset(["dlm_fg_product_ids"])
        self.assertIn(self.finished, picking.dlm_fg_product_ids)
        self.assertNotIn(khac, picking.dlm_fg_product_ids)

    # ── Dải thông báo ────────────────────────────────────────────────────────
    def test_dai_noi_ro_hang_a_khong_vao_ton(self):
        """§11.13 — Hạng A ghi nhận được nhưng KHÔNG sinh tồn, và màn phải nói
        ra: người dùng xác nhận xong, sang màn Tồn kho không thấy gì, rồi kết
        luận phiếu vừa rồi không ăn thua."""
        categ = self.env["product.category"].create({"name": "Bàn thép (K13)"})
        generic = self.env["product.product"].create({
            "name": "Bàn thép khung hộp (K13)",
            "categ_id": categ.id,
            "product_kind": "manufactured",
        })
        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép (K13)",
            "product_category_id": categ.id,
            "generic_product_id": generic.id,
        })
        generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(generic.detailed_type, "consu", "Bối cảnh §3.5.")

        # K16 — Hạng A BẮT BUỘC gắn đơn (nó không vào tồn nên đơn là danh tính
        # duy nhất). Không gắn thì dải chuyển sang đỏ, đúng như test riêng bên
        # dưới kiểm.
        picking = self._fg_picking(
            product=generic, qty=3.0, order=self._order(product=generic, qty=3.0))
        self.assertEqual(picking.dlm_banner_level, "info")
        self.assertIn("không vào tồn kho", picking.dlm_banner_message)
        self.assertFalse(picking.dlm_blocked)

    def test_dai_khong_bao_thieu_hang_o_vi_tri_ao(self):
        """🔴 Nguồn của phiếu [8] là vị trí ẢO Sản xuất — nơi không bao giờ có
        tồn. Rơi vào dải Chuyển kho thì MỌI phiếu nhập thành phẩm đều bị bêu
        "không đủ hàng để chuyển", và người dùng học cách bỏ qua dải cảnh báo."""
        picking = self._fg_picking(qty=10.0)
        self.assertNotEqual(picking.dlm_banner_level, "warning")
        self.assertFalse(picking.dlm_blocked)
