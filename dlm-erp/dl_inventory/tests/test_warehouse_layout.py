# -*- coding: utf-8 -*-
"""K2/K15 — Bố cục kho: MỘT kho, BỐN khu, nhận hàng 2 bước.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §3.1, §4, §5.

Vì sao cần bộ test này: cấu trúc kho là loại quyết định đổi sau rất đau, vì
mọi luân chuyển lịch sử trỏ vào vị trí cũ. Nếu ai đó lỡ tạo warehouse thứ hai
hoặc đổi vị trí đích của loại hoạt động, hàng sẽ nhập/xuất sai chỗ mà không có
lỗi nào báo: phiếu vẫn xác nhận được, chỉ có tồn nằm sai khu.
"""

from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestWarehouseLayout(DlInventoryCase):

    def test_chi_mot_kho(self):
        """§3.1: Đại Linh chỉ có một nhà xưởng, nên phải đúng một stock.warehouse.

        Kho thứ hai biến mọi luân chuyển nội bộ thành liên kho: thêm phiếu
        chuyển, thêm ô bắt buộc chọn kho, báo cáo tồn phải cộng thủ công.
        """
        self.assertEqual(
            self.env["stock.warehouse"].search_count([]), 1,
            "Phải đúng MỘT kho. Có kho thứ hai là sai thiết kế §3.1.")
        self.assertEqual(self.warehouse.code, "DL")

    def test_cay_vi_tri_bon_khu(self):
        """§4.1 — Bốn khu dưới kho DL, vị trí con nằm đúng khu của nó.

        🔴 K15 tách CHỖ CẤT khỏi CHỖ LÀM. Chuỗi hiển thị là thứ thủ kho đọc
        trong dropdown, nên nó phải khẳng định được đúng cái phân biệt đó — chứ
        không chỉ khẳng định cây có đủ số tầng.
        """
        expected = {
            self.loc_qc: "DL/Khu nhập hàng/Chờ kiểm hàng",
            self.loc_tra: "DL/Khu nhập hàng/Chờ trả nhà cung cấp",
            # Đường đi của ô này: DL/NHAN (K2) → DL/XUONG (K10) → DL/KHOSX (K15).
            self.loc_kho: "DL/Kho nhà máy sản xuất/Kho nguyên vật liệu",
            self.loc_xuong_pl: "DL/Kho nhà máy sản xuất/Phế liệu chờ bán",
            self.loc_khosx: "DL/Kho nhà máy sản xuất",
            self.loc_xuong: "DL/Xưởng sản xuất",
            self.loc_tp: "DL/Kho thành phẩm",
        }
        for location, complete_name in expected.items():
            self.assertEqual(location.complete_name, complete_name)

    def test_xuong_la_o_la_khong_con_vai_tro_kep(self):
        """🔴 K15 — Xưởng sản xuất KHÔNG được có con.

        Đây là bất biến sinh ra cả thay đổi này. Khi Xưởng còn là khu cha, chọn
        nó làm nguồn phiếu là với tay được vào Kho nguyên vật liệu qua `child_of`
        — lỗ mà K11 phải vá bằng luật. Cho nó một ô con trở lại là mở lại lỗ đó,
        và KHÔNG lỗi nào khác sẽ nổ.
        """
        con = self.env["stock.location"].with_context(
            active_test=False).search([("location_id", "=", self.loc_xuong.id)])
        self.assertFalse(
            con, "Xưởng sản xuất mọc lại ô con: %s" % con.mapped("name"))
        self.assertEqual(self.loc_xuong.location_id,
                         self.warehouse.view_location_id,
                         "Xưởng sản xuất phải nằm thẳng dưới kho DL.")

    def test_khu_gom_nhom_cam_chon_tay(self):
        """§4.1.1 + K15 — khu gom nhóm không được chọn tay trên phiếu.

        Khu nhập hàng và Kho nhà máy sản xuất đều là container: chọn chúng làm
        nguồn là rút được từ MỌI ô con. Xưởng sản xuất thì ngược lại — nó chứa
        hàng thật, phải chọn được.
        """
        self.assertTrue(self.loc_khosx.dlm_no_inventory,
                        "Kho nhà máy sản xuất là khu gom nhóm, phải cấm chọn tay.")
        self.assertTrue(
            self.env.ref("dl_inventory.stock_location_nhan").dlm_no_inventory)
        self.assertFalse(self.loc_xuong.dlm_no_inventory,
                         "Xưởng sản xuất chứa hàng thật — cấm chọn là chặn luôn "
                         "cả tuyến bàn giao lẫn tuyến gom phế liệu.")
        self.assertFalse(self.loc_kho.dlm_no_inventory)

    def test_khu_gom_nhom_khong_duoc_la_view(self):
        """🔴 §4.1: khu phải là 'internal', không được là 'view'.

        _compute_complete_name của Odoo bỏ tiền tố cha với vị trí 'view'. Khu để
        'view' sẽ hiện "Khu nhập hàng/Chờ kiểm hàng", mất luôn "DL/" và lệch hẳn
        với hai khu còn lại. Đã vấp thật khi thực thi K2.
        """
        nhan = self.env.ref("dl_inventory.stock_location_nhan")
        self.assertEqual(nhan.usage, "internal")
        self.assertTrue(nhan.complete_name.startswith("DL/"))

    def test_loai_hoat_dong_dung_nguon_dich(self):
        """§5.1 — Chín loại hoạt động, mỗi loại nối đúng hai đầu của nó.

        3 loại native (NH/GH/CK) + 6 loại tự tạo (KC/TR/BPL/HPL/XSX/NTP).
        """
        cases = [
            ("dl_inventory.picking_type_qc", self.loc_qc, self.loc_kho),
            ("dl_inventory.picking_type_vendor_return",
             self.loc_tra, self.loc_vendors),
            ("dl_inventory.picking_type_scrap_sale",
             self.env.ref("dl_inventory.stock_location_xuong_pl"),
             self.env.ref("stock.stock_location_customers")),
        ]
        for xml_id, source, destination in cases:
            picking_type = self.env.ref(xml_id)
            self.assertEqual(picking_type.default_location_src_id, source, xml_id)
            self.assertEqual(
                picking_type.default_location_dest_id, destination, xml_id)

        # Giao hàng khách đi từ Kho thành phẩm, không phải vị trí tồn mặc định.
        self.assertEqual(
            self.warehouse.out_type_id.default_location_src_id, self.loc_tp)

    def test_nhan_hang_hai_buoc_tu_sinh_phieu_kiem(self):
        """§3.2/§5.2: xác nhận phiếu nhận thì hàng vào khu Chờ kiểm và hệ thống
        phải tự sinh phiếu "Kiểm & cất hàng".

        Đây là mắt xích làm bước QC (K5) khả thi: không có phiếu tự sinh thì thủ
        kho phải nhớ tự tạo, và bước kiểm sẽ bị bỏ qua trong thực tế.
        """
        picking = self._receive(self._make_receipt())
        self.assertEqual(picking.state, "done")

        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.material.id),
            ("location_id", "=", self.loc_qc.id),
        ])
        self.assertEqual(quant.quantity, 100.0,
                         "Hàng phải nằm ở khu Chờ kiểm, chưa vào kho vật tư.")

        chained = picking.move_ids.move_dest_ids.picking_id
        self.assertTrue(chained, "Phải tự sinh phiếu kiểm & cất.")
        self.assertEqual(
            chained.picking_type_id,
            self.env.ref("dl_inventory.picking_type_qc"),
            "Bước 2 phải dùng loại 'Kiểm & cất hàng', không phải Chuyển kho "
            "nội bộ mặc định của Odoo (get_rules_dict).")
        self.assertEqual(chained.location_id, self.loc_qc)
        self.assertEqual(chained.location_dest_id, self.loc_kho)
