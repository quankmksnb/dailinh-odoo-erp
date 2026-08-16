# -*- coding: utf-8 -*-
"""K22 — vòng khép kín: đơn bán thiếu hàng thì mua thì nhận thì điều phối lại thấy đủ.

Đây là phép thử duy nhất chứng minh cả chuỗi hoạt động như một hệ thống chứ không phải
như sáu tính năng rời. Nếu chỉ giữ được một test của cả đợt này thì giữ
``test_vong_khep_kin``.
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
        cls.buyer = cls.env["res.users"].create({
            "name": "Mua hàng (vòng lặp)", "login": "muahang_supply_test",
            "email": "muahang.supply@test.local",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })

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
        """TC-INT-TestSupplyLoop-001: Thiếu vật tư thì đơn mua nháp đã gom sẵn, gắn ngược
        về đơn bán.

        Đỏ = Mua hàng phải tự đoán cần mua gì cho đơn nào; và khi hàng về không ai biết
        nó dành cho ai.
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

    def test_bom_nhieu_ncc_thi_tach_don_theo_tung_ncc(self):
        """TC-INT-TestSupplyLoop-002: Một BOM thường gọi tên nhiều nhà cung cấp — mỗi NCC
        một đơn.

        Đỏ = trộn hàng của hai NCC vào một đơn: gửi đi thì NCC này đọc được mặt hàng và
        giá của NCC kia, mà cũng không bên nào nhận trọn đơn được.

        Cũng canh chiều ngược lại: hai vật tư cùng một NCC phải nằm CHUNG một đơn, không
        phải mỗi vật tư một đơn.
        """
        ncc_b = self.env["res.partner"].create({
            "name": "Phú Thịnh (vòng lặp)", "partner_role": "supplier",
            "mobile": "0900000003"})
        oc_vit = self.env["product.product"].create({
            "name": "Ốc vít M6 (vòng lặp)", "product_kind": "material"})
        ban_le = self.env["product.product"].create({
            "name": "Bản lề lá 3 inch (vòng lặp)", "product_kind": "material"})
        self._apply_price(self.thep, self.vendor, 200000.0)
        self._apply_price(oc_vit, self.vendor, 1500.0)
        self._apply_price(ban_le, ncc_b, 3900.0)

        bom = self.env["dl.bom"].create({
            "product_id": self.ban.id,
            "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": material.id, "quantity": qty,
                "is_override": True,
            }) for material, qty in (
                (self.thep, 2.0), (oc_vit, 10.0), (ban_le, 4.0))],
        })
        bom.status = "confirmed"
        order = self._mk_sale_order(self.ban, 5.0, "manufactured", bom)

        order.action_dlm_dispatch()

        orders = order.dlm_purchase_order_ids
        self.assertEqual(len(orders), 2)
        don_a = orders.filtered(lambda o: o.partner_id == self.vendor)
        don_b = orders.filtered(lambda o: o.partner_id == ncc_b)
        self.assertEqual(set(don_a.line_ids.mapped("product_id")),
                         {self.thep, oc_vit})
        self.assertEqual(don_b.line_ids.product_id, ban_le)
        # Số lượng theo định mức × 5 cái, không lẫn giữa hai đơn.
        self.assertAlmostEqual(
            don_a.line_ids.filtered(lambda l: l.product_id == oc_vit).qty,
            50.0, places=2)
        self.assertAlmostEqual(don_b.line_ids.qty, 20.0, places=2)

    def test_hang_thuong_mai_thieu_cung_len_don_mua(self):
        """TC-INT-TestSupplyLoop-003: U-5 — gần một nửa doanh thu không có BOM.

        Đỏ = nhánh thương mại rơi khỏi hệ thống: màn báo thiếu nhưng Mua hàng không nhận
        được việc nào.
        """
        self._apply_price(self.hang_tm, self.vendor, 5900000.0)
        order = self._mk_sale_order(self.hang_tm, 3.0, "trading")

        order.action_dlm_dispatch()

        po = order.dlm_purchase_order_ids
        self.assertEqual(len(po), 1)
        self.assertEqual(po.line_ids.product_id, self.hang_tm)
        self.assertAlmostEqual(po.line_ids.qty, 3.0, places=2)

    def test_khong_co_ncc_thi_khong_len_don_nhung_phai_noi(self):
        """TC-INT-TestSupplyLoop-004: MH-14 — im lặng bỏ qua là Mua hàng không bao giờ biết
        cần mua món đó.

        Đỏ = một vật tư biến mất khỏi cả hai phía: kho không có, mua hàng không biết.
        """
        bom = self._mk_bom(self.ban, self.thep, 2.0)   # thép CHƯA có bảng giá
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        labels = order._dlm_dispatch_shortage([
            {"product": self.thep, "missing": 20.0}])

        self.assertFalse(order.dlm_purchase_order_ids)
        self.assertTrue(labels)
        self.assertIn(self.thep.display_name, labels[0])

    def test_gom_nhieu_don_ban_vao_mot_don_mua_giu_du_dau_vet(self):
        """TC-INT-TestSupplyLoop-005: M2M chứ không M2O: ép về một đơn là mất dấu các đơn
        còn lại.
        """
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
        """TC-INT-TestSupplyLoop-006: Điều phối thiếu thì mua thì nhận thì kiểm thì điều
        phối lại thấy đủ.

        Đỏ = vòng không khép: hàng về kho rồi mà đơn bán vẫn treo, hoặc phải gõ tay lại
        từ đầu. Đây là lý do tồn tại của cả đợt K15–K22.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        # 1. Kho trống thì điều phối báo thiếu 20 cây và đẩy sang Mua hàng.
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

    def test_mua_hang_doc_duoc_don_ban_gan_tren_don_mua(self):
        """TC-INT-TestSupplyLoop-007: ô "Đơn bán đang chờ" là câu trả lời cho "mua cái này
        cho ai".

        Đỏ = Mua hàng mở chính đơn mà điều phối vừa giao cho họ thì ăn AccessError
        'dl.sale.order' — nút bấm được, đơn mở không được.

        Chạy bằng vai trò thật: `env.su` của TransactionCase bỏ qua ACL, nên test chạy
        bằng admin sẽ xanh trong khi ngoài đời vẫn đỏ.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)
        order.action_dlm_dispatch()
        po = order.dlm_purchase_order_ids

        # Phải xoá cache trước: `display_name` đã được đọc lúc điều phối (bằng
        # quyền admin) nên còn nằm trong cache của transaction — đọc lại chỉ lấy
        # từ cache, KHÔNG chạm ACL, và test xanh trong khi ngoài đời vẫn đỏ.
        self.env.invalidate_all()

        # Đúng thứ client đọc cho `widget="many2many_tags"`: id rồi display_name.
        tags = po.with_user(self.buyer).dlm_origin_order_ids
        self.assertEqual(tags.mapped("display_name"), [order.name])


    # --------------------------------- Báo Mua hàng: TỰ ĐỘNG, không có nút
    def test_dieu_phoi_tu_giao_viec_kem_danh_sach_vat_tu(self):
        """TC-INT-TestSupplyLoop-008: Activity không chỉ là việc trong app —
        `mail.activity.create` gọi `action_notify()` thì `message_notify()` thì đây là
        lá thư Mua hàng nhận.

        Nên nó phải nêu số và tên. Đỏ = Mua hàng nhận thư "có hàng cần mua" rồi vẫn phải
        mở từng đơn ra đếm — đúng việc mà lời báo sinh ra để thay thế.

        Người dùng chốt 2026-08-14: báo phải tự động theo cú bấm Điều phối, chứ không
        qua một nút riêng phải nhớ bấm.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        order.action_dlm_dispatch()

        po = order.dlm_purchase_order_ids
        viec = self.env["mail.activity"].search([
            ("res_model", "=", "dl.purchase.order"), ("res_id", "=", po.id),
            ("user_id", "=", self.buyer.id)])
        self.assertTrue(viec, "Phải giao việc cho Mua hàng ngay khi điều phối.")
        self.assertIn(order.name, viec[0].summary)
        self.assertIn("Thép hộp 30x60x1.4", viec[0].note)
        self.assertIn("20", viec[0].note)

    def test_thu_bao_mua_hang_khong_lot_gia(self):
        """TC-INT-TestSupplyLoop-009: Giá trên đơn nháp là giá bảng, còn phải hỏi lại NCC.
        Đưa vào thư là tự chốt hộ mức trước khi đàm phán — cùng luật với biên bản K17.
        """
        self._apply_price(self.thep, self.vendor, 200000.0)
        bom = self._mk_bom(self.ban, self.thep, 2.0)
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        order.action_dlm_dispatch()

        note = self.env["mail.activity"].search([
            ("res_model", "=", "dl.purchase.order"),
            ("res_id", "=", order.dlm_purchase_order_ids.id)])[0].note
        for so_tien in ("200000", "200.000", "4000000", "4.000.000"):
            self.assertNotIn(so_tien, note)

    def test_vat_tu_khong_co_ncc_van_phai_giao_viec(self):
        """TC-INT-TestSupplyLoop-010: Ca duy nhất thiếu hàng mà không sinh đơn mua nào thì
        trước đây cũng là ca duy nhất không có activity nào: im lặng đúng chỗ nguy hiểm
        nhất.

        Đỏ = dấu vết duy nhất là một dòng chatter trên đơn bán — màn mà Mua hàng không
        có lý do gì để mở. Vật tư đó không bao giờ được mua.
        """
        bom = self._mk_bom(self.ban, self.thep, 2.0)   # thép CHƯA có bảng giá
        order = self._mk_sale_order(self.ban, 10.0, "manufactured", bom)

        order.action_dlm_dispatch()

        self.assertFalse(order.dlm_purchase_order_ids)
        viec = self.env["mail.activity"].search([
            ("res_model", "=", "dl.sale.order"), ("res_id", "=", order.id),
            ("user_id", "=", self.buyer.id)])
        self.assertTrue(viec, "Không có đơn mua thì việc phải gắn lên đơn bán.")
        self.assertIn(self.thep.display_name, viec[0].note)
