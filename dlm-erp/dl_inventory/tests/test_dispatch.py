# -*- coding: utf-8 -*-
"""K16 — Kiểm tra kho & Điều phối đơn bán hàng.

Bất biến lớn nhất bộ này canh: **một lần bấm ra đúng bộ chứng từ, bấm lần hai
không nhân đôi chỗ giữ**. Giữ chỗ gấp đôi không báo lỗi gì — nó chỉ làm đơn thứ
ba thấy hết hàng trong khi kho đang đầy.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_inventory")
class TestDispatch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loc_kho = cls.env.ref("dl_inventory.stock_location_nhan_kho")
        cls.loc_tp = cls.env.ref("dl_inventory.stock_location_tp")
        cls.loc_xuong = cls.env.ref("dl_inventory.stock_location_xuong")
        cls.customer = cls.env["res.partner"].create({
            "name": "Trường Nam Thái (điều phối)", "partner_role": "customer"})

        cls.thep = cls._mk("material", "Thép hộp 30x60 (điều phối)")
        cls.hang_tm = cls._mk("trading", "Cầu trượt liên hoàn (điều phối)")
        cls.ban = cls._mk("manufactured", "Bàn học sinh (điều phối)")
        # Hạng A — sản phẩm đặt riêng, không đi qua tồn kho.
        cls.dat_rieng = cls.env["product.product"].create({
            "name": "Khung sắt đặt riêng (điều phối)",
            "product_kind": "manufactured",
            "detailed_type": "consu",
        })
        # Vai trò THẬT để chạy màn này. Test chạy bằng admin không bao giờ
        # chạm vào ACL, mà ACL mới là thứ hỏng ngoài đời.
        # ⚠️ Phải có `email`: `action_dlm_dispatch` ghi chatter, mà `message_post`
        # từ chối khi tác giả không có địa chỉ gửi. User thật của Đại Linh đều
        # có email (xem demo_users_data.xml) — thiếu ô này là lỗi của FIXTURE,
        # không phải của luồng điều phối.
        cls.thu_kho = cls.env["res.users"].create({
            "name": "Thủ kho (điều phối)", "login": "thukho_dispatch_test",
            "email": "thukho.dispatch@test.local",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })

    @classmethod
    def _mk(cls, kind, name):
        return cls.env["product.product"].create(
            {"name": name, "product_kind": kind})

    # ------------------------------------------------------------------ helpers
    def _mk_bom(self, product, lines):
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": material.id,
                "quantity": qty,
                "is_override": True,
            }) for material, qty in lines],
        })
        bom.status = "confirmed"
        return bom

    def _mk_order(self, lines):
        """lines = [(product, qty, line_type, bom)]"""
        order = self.env["dl.sale.order"].create({
            "partner_id": self.customer.id,
            "state": "confirmed",
            "line_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "qty": qty,
                "line_type": line_type,
                "bom_id": bom.id if bom else False,
            }) for product, qty, line_type, bom in lines],
        })
        return order

    def _stock_up(self, product, qty, location):
        vals = {
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }
        if product.tracking == "lot":
            vals["lot_id"] = self.env["stock.lot"].create({
                "name": "LOT-DP-%s-%s" % (product.id, location.id),
                "product_id": product.id,
                "company_id": self.env.company.id,
            }).id
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            vals).action_apply_inventory()

    def _material_pickings(self, order):
        return order.dlm_picking_ids.filtered(
            lambda p: p.location_dest_id == self.loc_xuong)

    def _delivery_pickings(self, order):
        return order.dlm_picking_ids.filtered(
            lambda p: p.picking_type_id.sequence_code == "GH")

    # ------------------------------------------------------------------ tests
    def test_du_thanh_pham_thi_chi_ra_phieu_giao(self):
        """Kho có sẵn thành phẩm ⇒ giao thẳng, KHÔNG cấp vật tư.

        Đỏ = xưởng nhận lệnh làm lại món đã có trong kho.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.5)])
        order = self._mk_order([(self.ban, 4.0, "manufactured", bom)])
        self._stock_up(self.ban, 10.0, self.loc_tp)

        # Chạy bằng vai trò THẬT: nhánh sinh phiếu giao cũng phải đi qua được
        # ACL của thủ kho, không chỉ nhánh cấp vật tư.
        order.with_user(self.thu_kho).action_dlm_dispatch()

        self.assertEqual(len(self._delivery_pickings(order)), 1)
        self.assertFalse(self._material_pickings(order))

    def test_hang_dat_rieng_khong_tinh_ton_thanh_pham(self):
        """DP-10 — Hạng A luôn phải làm 100% số đơn, kể cả khi trùng tên hàng
        đang có trong kho.

        Đỏ = báo "đủ hàng" cho món khách đặt riêng ⇒ giao nhầm hàng của đơn khác.
        """
        bom = self._mk_bom(self.dat_rieng, [(self.thep, 3.0)])
        order = self._mk_order([(self.dat_rieng, 5.0, "manufactured", bom)])
        self._stock_up(self.thep, 100.0, self.loc_kho)

        check = order._dlm_supply_check()

        row = check["goods"][0]
        self.assertTrue(row["made_to_order"])
        self.assertEqual(row["ready"], 0.0)
        self.assertEqual(row["to_make"], 5.0)
        # 5 × 3 = 15 cây thép, không trừ gì cả.
        self.assertAlmostEqual(check["materials"][0]["need"], 15.0, places=2)

    def test_thieu_vat_tu_van_giu_phan_dang_co(self):
        """🔴 Kịch bản C — chờ mua đủ mới giữ chỗ là để đơn khác bốc mất phần
        đang có.

        Đỏ = phiếu cấp vật tư không được tạo, 20 cây thép đang có bị đơn sau lấy,
        và khi thép mới về thì lại thiếu thứ khác.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 30.0, "manufactured", bom)])
        self._stock_up(self.thep, 20.0, self.loc_kho)

        order.action_dlm_dispatch()

        picking = self._material_pickings(order)
        self.assertEqual(len(picking), 1)
        # Nhu cầu ĐỦ 60 cây lên phiếu, giữ chỗ được 20 ⇒ phiếu thiếu một phần.
        self.assertAlmostEqual(
            sum(picking.move_ids.mapped("product_uom_qty")), 60.0, places=2)
        # ⚠️ Odoo 17 KHÔNG còn trạng thái `partially_available` ở tầng phiếu
        # (doc B1.5 §3.3 viết theo bản cũ): phiếu giữ được một phần vẫn là
        # `assigned`. Bằng chứng "giữ được bao nhiêu" nằm ở số đã giữ, không ở
        # trạng thái — nên đo đúng chỗ đó.
        self.assertEqual(picking.state, "assigned")
        self.assertAlmostEqual(
            sum(picking.move_ids.mapped("quantity")), 20.0, places=2)

    def test_bam_lan_hai_bi_chan(self):
        """🔴 DP-08 — bấm hai lần là giữ chỗ gấp đôi.

        Đỏ = kho báo hết hàng trong khi hàng còn nguyên: nó đang bị chính đơn
        đó giữ hai lần.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 10.0, "manufactured", bom)])
        self._stock_up(self.thep, 100.0, self.loc_kho)
        order.action_dlm_dispatch()
        truoc = sum(self._material_pickings(order).move_ids.mapped(
            "product_uom_qty"))

        with self.assertRaises(UserError):
            order.action_dlm_dispatch()

        sau = sum(self._material_pickings(order).move_ids.mapped(
            "product_uom_qty"))
        self.assertEqual(truoc, sau)

    def test_dong_gia_cong_thieu_bom_thi_chan_va_neu_ten(self):
        """DP-03 — không có định mức thì điều phối vẫn "chạy" nhưng ra kết quả
        sai mà trông như đúng.

        Đỏ = đơn được điều phối với nhu cầu vật tư = 0 ⇒ xưởng không có gì để làm.
        """
        order = self._mk_order([(self.ban, 10.0, "manufactured", False)])

        check = order._dlm_supply_check()
        self.assertTrue(check["blocking"])
        self.assertIn(self.ban.display_name, check["blocking"][0])

        with self.assertRaises(UserError):
            order.action_dlm_dispatch()

    def test_hang_thuong_mai_thieu_thi_phai_mua_chinh_no(self):
        """U-5 — gần một nửa doanh thu của Đại Linh không có BOM.

        Đỏ = nhánh thương mại rơi khỏi hệ thống: màn báo thiếu nhưng không nói
        phải mua gì, và Mua hàng không bao giờ nhận được việc.
        """
        order = self._mk_order([(self.hang_tm, 3.0, "trading", False)])

        check = order._dlm_supply_check()

        self.assertFalse(check["blocking"])
        self.assertEqual(len(check["materials"]), 1)
        self.assertEqual(check["materials"][0]["product"], self.hang_tm)
        self.assertAlmostEqual(check["materials"][0]["missing"], 3.0, places=2)

    def test_trang_thai_dieu_phoi_suy_tu_chung_tu(self):
        """`dlm_dispatch_state` phải đổi theo CHỨNG TỪ, không theo tồn kho.

        Đỏ = depends vào stock.quant ⇒ mỗi phiếu kho validate là recompute mọi
        đơn; hệ thống bò dần và không ai biết vì sao.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 5.0, "manufactured", bom)])
        self.assertEqual(order.dlm_dispatch_state, "to_dispatch")

        self._stock_up(self.thep, 100.0, self.loc_kho)
        order.action_dlm_dispatch()

        # Có phiếu cấp vật tư nhưng hàng chưa giao ⇒ vẫn đang điều phối.
        self.assertEqual(order.dlm_dispatch_state, "dispatching")

    def test_sales_khong_bam_duoc_nut_dieu_phoi(self):
        """U-4 — một chủ sở hữu cho bước điều phối là Thủ kho.

        Đỏ = hai vai cùng bấm được ⇒ đơn nằm chờ vì "tưởng bên kia làm", hoặc
        cùng bấm ra hai bộ chứng từ.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 5.0, "manufactured", bom)])
        self._stock_up(self.thep, 100.0, self.loc_kho)
        sales = self.env["res.users"].create({
            "name": "Sales (điều phối)", "login": "sales_dispatch_test",
            "groups_id": [(6, 0, [self.env.ref("dl_base.dl_group_ba").id])],
        })

        with self.assertRaises(UserError):
            order.with_user(sales)._dlm_check_dispatch_allowed()

    def test_thu_kho_mo_man_dieu_phoi_khong_dinh_loi_quyen(self):
        """🔴 Chạy bằng ĐÚNG vai trò Thủ kho, không phải admin.

        Định mức (`dl.bom`) là tài sản của Kỹ thuật — thủ kho KHÔNG có quyền
        đọc. Mọi đường chạm BOM ở màn này phải đi qua `sudo()` và chỉ để số
        LƯỢNG đi ra.

        Đỏ = thủ kho mở đơn gia công là thấy dải đỏ "bạn không được phép truy
        cập dữ liệu BOM" — màn Điều phối vô dụng đúng với nhánh hàng chính của
        Đại Linh. Mọi test khác của file này chạy bằng admin nên KHÔNG bắt được
        ca này; đã lọt ra tới người dùng thật một lần (2026-08-14).
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 6.0, "manufactured", bom)])
        self._stock_up(self.thep, 100.0, self.loc_kho)

        nhu_thu_kho = order.with_user(self.thu_kho)
        check = nhu_thu_kho._dlm_supply_check()

        self.assertFalse(check["blocking"], check["blocking"])
        self.assertAlmostEqual(
            check["materials"][0]["need"], 12.0, places=2)
        # Dải trên form cũng phải sạch — nó đọc cùng một hàm.
        self.assertNotEqual(nhu_thu_kho.dlm_supply_level, "danger")

    def test_thu_kho_bam_dieu_phoi_ra_dung_chung_tu(self):
        """Toàn bộ hành động chạy bằng vai trò Thủ kho, không phải admin.

        Đỏ = nút bấm được nhưng ném lỗi quyền ở giữa chừng, và đơn nằm lại với
        một nửa bộ chứng từ.
        """
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 6.0, "manufactured", bom)])
        self._stock_up(self.thep, 100.0, self.loc_kho)

        order.with_user(self.thu_kho).action_dlm_dispatch()

        picking = self._material_pickings(order)
        self.assertEqual(len(picking), 1)
        self.assertAlmostEqual(
            sum(picking.move_ids.mapped("product_uom_qty")), 12.0, places=2)

    def test_don_nhap_khong_dieu_phoi_duoc(self):
        """DP-01 — điều phối đơn nháp là giữ chỗ cho cam kết chưa tồn tại."""
        bom = self._mk_bom(self.ban, [(self.thep, 2.0)])
        order = self._mk_order([(self.ban, 5.0, "manufactured", bom)])
        order.state = "draft"

        with self.assertRaises(UserError):
            order.action_dlm_dispatch()
