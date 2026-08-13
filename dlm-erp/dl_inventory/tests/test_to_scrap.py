# -*- coding: utf-8 -*-
"""K11 + K12 — Bịt ba cửa khu quá cảnh, và mở lối ra cho hàng kẹt ở Chờ trả NCC.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §4.1.1, §4.2, §6.4.1, §11.14.

Hai mốc này BẮT BUỘC đi cùng nhau, và bộ test canh đúng lý do đó: K11 bịt đường
vòng qua khu cha `DL/NHAN` — mà đó đang là lối ra DUY NHẤT của hàng kẹt ở khu Chờ
trả NCC. Bịt trước mà không mở lối sau thì có một khoảng thời gian 8 cây thép gỉ
không ra được bằng đường nào: cấm kiểm kê tay (RS-07), cấm làm nguồn phiếu chuyển
kho (§4.1.1), và phiếu trả thì đã huỷ.

Cái sai đắt nếu K11 hỏng, xếp theo mức nặng:

1. phiếu GIAO HÀNG lấy nguồn "Chờ kiểm hàng" ⇒ giao thẳng hàng CHƯA KIỂM cho
   khách — nặng hơn hẳn hai cửa Chuyển kho/Kiểm kê cộng lại;
2. khu Phế liệu nhận cả thép nguyên cây ⇒ bán ve chai thép mới, và Lệnh sản xuất
   (B2) lại rút chính nó ra làm hàng;
3. chọn khu cha `DL/NHAN` làm nguồn ⇒ rút thẳng từ Chờ kiểm / Chờ trả.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestToScrap(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loc_nhan = cls.env.ref("dl_inventory.stock_location_nhan")
        cls.scrap = cls.env["product.product"].search(
            [("dlm_is_scrap", "=", True)], limit=1)
        if not cls.scrap:
            cls.scrap = cls.env["product.product"].create({
                "name": "Phế liệu thép (test K12)",
                "product_kind": "material",
                "dlm_is_scrap": True,
            })
        cls.scrap.tracking = "none"
        # Quy đổi kg để có số GỢI Ý: 1 cây thép ≈ 6 kg.
        cls.material.dlm_mass_per_unit = 6.0

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _picking(self, ptype, source, dest, product=None, qty=8.0):
        product = product or self.material
        return self.env["stock.picking"].create({
            "picking_type_id": ptype.id,
            "location_id": source.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": source.id,
                "location_dest_id": dest.id,
            })],
        })

    def _reject_flow(self, nhan=10.0, loai=8.0):
        """Nhận hàng → kiểm → loại `loai` cây ⇒ phiếu trả NHÁP + hàng ở Chờ trả."""
        receipt = self._receive(self._make_receipt(qty=nhan), qty=nhan)
        qc = self._qc_picking(receipt)
        # `picked=True` bắt buộc: thiếu nó thì Odoo coi dòng chưa làm gì và
        # button_validate không dời hàng ⇒ không có hàng nào tới khu Chờ trả.
        qc.move_ids[:1].write({
            "quantity": nhan - loai,
            "picked": True,
            "dlm_qty_rejected": loai,
            "dlm_reject_reason": "defect",
        })
        qc.action_dlm_validate_qc()
        ret = qc._dlm_vendor_returns()[:1]
        self.assertTrue(ret, "Bước kiểm không sinh phiếu trả NCC — test sau vô nghĩa.")
        return ret

    # ══ K11 — BA CỬA ════════════════════════════════════════════════════════
    def test_k11_khu_nhap_cha_cam_chon_tay(self):
        """Cửa 1: khu CHA `DL/NHAN` phải mang cờ, không chỉ hai khu con.

        K10 biến thiếu sót này thành lỗ THẬT: sau khi Kho vật tư dời xuống Xưởng,
        con của DL/NHAN chỉ còn hai khu quá cảnh ⇒ chọn khu cha là rút thẳng từ
        Chờ kiểm / Chờ trả, đi vòng qua thằng cha nhưng cùng một lỗ.
        """
        self.assertTrue(self.loc_nhan.dlm_no_inventory,
                        "Khu nhập hàng (cha) chưa gắn cờ cấm chọn tay.")
        cam = self.env["stock.location"].search([
            ("usage", "=", "internal"), ("dlm_no_inventory", "=", False),
            ("id", "child_of", self.warehouse.view_location_id.id),
        ])
        # K15: còn 4 — Kho nguyên vật liệu · Phế liệu chờ bán · Xưởng sản xuất ·
        # Kho thành phẩm. (Trước K15 là 5: ô "Bán thành phẩm" đã gộp vào Kho
        # nguyên vật liệu, và khu gom nhóm mới "Kho nhà máy sản xuất" bị cấm.)
        self.assertEqual(
            len(cam), 4,
            "Ô chọn vị trí phải còn đúng 4 mục (§4.1.1), đang có %s: %s"
            % (len(cam), ", ".join(cam.mapped("display_name"))))

    def test_k15_khu_gom_nhom_kho_san_xuat_cam_chon_tay(self):
        """Cửa thứ tư, sinh ra CÙNG LÚC với khu mới: `DL/KHOSX` là container.

        Cùng một lỗ với cửa 1 (`DL/NHAN`): chọn khu cha làm nguồn là rút được
        từ mọi ô con — ở đây là Kho nguyên vật liệu và Phế liệu chờ bán. Viết
        test ngay lúc tạo khu, không đợi nó thành sự cố như K10 → K11.
        """
        khosx = self.env.ref("dl_inventory.stock_location_khosx")
        self.assertTrue(khosx.dlm_no_inventory)
        picking = self._picking(
            self.warehouse.int_type_id, khosx, self.loc_xuong)
        self.assertTrue(
            any("quá cảnh" in p for p in picking._dlm_confirm_problems()),
            "Chọn khu Kho nhà máy sản xuất (cha) làm nguồn mà không bị chặn.")

    def test_k11_chuyen_kho_nguon_khu_cha_bi_chan(self):
        picking = self._picking(
            self.warehouse.int_type_id, self.loc_nhan, self.loc_xuong)
        self.assertTrue(
            any("quá cảnh" in p for p in picking._dlm_confirm_problems()),
            "Chọn khu cha làm nguồn phiếu chuyển kho mà không bị chặn.")

    def test_k11_giao_hang_nguon_cho_kiem_bi_chan(self):
        """Cửa 3 — nặng nhất: guard cũ chỉ áp cho `transfer` nên phiếu GIAO HÀNG
        lấy nguồn Chờ kiểm lọt sạch ⇒ giao hàng chưa kiểm cho khách."""
        picking = self._picking(
            self.warehouse.out_type_id, self.loc_qc,
            self.env.ref("stock.stock_location_customers"))
        self.assertEqual(picking.dlm_picking_kind, "delivery")
        self.assertTrue(
            any("quá cảnh" in p for p in picking._dlm_confirm_problems()),
            "Phiếu GIAO HÀNG vẫn lấy được nguồn Chờ kiểm — giao hàng chưa kiểm.")

    def test_k11_domain_form_giao_hang_co_loc_khu_qua_canh(self):
        """Canh trên chính `arch` của view: guard server đúng mà dropdown vẫn mời
        chọn thì người dùng chọn xong mới ăn lỗi."""
        arch = self.env["stock.picking"].get_views(
            [(self.env.ref("dl_inventory.view_dl_delivery_form").id, "form")]
        )["views"]["form"]["arch"]
        self.assertIn("dlm_no_inventory", arch,
                      'Ô "Lấy hàng từ" của form Giao hàng chưa lọc khu quá cảnh.')

    # ══ K11 — LUẬT KHU PHẾ LIỆU (canh CẢ HAI CHIỀU) ═════════════════════════
    def test_k11_thep_nguyen_cay_khong_vao_duoc_khu_phe_lieu(self):
        picking = self._picking(
            self.warehouse.int_type_id, self.loc_xuong, self.loc_xuong_pl)
        problems = " ".join(picking._dlm_confirm_problems())
        self.assertIn("phế liệu", problems,
                      "Thép nguyên cây vào được khu Phế liệu — sẽ bị bán ve chai.")

    def test_k11_phe_lieu_thi_vao_duoc(self):
        """Chiều ngược: luật chỉ trả 'cấm' cho mọi thứ thì test trên vẫn xanh mà
        khu Phế liệu thành khu chết."""
        picking = self._picking(
            self.warehouse.int_type_id, self.loc_xuong, self.loc_xuong_pl,
            product=self.scrap)
        problems = " ".join(picking._dlm_confirm_problems())
        self.assertNotIn("phế liệu chỉ", problems)
        self.assertNotIn("không được đưa vào", problems,
                         "Chính mặt hàng phế liệu lại không vào được khu của nó.")

    def test_k11_luat_khu_phe_lieu_khong_doc_product_kind(self):
        """SCRAP-STEEL mang `product_kind='material'` y hệt thép thật — luật phải
        đọc CỜ, không đọc loại hàng. Đây là luật ĐẦU TIÊN như thế."""
        self.assertEqual(self.scrap.product_kind, self.material.product_kind)
        self.assertTrue(self.scrap.dlm_is_scrap)
        self.assertFalse(self.material.dlm_is_scrap)

    # ══ K12 — LỐI RA CHO KHU CHỜ TRẢ ════════════════════════════════════════
    def test_k12_phieu_tra_huy_thi_hien_nut(self):
        ret = self._reject_flow()
        self.assertFalse(ret.dlm_has_stuck_stock,
                         "Phiếu trả chưa huỷ mà đã mời hoá phế liệu.")
        ret.action_cancel()
        self.assertTrue(ret.dlm_has_stuck_stock,
                        "Phiếu trả đã huỷ, hàng còn kẹt, mà nút không hiện.")

    def test_k12_hoa_phe_lieu_doi_mat_hang(self):
        """Bất biến của phiếu [9]: hàng gốc rời sổ VÀ phế liệu vào khu chờ bán —
        hai nửa, một chứng từ. Thiếu nửa giảm thì 8 cây thép gỉ vẫn nằm trong sổ
        như hàng dùng được."""
        ret = self._reject_flow(nhan=10.0, loai=8.0)
        ret.action_cancel()
        self.assertEqual(self._qty_at(self.loc_tra), 8.0)

        action = ret.action_dlm_to_scrap()
        picking = self.env["stock.picking"].browse(action["res_id"])
        self.assertEqual(picking.dlm_picking_kind, "to_scrap")
        self.assertEqual(len(picking.move_ids), 2, "Phiếu phải có ĐÚNG hai dòng.")

        vao = picking.move_ids.filtered("dlm_is_scrap_line")
        self.assertEqual(vao.product_id, self.scrap)
        self.assertEqual(vao.product_uom_qty, 48.0,
                         "Số kg gợi ý phải là 8 cây × 6 kg.")

        # Cân thật thắng số quy đổi (§7.3). Ghi vào `quantity` — số THỰC —
        # đúng ô người dùng gõ trên form.
        vao.quantity = 47.0
        picking.dlm_scrap_reason = "NCC giảm trừ công nợ, giữ hàng lại"
        picking.button_validate()

        self.assertEqual(self._qty_at(self.loc_tra), 0.0,
                         "Thép gốc vẫn nằm trong sổ sau khi hoá phế liệu.")
        self.assertEqual(self._qty_at(self.loc_xuong_pl, product=self.scrap),
                         47.0, "Phải vào đúng SỐ CÂN ĐƯỢC, không phải số quy đổi.")

    def test_k12_khong_hoa_phe_lieu_hai_lan(self):
        ret = self._reject_flow()
        ret.action_cancel()
        action = ret.action_dlm_to_scrap()
        picking = self.env["stock.picking"].browse(action["res_id"])
        picking.dlm_scrap_reason = "thép gỉ"
        picking.button_validate()

        ret.invalidate_recordset()
        self.assertFalse(
            ret.dlm_has_stuck_stock,
            "Hoá phế liệu xong mà nút vẫn hiện — bấm lần hai là tồn xuống âm.")
        with self.assertRaises(UserError):
            ret.action_dlm_to_scrap()

    def test_k12_thieu_ly_do_thi_chan(self):
        """Bút toán làm hàng biến mất khỏi sổ — không lý do thì sáu tháng sau
        không ai giải thích nổi vì sao 8 cây thép bốc hơi."""
        ret = self._reject_flow()
        ret.action_cancel()
        picking = self.env["stock.picking"].browse(
            ret.action_dlm_to_scrap()["res_id"])

        self.assertTrue(picking.dlm_blocked, "Thiếu lý do mà nút vẫn bấm được.")
        self.assertTrue(any("lý do" in p
                            for p in picking._dlm_to_scrap_problems()))
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_k12_thieu_so_kg_thi_chan(self):
        ret = self._reject_flow()
        ret.action_cancel()
        picking = self.env["stock.picking"].browse(
            ret.action_dlm_to_scrap()["res_id"])
        picking.dlm_scrap_reason = "thép gỉ"
        picking.move_ids.filtered("dlm_is_scrap_line").quantity = 0.0

        self.assertTrue(any("cân được" in p
                            for p in picking._dlm_to_scrap_problems()))
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_k12_giu_dung_lo_dang_bo(self):
        """Giữ chỗ theo ĐÚNG lô đang bỏ, không để chiến lược lấy hàng chọn hộ."""
        ret = self._reject_flow()
        ret.action_cancel()
        picking = self.env["stock.picking"].browse(
            ret.action_dlm_to_scrap()["res_id"])
        ra = picking.move_ids.filtered(lambda m: not m.dlm_is_scrap_line)
        lo_o_kho = self.env["stock.quant"].search([
            ("location_id", "=", self.loc_tra.id),
            ("product_id", "=", self.material.id),
        ]).lot_id
        self.assertEqual(ra.move_line_ids.lot_id, lo_o_kho,
                         "Dòng hàng bỏ không giữ đúng lô đang nằm ở khu Chờ trả.")

    def _stock_up(self, product, location, qty):
        """Đặt tồn rồi TRA LẠI quant: `action_apply_inventory` để bản ghi vừa
        tạo ở trạng thái không còn mang số — cầm nó đi tiếp là cầm số 0."""
        vals = {
            "product_id": product.id,
            "location_id": location.id,
            "inventory_quantity": qty,
        }
        if product.tracking != "none":
            # Vật tư theo lô: thiếu lô thì kiểm kê không áp được và quant không
            # sinh ra — im lặng, không lỗi nào nổ.
            vals["lot_id"] = self.env["stock.lot"].create({
                "name": "LO/TEST/K12/%s" % product.id,
                "product_id": product.id,
                "company_id": self.env.company.id,
            }).id
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            vals).action_apply_inventory()
        return self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
            ("quantity", ">", 0),
        ], limit=1)

    def test_k12_khong_hoa_phe_lieu_chinh_phe_lieu(self):
        """Phế liệu đã là phế liệu — hoá lần nữa là vòng lặp vô nghĩa và làm
        biến mất chính thứ đang chờ bán."""
        quant = self._stock_up(self.scrap, self.loc_xuong_pl, 20.0)
        with self.assertRaises(UserError):
            quant.action_dlm_to_scrap()

    def test_k12_khong_hoa_phe_lieu_thang_tu_khu_qua_canh(self):
        """Màn Tồn kho KHÔNG được là cửa sau vào khu Chờ trả: mất dấu vết lô
        hàng đi từ phiếu trả nào ra."""
        ret = self._reject_flow()
        ret.action_cancel()
        quant = self.env["stock.quant"].search([
            ("location_id", "=", self.loc_tra.id),
            ("product_id", "=", self.material.id),
        ], limit=1)
        with self.assertRaises(UserError):
            quant.action_dlm_to_scrap()

    def test_k12_vat_tu_hong_trong_kho_hoa_duoc(self):
        """Lối vào thứ hai (§6.5): vật tư gỉ trong Kho vật tư, không đòi NCC."""
        quant = self._stock_up(self.material, self.loc_kho, 5.0)
        picking = self.env["stock.picking"].browse(
            quant.action_dlm_to_scrap()["res_id"])
        picking.dlm_scrap_reason = "để lâu bị gỉ"
        picking.button_validate()

        self.assertEqual(self._qty_at(self.loc_kho), 0.0)
        self.assertEqual(
            self._qty_at(self.loc_xuong_pl, product=self.scrap), 30.0)
