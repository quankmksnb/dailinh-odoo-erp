# -*- coding: utf-8 -*-
"""K4: truy vết lô và hai màn hình đầu tiên của phân hệ Kho.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §5.5, §11.2, §11.9.

Chuỗi truy vết phải đi được tới tận NCC: khách báo hỏng, dẫn tới đơn, BOM,
lô vật tư, phiếu nhận, rồi tới NCC và ngày nhập. Bộ test này khoá chặng
cuối (lô, phiếu nhận, NCC).
"""

from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestLotTraceability(DlInventoryCase):

    def test_lo_ghi_nguon_goc_khi_nhan_hang(self):
        """§5.5: nhận hàng xong thì lô phải biết mình của ai, về ngày nào.

        Không có 3 field này, số lô chỉ là chuỗi ký tự vô nghĩa. Khách báo nứt
        mối hàn vẫn không tra được thép mua của ai.
        """
        picking = self._receive(self._make_receipt())
        lot = picking.move_line_ids.lot_id

        self.assertEqual(lot.dlm_supplier_id, self.vendor)
        self.assertEqual(lot.dlm_receipt_picking_id, picking)
        self.assertTrue(lot.dlm_receipt_date)

    def test_nguon_goc_khong_bi_ghi_de_boi_luan_chuyen_sau(self):
        """§5.5: nguồn gốc lô phải giữ thông tin của lần nhập đầu tiên.

        Nếu mỗi lần hàng đi qua một phiếu lại ghi đè, truy vết sẽ trỏ về phiếu
        chuyển kho nội bộ gần nhất thay vì về NCC, mất sạch giá trị truy vết.
        """
        picking = self._receive(self._make_receipt())
        lot = picking.move_line_ids.lot_id

        ncc_khac = self.env["res.partner"].create({"name": "NCC Khac (test)"})
        picking2 = self._make_receipt()
        picking2.partner_id = ncc_khac
        picking2.move_line_ids.lot_id = lot
        self._receive(picking2)

        self.assertEqual(
            lot.dlm_supplier_id, self.vendor,
            "Nguồn gốc lô phải giữ NCC của lần nhập ĐẦU TIÊN.")
        self.assertEqual(lot.dlm_receipt_picking_id, picking)

    def test_lo_mo_duoc_phieu_nhan_goc(self):
        """§11.9: nút trên form Lô hàng dẫn thẳng về phiếu nhận."""
        picking = self._receive(self._make_receipt())
        lot = picking.move_line_ids.lot_id

        action = lot.action_dlm_open_receipt()
        self.assertEqual(action["res_model"], "stock.picking")
        self.assertEqual(action["res_id"], picking.id)

    def test_man_ton_kho_doc_duoc_ncc_va_ngay_nhap(self):
        """§11.2: màn Tồn kho hiện NCC và ngày nhập mà không phải mở từng lô."""
        picking = self._receive(self._make_receipt())
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.material.id),
            ("location_id", "=", self.loc_qc.id),
        ])
        self.assertEqual(quant.dlm_supplier_id, self.vendor)
        self.assertEqual(
            quant.dlm_receipt_date, picking.move_line_ids.lot_id.dlm_receipt_date)

    def test_man_ton_kho_khong_lo_gia(self):
        """🔴 §8.3: Thủ kho mở màn Tồn kho không được thấy tiền.

        Kiểm ngay trên view (không chỉ ACL): cột giá lọt vào view là lộ ngay,
        dù ACL có đúng.
        """
        view = self.env.ref("dl_inventory.view_dl_stock_quant_tree")
        for token in ("standard_price", "value", "price", "cost"):
            self.assertNotIn(
                token, view.arch,
                "Màn Tồn kho không được có cột liên quan tới giá ('%s')." % token)

    def test_menu_kho_co_muc_con_de_hien_tren_rail(self):
        """§11.11: menu lá phải có action, nếu không rail sẽ nuốt mất mục.

        Bẫy đã ghi trong CLAUDE.md: rail lọc bằng _hasActionableMenu, nên menu
        lá rỗng action sẽ biến mất khỏi thanh điều hướng mà không lỗi nào nổ.
        """
        for xml_id in ("dl_inventory.menu_dl_stock_quant",
                       "dl_inventory.menu_dl_stock_lot"):
            menu = self.env.ref(xml_id)
            self.assertTrue(menu.action, "%s thiếu action ⇒ mất khỏi rail." % xml_id)
            self.assertEqual(menu.parent_id, self.env.ref("dl_base.menu_dl_inventory"))

    def test_thu_kho_vao_duoc_app_dlm(self):
        """🔴 Thủ kho phải thấy menu gốc "DLM-ERP", không chỉ menu "Kho".

        Bẫy đã ghi trong CLAUDE.md: Odoo bắt phải pass groups của cả tổ tiên.
        Cấp quyền cho menu con mà quên menu gốc thì user đăng nhập vào không
        thấy app đâu cả, và không có lỗi nào nổ, chỉ là màn hình trống.
        """
        warehouse_group = self.env.ref("dl_base.dl_group_warehouse")
        for xml_id in ("dl_base.menu_dl_root", "dl_base.menu_dl_inventory"):
            menu = self.env.ref(xml_id)
            self.assertIn(
                warehouse_group, menu.groups_id,
                "Thủ kho không thấy được %s ⇒ đăng nhập vào là màn trống."
                % xml_id)

    def test_thu_kho_mo_duoc_hai_man(self):
        """K4: vai trò Thủ kho thực sự đọc được dữ liệu của hai màn mới."""
        user = self.env["res.users"].create({
            "name": "thukho_k4", "login": "thukho_k4",
            "groups_id": [(6, 0, [self.env.ref("dl_base.dl_group_warehouse").id])],
        })
        self._receive(self._make_receipt())

        quants = self.env["stock.quant"].with_user(user).search(
            [("location_id", "=", self.loc_qc.id)])
        self.assertTrue(quants, "Thủ kho phải xem được tồn kho.")
        lots = self.env["stock.lot"].with_user(user).search(
            [("product_id", "=", self.material.id)])
        self.assertTrue(lots, "Thủ kho phải xem được lô hàng.")
