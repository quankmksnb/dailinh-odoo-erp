# -*- coding: utf-8 -*-
"""K6 — Đơn bán hàng ↔ phiếu giao hàng.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §9.1, §11.6, §12.1 (tiêu chí verify K6).

Ba bất biến đắt nhất nếu sai:

  1. Đơn CHƯA chốt không được sinh phiếu giao — phiếu giao giữ chỗ hàng cho một
     cam kết chưa tồn tại, hàng "biến mất" khỏi tồn khả dụng của đơn thật.
  2. SP dùng chung (Hạng A, ``consu``) PHẢI lên phiếu giao — 🔴 K13 đảo lại bất
     biến của K6 (xem `test_sp_dung_chung_van_len_phieu_giao`).
  3. Đơn đã có phiếu giao KHÔNG đưa về nháp được — sửa lại đơn đã giao là làm
     lệch chứng từ kho với chứng từ bán.
"""

from odoo.exceptions import UserError
from odoo.tests.common import Form, tagged

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

    def _generic_product(self, suffix="K6"):
        """SP dùng chung Hạng A — `detailed_type` thành `consu` vì có
        `dl.bom.template` trỏ tới (§3.5)."""
        categ = self.env["product.category"].create(
            {"name": "Bàn thép (%s)" % suffix})
        generic = self.env["product.product"].create({
            "name": "Bàn thép khung hộp (%s)" % suffix,
            "categ_id": categ.id,
            "product_kind": "manufactured",
        })
        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép (%s)" % suffix,
            "product_category_id": categ.id,
            "generic_product_id": generic.id,
        })
        generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(generic.detailed_type, "consu", "Bối cảnh §3.5.")
        return generic

    def test_sp_dung_chung_van_len_phieu_giao(self):
        """🔴 K13 ĐẢO bất biến số 2 của K6 (§9.1).

        K6 loại dòng `consu` ra với lý do "không có tồn nên sẽ treo vĩnh viễn".
        Lý do đó SAI: `_should_bypass_reservation()` trả True cho SP không
        storable ⇒ dòng nhảy thẳng sang `assigned`. Test này canh cả hai vế —
        dòng LÊN được phiếu, VÀ phiếu không treo ở trạng thái chờ hàng.

        Cái giá của bản cũ: đơn Hạng A (loại phổ biến nhất) không có chứng từ
        giao nào để khách ký, và tình trạng giao đứng yên kể cả khi hàng đã lên xe.
        """
        generic = self._generic_product()
        order = self._make_order(product=generic, qty=3.0)
        self.assertTrue(
            order.dlm_has_deliverable,
            "Đơn Hạng A phải có hàng để giao — đó là nghiệp vụ lõi.")

        order.action_dlm_create_delivery()
        picking = self._delivery_of(order)
        self.assertEqual(picking.move_ids.product_id, generic)
        self.assertEqual(picking.move_ids.product_uom_qty, 3.0)
        self.assertEqual(
            picking.state, "assigned",
            "Dòng consu bỏ qua giữ chỗ ⇒ phiếu sẵn sàng ngay, không treo.")

        picking.move_ids.quantity = 3.0
        picking.move_ids.picked = True
        picking.button_validate()
        order.invalidate_recordset(["dlm_delivery_state"])
        self.assertEqual(order.dlm_delivery_state, "done")

    def test_don_toan_dich_vu_khong_tao_duoc_phieu_giao(self):
        """Vế còn lại của K13: mở cho `consu` KHÔNG có nghĩa là mở cho tất cả.

        Dịch vụ không có gì để giao và không có gì để khách ký nhận. Bỏ luôn cả
        điều kiện này là đẻ ra phiếu giao rỗng nghĩa cho mọi đơn có dòng công
        lắp đặt.
        """
        # detailed_type khai ngay trong create: dl_product chỉ ép `product` khi
        # vals CHƯA nói gì (`_STORABLE_KINDS`), khai rồi thì nó tôn trọng.
        service = self.env["product.product"].create({
            "name": "Công lắp đặt tại chỗ (test)",
            "product_kind": "trading",
            "detailed_type": "service",
        })

        order = self._make_order(product=service, qty=1.0)
        self.assertFalse(order.dlm_has_deliverable)
        with self.assertRaises(UserError) as caught:
            order.action_dlm_create_delivery()
        self.assertIn("dịch vụ", str(caught.exception))

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

    # ── SM-14 — Cửa tạo phiếu giao thủ công (nút New ở màn Kho) ──────────────
    def _delivery_form(self):
        """Form Giao hàng của Đại Linh cho một phiếu MỚI.

        picking_type qua context chứ không gán tay: ô đó cố ý `invisible` trên
        form (thủ kho không chọn loại phiếu ở màn này), đúng như khi bấm New.
        """
        return Form(
            self.env["stock.picking"].with_context(
                default_picking_type_id=self.warehouse.out_type_id.id),
            view="dl_inventory.view_dl_delivery_form")

    def test_chon_don_tu_dien_hang_con_phai_giao(self):
        """Chọn khách → chọn đơn ⇒ bảng hàng tự có đúng phần còn phải giao."""
        order = self._make_order(qty=10.0)

        picking_form = self._delivery_form()
        picking_form.partner_id = self.customer
        picking_form.dlm_sale_order_id = order
        picking = picking_form.save()

        self.assertEqual(len(picking.move_ids), 1)
        self.assertEqual(picking.move_ids.product_id, self.goods)
        self.assertEqual(picking.move_ids.product_uom_qty, 10.0)
        self.assertEqual(
            picking.move_ids.location_id, self.loc_tp,
            "Dòng phải lấy vị trí nguồn của phiếu, không để trống.")

    def test_khong_dien_lai_phan_da_nam_tren_phieu_khac(self):
        """🔴 Bất biến đắt nhất của cửa thứ hai.

        Đơn 10 cái đã có một phiếu giao 10 cái đang chờ. Nếu autofill đọc thẳng
        `line_ids` của đơn thì phiếu thứ hai lại ra 10 cái nữa — kho giao gấp
        đôi và không chứng từ nào cảnh báo. Phải đọc `_dlm_remaining_qty()`,
        đúng phép tính mà nút [Tạo phiếu giao] trên đơn đang dùng.
        """
        order = self._make_order(qty=10.0)
        order.action_dlm_create_delivery()

        picking_form = self._delivery_form()
        picking_form.partner_id = self.customer
        picking_form.dlm_sale_order_id = order

        self.assertEqual(
            len(picking_form.move_ids), 0,
            "Đơn đã lên phiếu đủ ⇒ không được điền thêm dòng nào.")

    def test_doi_khach_thi_bo_don_va_dong_cua_khach_cu(self):
        """Đổi khách ⇒ đơn + dòng của khách cũ phải rời khỏi phiếu.

        Giữ lại là phiếu ghi "giao cho khách B theo đơn của khách A", và tình
        trạng giao của đơn A nói sai về một chuyến hàng họ không hề nhận.
        """
        order = self._make_order(qty=10.0)
        other = self.env["res.partner"].create({
            "name": "Khách hàng khác (test)",
            "partner_role": "customer",
        })

        picking_form = self._delivery_form()
        picking_form.partner_id = self.customer
        picking_form.dlm_sale_order_id = order
        self.assertEqual(len(picking_form.move_ids), 1, "Bối cảnh: đã có dòng.")

        picking_form.partner_id = other
        self.assertFalse(picking_form.dlm_sale_order_id)
        self.assertEqual(len(picking_form.move_ids), 0)

    def test_doi_don_thi_bang_hang_lay_theo_don_moi(self):
        """Một khách có nhiều đơn: đổi đơn ⇒ bảng hàng phải theo đơn ĐANG chọn.

        Bản đầu chốt "chỉ điền khi bảng trống" để giữ dòng người dùng gõ tay —
        nhưng bảng dòng khoá tới khi có đơn, nên không có dòng nào gõ được từ
        đầu. Thứ duy nhất chốt đó giữ lại là dòng của ĐƠN TRƯỚC: phiếu ghi đơn B
        mà bảng hàng vẫn là của đơn A.
        """
        order_a = self._make_order(qty=10.0)
        order_b = self._make_order(qty=4.0)

        picking_form = self._delivery_form()
        picking_form.partner_id = self.customer
        picking_form.dlm_sale_order_id = order_a
        self.assertEqual(len(picking_form.move_ids), 1, "Bối cảnh: đơn A đã điền.")

        picking_form.dlm_sale_order_id = order_b
        picking = picking_form.save()

        self.assertEqual(picking.dlm_sale_order_id, order_b)
        self.assertEqual(len(picking.move_ids), 1)
        self.assertEqual(
            picking.move_ids.product_uom_qty, 4.0,
            "Số lượng phải là của đơn B, không còn sót số của đơn A.")

    def test_quay_lai_don_cu_tren_phieu_nhap_da_luu(self):
        """🔴 Phiếu không được tự trừ mình.

        Phiếu nháp ĐÃ LƯU vẫn nằm trong `dlm_picking_ids` của đơn. Đổi sang đơn
        khác rồi đổi ngược về đơn cũ: nếu phép trừ "đang nằm trên phiếu khác"
        đếm cả chính nó thì remaining = 0 ⇒ bảng trống + cảnh báo "đơn không còn
        hàng", mất dòng mà không có gì báo là đã mất.
        """
        order_a = self._make_order(qty=10.0)
        order_b = self._make_order(qty=4.0)

        picking_form = self._delivery_form()
        picking_form.partner_id = self.customer
        picking_form.dlm_sale_order_id = order_a
        picking = picking_form.save()
        self.assertEqual(picking.state, "draft", "Bối cảnh: phiếu nháp đã lưu.")

        reopened = Form(picking, view="dl_inventory.view_dl_delivery_form")
        reopened.dlm_sale_order_id = order_b
        reopened.dlm_sale_order_id = order_a
        picking = reopened.save()

        self.assertEqual(len(picking.move_ids), 1)
        self.assertEqual(picking.move_ids.product_uom_qty, 10.0)

    def test_phieu_cap_vat_tu_khong_bi_dien_hang_cua_don(self):
        """Vế chặn của SM-14: `dlm_sale_order_id` còn nằm trên phiếu [3] chuyển
        kho ("cấp cho đơn hàng"). Điền thành phẩm của đơn vào phiếu cấp vật tư
        là đưa hàng đi sai tuyến ngay từ dòng đầu tiên."""
        order = self._make_order(qty=10.0)
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.int_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.loc_xuong.id,
        })
        picking.dlm_sale_order_id = order
        picking._onchange_dlm_sale_order_fills_moves()

        self.assertFalse(
            picking.move_ids,
            "Onchange chỉ được chạy cho phiếu Giao hàng.")

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
        # 🔴 K16 — preset "Gom phế liệu" ĐÃ GỠ (phế liệu nay khai trên phiếu mẻ,
        # xem test_workshop_batch). Preset còn lại vẫn phải kéo dòng đi theo:
        # dòng nhập trước khi bấm nút mà đứng yên thì phiếu nói một đằng, hàng
        # chạy một nẻo — đó mới là bất biến test này canh.
        picking.action_dlm_preset_to_workshop()

        self.assertEqual(picking.location_id, self.loc_kho)
        self.assertEqual(picking.location_dest_id, self.loc_xuong)
        self.assertEqual(picking.move_ids.location_id, self.loc_kho)
        self.assertEqual(picking.move_ids.location_dest_id, self.loc_xuong)
