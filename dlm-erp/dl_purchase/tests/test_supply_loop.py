# -*- coding: utf-8 -*-
"""K22 — VÒNG KHÉP KÍN: đơn bán thiếu hàng → mua → nhận → điều phối lại thấy đủ.

Đây là phép thử duy nhất chứng minh cả chuỗi hoạt động như một hệ thống chứ
không phải như sáu tính năng rời. Nếu chỉ giữ được một test của cả đợt này thì
giữ ``test_vong_khep_kin``.
"""

from odoo.tests.common import tagged

from .common import DlPurchaseCase


@tagged("post_install", "-at_install", "dl_purchase")
class TestSupplyLoop(DlPurchaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ban = cls.env["product.product"].create({
            "name": "Bàn học sinh (vòng lặp)", "product_kind": "manufactured"})
        cls.hang_tm = cls.env["product.product"].create({
            "name": "Cầu trượt liên hoàn (vòng lặp)", "product_kind": "trading"})

    def _mk_bom(self, product, material, qty):
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": material.id, "quantity": qty,
                "is_override": True})],
        })
        bom.status = "confirmed"
        return bom

    def _mk_sale_order(self, product, qty, line_type, bom=None):
        return self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "qty": qty,
                "line_type": line_type,
                "bom_id": bom.id if bom else False,
            })],
        })

    # ------------------------------------------------------------------ tests
    def test_dieu_phoi_thieu_sinh_don_mua_nhap_gom_theo_ncc(self):
        """Thiếu vật tư ⇒ đơn mua NHÁP đã gom sẵn, gắn ngược về đơn bán.

        Đỏ = Mua hàng phải tự đoán cần mua gì cho đơn nào; và khi hàng về không
        ai biết nó dành cho ai.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        order.action_dlm_dispatch()

        po = order.dlm_purchase_order_ids
        self.assertEqual(len(po), 1)
        self.assertEqual(po.state, "draft")
        self.assertEqual(po.partner_id, self.vendor)
        self.assertAlmostEqual(po.line_ids.qty, 20.0, places=2)
        self.assertAlmostEqual(po.line_ids.price_unit, 200000.0, places=2)
        self.assertIn(order, po.dlm_origin_order_ids)

    def test_hang_thuong_mai_thieu_cung_len_don_mua(self):
        """U-5 — gần một nửa doanh thu không có BOM.

        Đỏ = nhánh thương mại rơi khỏi hệ thống: màn báo thiếu nhưng Mua hàng
        không nhận được việc nào.
        """
        self._apply_price(self.hang_tm, self.vendor, 5900000.0)
        order = self._mk_sale_order(self.hang_tm, 3.0, "trading")

        order.action_dlm_dispatch()

        po = order.dlm_purchase_order_ids
        self.assertEqual(len(po), 1)
        self.assertEqual(po.line_ids.product_id, self.hang_tm)
        self.assertAlmostEqual(po.line_ids.qty, 3.0, places=2)

    def test_khong_co_ncc_thi_khong_len_don_nhung_phai_noi(self):
        """MH-14 — im lặng bỏ qua là Mua hàng không bao giờ biết cần mua món đó.

        Đỏ = một vật tư biến mất khỏi cả hai phía: kho không có, mua hàng không
        biết.
        """
        bom = self._mk_bom(self.ban, self.thep, 2.0)   # thép CHƯA có bảng giá
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        labels = order._dlm_dispatch_shortage([
            {"product": self.thep, "missing": 20.0}])

        self.assertFalse(order.dlm_purchase_order_ids)
        self.assertTrue(labels)
        self.assertIn(self.thep.display_name, labels[0])

    def test_gom_nhieu_don_ban_vao_mot_don_mua_giu_du_dau_vet(self):
        """🔴 M2M chứ không M2O: ép về một đơn là mất dấu các đơn còn lại."""
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        don_a = self._mk_sale_order(self.ban, 5.0, "manufactured", bom)
        don_b = self._mk_sale_order(self.ban, 7.0, "manufactured", bom)

        don_a.action_dlm_dispatch()
        don_b.action_dlm_dispatch()
        po_a = don_a.dlm_purchase_order_ids
        po_b = don_b.dlm_purchase_order_ids

        # Mỗi lượt điều phối sinh đơn riêng, nhưng mỗi đơn mua vẫn neo đúng đơn
        # bán của nó — và quan hệ là nhiều-nhiều nên gom được về sau.
        self.assertIn(don_a, po_a.dlm_origin_order_ids)
        self.assertIn(don_b, po_b.dlm_origin_order_ids)
        po_a.dlm_origin_order_ids = [(4, don_b.id)]
        self.assertIn(po_a, don_b.dlm_purchase_order_ids)

    def test_vong_khep_kin(self):
        """🔴 Điều phối thiếu → mua → nhận → kiểm → ĐIỀU PHỐI LẠI THẤY ĐỦ.

        Đỏ = vòng không khép: hàng về kho rồi mà đơn bán vẫn treo, hoặc phải gõ
        tay lại từ đầu. Đây là lý do tồn tại của cả đợt K15–K22.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        # 1. Kho trống ⇒ điều phối báo thiếu 20 cây và đẩy sang Mua hàng.
        check = order._dlm_supply_check()
        self.assertAlmostEqual(check["materials"][0]["missing"], 20.0, places=2)
        order.action_dlm_dispatch()
        po = order.dlm_purchase_order_ids
        self.assertTrue(po)

        # 2. Mua hàng chốt giá, NCC giao, thủ kho nhận & kiểm.
        po.date_expected = self.env.cr.now()
        self._receive_po(po)

        # 3. Đơn CŨ điều phối lại: nhu cầu đã có chứng từ nên không đòi thêm,
        #    và số thiếu về 0 — hàng đã nằm trong Kho nguyên vật liệu.
        lai = order._dlm_supply_check()
        self.assertFalse([row for row in lai["materials"]
                          if row["missing"] > 0])
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.thep.id),
            ("location_id", "=", self.loc_kho.id),
        ])
        self.assertAlmostEqual(sum(quants.mapped("quantity")), 20.0, places=2)
