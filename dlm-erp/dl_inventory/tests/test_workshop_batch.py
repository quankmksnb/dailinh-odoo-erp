# -*- coding: utf-8 -*-
"""K16 — Phiếu mẻ "Nhập kho từ xưởng": một chứng từ cho trọn một mẻ sản xuất.

Vì sao bộ test này đáng có: trước K16, phiếu [8] chỉ CỘNG thành phẩm vào kho mà
không trừ vật tư nào. Hệ quả không nổ lỗi nào nhưng sai thật — 100 cây thép đã
thành 10 cái bàn vẫn nằm nguyên trên sổ ở Xưởng, và tồn kho báo "100 cây thép +
10 cái bàn" trong khi ngoài đời chỉ có 10 cái bàn.

Bất biến trung tâm được canh ở đây: **sổ chỉ ghi thứ đi qua cửa**. Rời Xưởng là
THÉP (nguồn thật, trừ tồn Xưởng); vào kho là BÀN (nguồn ảo Sản xuất, vì cái bàn
chưa từng tồn tại ở Xưởng trên sổ). Lẫn hai cái đó là tồn âm vĩnh viễn.
"""

from odoo.exceptions import UserError
from odoo.tests.common import Form, tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestWorkshopBatch(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fg_type = cls.env.ref("dl_inventory.picking_type_mo_receipt")
        cls.loc_production = cls.env["stock.location"]._dlm_virtual_location(
            "production")
        cls.finished = cls.env["product.product"].create({
            "name": "Bàn thép (K16)", "product_kind": "manufactured",
        })
        cls.finished.tracking = "none"
        # Phế liệu: `product_kind='material'` y hệt thép thật — cờ `dlm_is_scrap`
        # mới là thứ phân biệt (xem _DLM_LOCATION_RULES).
        cls.scrap = cls.env["product.product"].create({
            "name": "Phế liệu thép (K16)",
            "product_kind": "material",
            "dlm_is_scrap": True,
        })
        cls.scrap.tracking = "none"
        cls.material.tracking = "none"

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _stock_at(self, location, product, qty):
        self.env["stock.quant"]._update_available_quantity(
            product, location, qty)

    def _batch(self, outputs=(), materials=(), order=None, confirm=True):
        """Phiếu mẻ. KHÔNG khai vị trí — đó chính là bất biến đang test.

        `confirm=False` cho ca đang test LÁ CHẮN: `action_confirm` nổ UserError
        khi phiếu có lỗi, nên muốn soi dải đỏ thì phải dừng ở trạng thái nháp.
        """
        moves = [(0, 0, {
            "product_id": product.id,
            "product_uom_qty": qty,
            "product_uom": product.uom_id.id,
            "dlm_move_kind": "output",
        }) for product, qty in outputs]
        moves += [(0, 0, {
            "product_id": product.id,
            "product_uom_qty": qty,
            "product_uom": product.uom_id.id,
            "dlm_move_kind": kind,
        }) for product, qty, kind in materials]
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "dlm_sale_order_id": order.id if order else False,
            "move_ids": moves,
        })
        if confirm:
            picking.action_confirm()
            picking.action_assign()
        return picking

    def _hand_over_and_receive(self, picking, quantities=None):
        for move in picking.move_ids:
            move.quantity = (quantities or {}).get(
                move.product_id, move.product_uom_qty)
            move.picked = True
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()
        return picking

    def _issue_to_workshop(self, product, qty, order=None, extra=False):
        """Phiếu [3] cấp vật tư ra xưởng — hai chữ ký như K15."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
            "dlm_sale_order_id": order.id if order else False,
            "dlm_is_extra_issue": extra,
            "dlm_extra_reason": "damaged" if extra else False,
            "move_ids": [(0, 0, {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.loc_xuong.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = qty
            move.picked = True
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()
        return picking

    # ── 🔴 Phiếu CHƯA LƯU: dải phải thấy dòng vừa gõ ─────────────────────────
    def test_dai_thay_dong_vua_go_khi_phieu_chua_luu(self):
        """Dùng `Form` vì đây là ca CHỈ xảy ra qua giao thức onchange của client.

        Vấp thật khi test tay: gõ 2 dòng vào bảng "Xưởng nộp về", dải đỏ vẫn nói
        "Phiếu chưa có dòng nào" và nút Xác nhận biến mất ⇒ người dùng nhìn thấy
        dòng của mình trên màn mà không có đường nào đi tiếp.

        Nguyên nhân: `move_ids`, `dlm_fg_move_ids`, `dlm_material_move_ids` cùng
        một inverse nhưng là BA ô độc lập với client — gõ vào ô này thì ô kia
        rỗng cho tới lúc Lưu. Mọi test `create()` đều bỏ lọt vì `create()` ghi
        thẳng xuống DB, nơi cả ba ô trỏ cùng một tập.
        """
        picking_form = Form(
            self.env["stock.picking"].with_context(
                default_picking_type_id=self.fg_type.id),
            view="dl_inventory.view_dl_fg_receipt_form")

        # 🔴 Bẫy THỨ HAI, cùng gốc: `stock.picking.state` là compute stored
        # `depends('move_ids.state', ...)`. Form không dùng `move_ids` thì
        # `_compute_state` không bao giờ chạy ⇒ `state` = False, KHÔNG phải
        # 'draft'. Nút "Xác nhận phiếu" (điều kiện `state != 'draft'`) vì thế
        # biến mất dù phiếu hoàn toàn hợp lệ. Vá bằng `<field name="move_ids"
        # invisible="1"/>` trong view — assert ở đây canh đúng chỗ đó.
        self.assertEqual(
            picking_form.state, "draft",
            "Phiếu mới phải ở trạng thái Nháp, không phải False.")

        with picking_form.dlm_fg_move_ids.new() as line:
            line.product_id = self.finished
            line.product_uom_qty = 10.0

        self.assertEqual(picking_form.state, "draft")
        self.assertFalse(
            picking_form.dlm_blocked,
            "Phiếu đã có dòng — không được khoá nút Xác nhận.")
        self.assertNotIn(
            "chưa có dòng nào", picking_form.dlm_banner_message or "")

        # Lưu xong phải ra ĐÚNG số dòng: ba ô one2many cùng inverse là chỗ dễ
        # sinh dòng nhân đôi nhất, mà nhân đôi ở đây là nhân đôi tồn kho.
        picking = picking_form.save()
        self.assertEqual(len(picking.move_ids), 1)

    # ── Kịch bản trọn vòng ───────────────────────────────────────────────────
    def test_tron_mot_me_bon_con_so_cuoi_deu_dung(self):
        """Cấp 100 → bổ sung 10 → làm ra 10 bàn, dùng 110 thép, cân 43kg phế.

        Đây là kịch bản nghiệm thu của K16. Bốn con số cuối phải khớp thực tế:
        không thép ma ở Xưởng, không tồn âm, phế liệu có chỗ nằm.
        """
        self._stock_at(self.loc_kho, self.material, 118.0)
        self._issue_to_workshop(self.material, 100.0)
        self._issue_to_workshop(self.material, 10.0, extra=True)

        self.assertEqual(self._qty_at(self.loc_kho, self.material), 8.0)
        self.assertEqual(self._qty_at(self.loc_xuong, self.material), 110.0)

        batch = self._batch(
            outputs=((self.finished, 10.0), (self.scrap, 43.0)),
            materials=((self.material, 110.0, "consume"),))
        self._hand_over_and_receive(batch)

        self.assertEqual(batch.state, "done")
        self.assertEqual(self._qty_at(self.loc_kho, self.material), 8.0)
        self.assertEqual(
            self._qty_at(self.loc_xuong, self.material), 0.0,
            "🔴 Thép đã thành bàn thì phải rời sổ Xưởng — không để lại thép ma.")
        self.assertEqual(self._qty_at(self.loc_tp, self.finished), 10.0)
        self.assertEqual(self._qty_at(self.loc_xuong_pl, self.scrap), 43.0)

    def test_khong_co_ton_am_o_vi_tri_noi_bo(self):
        """Lá chắn tổng: một quant âm ở khu NỘI BỘ là dấu hiệu luồng đã sai.

        Chỉ soi `usage='internal'`. Vị trí ẢO Sản xuất âm là ĐÚNG và bắt buộc —
        nó là vế đối ứng của việc hàng được sinh ra: 10 cái bàn vào Kho thành
        phẩm thì Sản xuất phải nợ 10 cái. Bắt cả vị trí ảo là bắt sai chỗ, và
        sẽ đẩy người sửa đi bịt đúng thứ đang chạy đúng.
        """
        self._stock_at(self.loc_kho, self.material, 50.0)
        self._issue_to_workshop(self.material, 50.0)
        self._hand_over_and_receive(self._batch(
            outputs=((self.finished, 5.0),),
            materials=((self.material, 50.0, "consume"),)))

        am = self.env["stock.quant"].search([
            ("quantity", "<", 0), ("location_id.usage", "=", "internal")])
        self.assertFalse(
            am, "Tồn âm ở: %s" % [
                "%s @ %s" % (q.product_id.display_name,
                             q.location_id.display_name) for q in am])

    # ── Vị trí SUY RA, không ai chọn ─────────────────────────────────────────
    def test_vi_tri_suy_tu_vai_tro_dong_va_mat_hang(self):
        """Ba loại dòng, ba cặp vị trí — người dùng không có ô nào để chọn sai."""
        self._stock_at(self.loc_kho, self.material, 20.0)
        self._issue_to_workshop(self.material, 20.0)
        batch = self._batch(
            outputs=((self.finished, 1.0), (self.scrap, 2.0)),
            materials=((self.material, 5.0, "consume"),
                       (self.material, 3.0, "return")))

        by_role = {}
        for move in batch.move_ids:
            by_role.setdefault(
                (move.dlm_move_kind, move.product_id), move)

        thanh_pham = by_role[("output", self.finished)]
        self.assertEqual(thanh_pham.location_id, self.loc_production)
        self.assertEqual(thanh_pham.location_dest_id, self.loc_tp)

        phe = by_role[("output", self.scrap)]
        self.assertEqual(phe.location_id, self.loc_production)
        self.assertEqual(
            phe.location_dest_id, self.loc_xuong_pl,
            "Phế liệu nhận diện bằng cờ dlm_is_scrap, không bằng product_kind.")

        dung = by_role[("consume", self.material)]
        self.assertEqual(dung.location_id, self.loc_xuong)
        self.assertEqual(dung.location_dest_id, self.loc_production)

        tra = by_role[("return", self.material)]
        self.assertEqual(tra.location_id, self.loc_xuong)
        self.assertEqual(tra.location_dest_id, self.loc_kho)

    def test_tra_vat_tu_thua_ve_kho_nguyen_vat_lieu(self):
        self._stock_at(self.loc_kho, self.material, 30.0)
        self._issue_to_workshop(self.material, 30.0)
        self._hand_over_and_receive(self._batch(
            outputs=((self.finished, 2.0),),
            materials=((self.material, 25.0, "consume"),
                       (self.material, 5.0, "return"))))

        self.assertEqual(self._qty_at(self.loc_xuong, self.material), 0.0)
        self.assertEqual(self._qty_at(self.loc_kho, self.material), 5.0)

    # ── Lá chắn ──────────────────────────────────────────────────────────────
    def test_khai_vat_tu_vuot_ton_o_xuong_bi_chan(self):
        """🔴 Khác chính sách SM-03: ở đây "thiếu" không phải phiếu treo mà là
        TỒN ÂM — Odoo không chặn tồn âm nội bộ nên nó hỏng im lặng."""
        self._stock_at(self.loc_kho, self.material, 10.0)
        self._issue_to_workshop(self.material, 10.0)
        batch = self._batch(
            outputs=((self.finished, 1.0),),
            materials=((self.material, 40.0, "consume"),), confirm=False)

        self.assertTrue(batch.dlm_blocked)
        self.assertIn("đang ở Xưởng sản xuất", batch.dlm_banner_message)
        with self.assertRaises(UserError):
            batch.action_confirm()

    def test_hang_khong_vao_ton_phai_gan_don(self):
        """Hạng A không có dòng tồn nào để tra ngược ⇒ đơn là danh tính duy nhất."""
        categ = self.env["product.category"].create({"name": "Bàn (K16)"})
        generic = self.env["product.product"].create({
            "name": "Bàn thép dùng chung (K16)",
            "categ_id": categ.id,
            "product_kind": "manufactured",
        })
        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn (K16)",
            "product_category_id": categ.id,
            "generic_product_id": generic.id,
        })
        generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(generic.detailed_type, "consu", "Bối cảnh §3.5.")

        batch = self._batch(outputs=((generic, 3.0),), confirm=False)
        self.assertTrue(batch.dlm_blocked)
        self.assertIn("phải gắn Đơn bán hàng", batch.dlm_banner_message)
        with self.assertRaises(UserError):
            batch.action_confirm()

    def test_cap_bo_sung_phai_co_ly_do(self):
        """Ô tick một mình không nói được gì — lý do mới là dữ liệu."""
        self._stock_at(self.loc_kho, self.material, 10.0)
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
            "dlm_is_extra_issue": True,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": 5.0,
                "product_uom": self.material.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.loc_xuong.id,
            })],
        })
        self.assertTrue(picking.dlm_blocked)
        self.assertIn("phải chọn lý do", picking.dlm_banner_message)

    # ── Nhận thiếu: không sinh phiếu bù ──────────────────────────────────────
    def test_khai_100_nhan_98_thi_ton_tang_98_va_khong_phieu_bu(self):
        """Thủ kho là nút chặn cuối. Xưởng khai 100, đếm thực 98 ⇒ sổ ghi 98.

        Và KHÔNG sinh phiếu bù: 2 cái còn nằm ở xưởng, mẻ sau khai tiếp — chứ
        không phải một phiếu rỗng treo vĩnh viễn trong hàng đợi thủ kho.
        """
        batch = self._batch(outputs=((self.finished, 100.0),))
        self._hand_over_and_receive(batch, quantities={self.finished: 98.0})

        self.assertEqual(batch.state, "done")
        self.assertEqual(self._qty_at(self.loc_tp, self.finished), 98.0)
        self.assertEqual(
            self.env["stock.picking"].search_count(
                [("backorder_id", "=", batch.id)]), 0,
            "Loại NTP đặt create_backorder='never'.")

    # ── Hai chữ ký, hai người ────────────────────────────────────────────────
    def test_khong_ky_nhan_thi_hang_chua_vao_so(self):
        batch = self._batch(outputs=((self.finished, 4.0),))
        self.assertEqual(batch.dlm_receipt_flow, "from_workshop")
        self.assertEqual(batch.dlm_receipt_state, "ready")

        for move in batch.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        batch.action_dlm_handover()

        self.assertEqual(batch.dlm_receipt_state, "waiting")
        self.assertEqual(
            self._qty_at(self.loc_tp, self.finished), 0.0,
            "Chưa ai ký nhận thì hàng chưa vào sổ kho.")
        with self.assertRaises(UserError) as caught:
            batch.button_validate()
        self.assertIn("chữ ký nhận hàng", str(caught.exception))

    def test_ky_thuat_lap_va_xac_nhan_duoc_phieu_me(self):
        """🔴 Chạy DƯỚI QUYỀN THẬT, không sudo — đây là ca mà mọi test khác
        trong file này bỏ lọt vì chúng chạy bằng superuser.

        Lỗ đã vấp thật: `action_confirm` của Odoo đụng `stock.warehouse.orderpoint`
        (quy tắc tồn kho tối thiểu), mà bên Kỹ thuật không có ACL đọc model đó ⇒
        họ lưu được phiếu nhưng KHÔNG xác nhận nổi, và câu lỗi nói về một model
        chẳng liên quan gì tới việc họ đang làm.
        """
        tech = self.env["res.users"].create({
            "name": "KTV lập phiếu (K16)", "login": "ktv_lap_k16@test.dl",
            "groups_id": [(6, 0, [
                self.env.ref("dl_base.dl_group_tech").id,
                self.env.ref("base.group_user").id,
            ])],
        })
        picking = self.env["stock.picking"].with_user(tech).create({
            "picking_type_id": self.fg_type.id,
            "location_id": self.loc_production.id,
            "location_dest_id": self.loc_tp.id,
            "move_ids": [(0, 0, {
                "product_id": self.finished.id,
                "product_uom_qty": 6.0,
                "product_uom": self.finished.uom_id.id,
                "dlm_move_kind": "output",
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.action_dlm_handover()

        self.assertEqual(picking.dlm_receipt_state, "waiting")
        self.assertEqual(picking.dlm_handover_uid, tech)

    def test_ky_thuat_khong_ky_nhan_thay_thu_kho(self):
        """Bên NHẬN của phiếu [8] là Thủ kho. Xưởng ký cả hai đầu thì lần truy
        cứu sau không phân biệt nổi ai giao với ai nhận."""
        tech = self.env["res.users"].create({
            "name": "KTV (K16)", "login": "ktv_k16@test.dl",
            "groups_id": [(6, 0, [
                self.env.ref("dl_base.dl_group_tech").id,
                self.env.ref("base.group_user").id,
            ])],
        })
        batch = self._batch(outputs=((self.finished, 4.0),))
        for move in batch.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        batch.action_dlm_handover()

        with self.assertRaises(UserError) as caught:
            batch.with_user(tech).action_dlm_confirm_receipt()
        self.assertIn("bên NHẬN", str(caught.exception))
