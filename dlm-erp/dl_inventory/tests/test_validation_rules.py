# -*- coding: utf-8 -*-
"""RS-06, RS-07, RS-11: các ca ngoại lệ, chặn đúng chỗ, báo lỗi bằng tiếng Việt.

Rà soát: docs/Ra_soat_phan_he_kho_2026-08-12.md

Nguyên tắc đã chốt (memory `rfq-sales-hard-constrains-ux-branch`): ràng buộc
sửa được ngay trên form phải báo inline bằng dải đỏ và ẩn nút, không bắn modal.
Guard phía server chỉ là lưới chặn cuối cho đường RPC.

Ca đắt nhất trong file này là RS-07: kiểm kê ở khu Chờ trả nhà cung cấp xoá đúng số hàng
mà phiếu trả (nháp) đang tham chiếu — mất bằng chứng khiếu nại NCC, không lỗi
nào nổ.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestQcEntryEase(DlInventoryCase):
    """RS-06: gõ Loại thì tự hạ Đạt."""

    def _qc(self, qty=198.0):
        receipt = self._receive(self._make_receipt(qty=qty), qty=qty)
        return self._qc_picking(receipt)

    def test_go_loai_tu_ha_dat(self):
        """Ca bẫy trong ảnh chụp: "Đạt tất cả" rồi mới phát hiện 2 cái lỗi."""
        qc = self._qc()
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.quantity = 198.0
        move.dlm_qty_rejected = 2.0
        move._onchange_dlm_qty_rejected()
        self.assertEqual(move.quantity, 196.0,
                         "Gõ Loại 2 trên 198 nhận ⇒ Đạt phải tự về 196.")
        self.assertFalse(move.dlm_qc_over, "QC-02 không được còn nổ đỏ.")

    def test_khong_ha_khi_chua_vuot(self):
        """Chỉ can thiệp khi vượt, không được sửa số người dùng đã gõ vô cớ."""
        qc = self._qc()
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.quantity = 100.0
        move.dlm_qty_rejected = 2.0
        move._onchange_dlm_qty_rejected()
        self.assertEqual(move.quantity, 100.0,
                         "100 + 2 chưa vượt 198 ⇒ giữ nguyên số đã gõ.")

    def test_loai_vuot_ca_so_nhan_thi_dat_ve_0_va_van_bi_chan(self):
        """Lưới an toàn QC-02 vẫn phải bắt ca gõ Loại lớn hơn số NCC giao."""
        qc = self._qc()
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.quantity = 198.0
        move.dlm_qty_rejected = 250.0
        move._onchange_dlm_qty_rejected()
        self.assertEqual(move.quantity, 0.0)
        self.assertTrue(move.dlm_qc_over,
                        "Loại 250 trên 198 nhận vẫn phải bị chặn.")

    def test_onchange_duoc_noi_vao_form_kiem_hang(self):
        """Method đúng chưa đủ, client phải thật sự gọi nó khi gõ.

        Hai điều kiện: onchange có trong registry của model, và ô Loại có mặt
        trên bảng dòng của form Kiểm hàng (client chỉ kích hoạt onchange cho
        field nó nhìn thấy).
        """
        self.assertIn(
            "dlm_qty_rejected", self.env["stock.move"]._onchange_methods,
            "Onchange chưa vào registry — gõ Loại sẽ không tự hạ Đạt.")
        arch = self.env.ref("dl_inventory.view_dl_qc_form").arch
        self.assertIn('name="dlm_qty_rejected"', arch,
                      "Ô Loại không có trên form Kiểm hàng.")


@tagged("post_install", "-at_install", "dl_inventory")
class TestTransitZoneInventory(DlInventoryCase):
    """RS-07: khu quá cảnh, tồn chỉ đổi qua phiếu."""

    def test_hai_khu_qua_canh_bi_danh_dau(self):
        """Khu Chờ kiểm và khu Chờ trả NCC là khu quá cảnh, kỳ vọng cả hai
        đều bị đánh dấu dlm_no_inventory=True (cấm kiểm kê tay)."""
        self.assertTrue(self.loc_qc.dlm_no_inventory,
                        "Khu Chờ kiểm phải bị cấm kiểm kê tay.")
        self.assertTrue(self.loc_tra.dlm_no_inventory,
                        "Khu Chờ trả nhà cung cấp phải bị cấm kiểm kê tay.")

    def test_kho_vat_tu_van_kiem_ke_duoc(self):
        """Cấm đúng 2 khu quá cảnh, không cấm lan sang kho thật."""
        self.assertFalse(self.loc_kho.dlm_no_inventory)
        self.assertFalse(self.loc_tp.dlm_no_inventory)

    def test_khong_ap_duoc_kiem_ke_o_khu_cho_tra(self):
        """🔴 Đếm về 0 ở đây là xoá mất hàng mà phiếu trả NCC đang trỏ tới."""
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.write({
            "quantity": 92.0, "picked": True,
            "dlm_qty_rejected": 8.0, "dlm_reject_reason": "defect"})
        qc.action_dlm_validate_qc()

        quant = self.env["stock.quant"].search([
            ("location_id", "=", self.loc_tra.id),
            ("product_id", "=", self.material.id),
        ], limit=1)
        self.assertTrue(quant, "Hàng loại phải đang nằm ở khu Chờ trả nhà cung cấp.")
        quant.inventory_quantity = 0.0
        with self.assertRaises(UserError):
            quant._apply_inventory()

    def test_man_kiem_ke_khong_liet_ke_khu_qua_canh(self):
        """Domain của action kiểm kê không được liệt kê khu Chờ trả NCC và
        khu Chờ kiểm, kỳ vọng cả hai khu đều không nằm trong locations trả
        về."""
        from odoo.tools.safe_eval import safe_eval
        domain = safe_eval(
            self.env.ref("dl_inventory.action_dl_stock_inventory").domain)
        locations = self.env["stock.quant"].search(domain).location_id
        self.assertNotIn(self.loc_tra, locations)
        self.assertNotIn(self.loc_qc, locations)


@tagged("post_install", "-at_install", "dl_inventory")
class TestConfirmValidation(DlInventoryCase):
    """RS-11: năm ca ngoại lệ từng rơi xuống thông báo tiếng Anh."""

    def _transfer(self, source, dest, qty=5.0):
        return self.env["stock.picking"].create({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("sequence_code", "=", "CK")], limit=1).id,
            "location_id": source.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": qty,
                "product_uom": self.material.uom_id.id,
                "location_id": source.id,
                "location_dest_id": dest.id,
            })],
        })

    def test_chuyen_kho_nguon_trung_dich_bi_chan(self):
        """Phiếu chuyển kho có vị trí nguồn trùng vị trí đích thì bị chặn
        (dlm_blocked=True, banner danger) và action_confirm() phải raise
        UserError."""
        picking = self._transfer(self.loc_kho, self.loc_kho)
        self.assertTrue(picking.dlm_blocked,
                        "Nguồn trùng đích ⇒ phải chặn xác nhận.")
        self.assertEqual(picking.dlm_banner_level, "danger")
        self.assertIn("cùng một chỗ", picking.dlm_banner_message)
        with self.assertRaises(UserError):
            picking.action_confirm()

    def test_chuyen_kho_hop_le_khong_bi_chan(self):
        """Phiếu chuyển kho có nguồn khác đích (hợp lệ) thì không bị chặn,
        action_confirm() chạy được và đổi state khỏi draft."""
        picking = self._transfer(self.loc_kho, self.loc_xuong)
        self.assertFalse(picking.dlm_blocked)
        picking.action_confirm()
        self.assertNotEqual(picking.state, "draft")

    def test_dong_so_luong_0_bi_chan_va_neu_ten(self):
        """Dòng chuyển kho có số lượng 0 thì bị chặn, banner phải nêu đích
        danh tên vật tư sai chứ không nói chung chung, và action_confirm()
        phải raise UserError."""
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=0.0)
        self.assertTrue(picking.dlm_blocked)
        self.assertIn(self.material.display_name, picking.dlm_banner_message,
                      "Dải phải nêu ĐÍCH DANH dòng sai, không nói chung chung.")
        with self.assertRaises(UserError):
            picking.action_confirm()

    def test_phieu_nhan_dong_so_luong_0_bi_chan(self):
        """Phiếu nhận hàng từ NCC cũng áp dụng cùng quy tắc: dòng số lượng
        0 phải bị chặn."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": self.vendor.id,
            "location_id": self.loc_vendors.id,
            "location_dest_id": self.loc_qc.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": 0.0,
                "product_uom": self.material.uom_id.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
            })],
        })
        self.assertTrue(picking.dlm_blocked)

    def test_kiem_hang_chua_nhap_gi_bi_chan_bang_tieng_viet(self):
        """Xoá sạch số rồi bấm xác nhận: trước đây rơi xuống lỗi native.

        Phải xoá tay: bước giữ chỗ đã điền sẵn số Đạt bằng số giữ được, nên ca
        "0 hết" chỉ xảy ra khi thủ kho tự xoá (hoặc chưa giữ chỗ được gì).
        """
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        qc.move_ids.write({"quantity": 0.0, "dlm_qty_rejected": 0.0})
        self.assertTrue(qc.dlm_blocked)
        self.assertIn("Chưa nhập kết quả kiểm", qc.dlm_banner_message)
        with self.assertRaises(UserError):
            qc.action_dlm_validate_qc()

    def test_chuyen_kho_thieu_ton_canh_bao_chu_khong_chan(self):
        """Thiếu tồn là cảnh báo, không chặn, cùng lệ với màn Bán phế liệu.

        Chặn cứng ở đây là chặn luôn ca hợp lệ "lập phiếu trước, hàng về sau".
        """
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=5.0)
        self.assertEqual(picking.dlm_banner_level, "warning")
        self.assertFalse(picking.dlm_blocked)
        picking.action_confirm()

    def test_dai_giao_hang_doc_theo_vi_tri_that(self):
        """Đổi "Lấy hàng từ" thì dải phải nói đúng khu đó, không viết cứng."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.loc_kho.id,
            "location_dest_id": self.env.ref(
                "stock.stock_location_customers").id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": 5.0,
                "product_uom": self.material.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": self.env.ref(
                    "stock.stock_location_customers").id,
            })],
        })
        picking.action_confirm()
        self.assertIn(self.loc_kho.display_name, picking.dlm_banner_message,
                      "Dải vẫn viết cứng 'Kho thành phẩm' — sai ngữ cảnh.")


@tagged("post_install", "-at_install", "dl_inventory")
class TestTransferShortage(DlInventoryCase):
    """Chuyển kho: khu nguồn có đủ hàng để chuyển số đó không?

    Lỗ hổng đang vá: domain SM-03 chỉ lọc mặt hàng có tồn (> 0) ở khu nguồn,
    không nói gì về số lượng. Chọn đúng mặt hàng rồi gõ số vượt tồn vẫn lọt
    trơn, phiếu treo ở trạng thái `confirmed` mà màn hình không giải thích vì sao.
    """

    def _stock(self, location, qty, product=None):
        """Đặt sẵn tồn ở một khu, kèm lô vì vật tư của dự án theo lô."""
        product = product or self.material
        lot = self.env["stock.lot"].create({
            "name": "LO-TEST-%s" % location.id,
            "product_id": product.id,
            "company_id": self.env.company.id,
        })
        self.env["stock.quant"]._update_available_quantity(
            product, location, qty, lot_id=lot)

    def _transfer(self, source, dest, qty=5.0, lines=1):
        return self.env["stock.picking"].create({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("sequence_code", "=", "CK")], limit=1).id,
            "location_id": source.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": self.material.name,
                "product_id": self.material.id,
                "product_uom_qty": qty,
                "product_uom": self.material.uom_id.id,
                "location_id": source.id,
                "location_dest_id": dest.id,
            }) for _i in range(lines)],
        })

    def test_go_vuot_ton_thi_canh_bao_kem_con_so(self):
        """Cảnh báo phải nêu đích danh mặt hàng và số còn thực tế.

        "Không đủ hàng" chung chung thì thủ kho vẫn phải tự đi tra tồn.
        """
        self._stock(self.loc_kho, 2.0)
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=5.0)

        self.assertEqual(picking.dlm_banner_level, "warning")
        self.assertIn(self.material.display_name, picking.dlm_banner_message)
        self.assertIn("chỉ còn 2", picking.dlm_banner_message)
        self.assertIn(self.loc_kho.display_name, picking.dlm_banner_message,
                      "Dải phải gọi tên khu nguồn thật, không viết cứng.")

    def test_du_ton_thi_khong_canh_bao(self):
        """Không được kêu oan: đủ hàng thì dải quay về hướng dẫn bình thường."""
        self._stock(self.loc_kho, 10.0)
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=5.0)

        self.assertEqual(picking.dlm_banner_level, "info")
        self.assertNotIn("không đủ hàng", picking.dlm_banner_message)

    def test_cong_gop_nhieu_dong_cung_mat_hang(self):
        """Tồn 5, hai dòng mỗi dòng 3: từng dòng đều "đủ" mà cả phiếu thì không.

        Xét lẻ từng dòng là bỏ lọt đúng ca này.
        """
        self._stock(self.loc_kho, 5.0)
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=3.0, lines=2)

        self.assertEqual(picking.dlm_banner_level, "warning")
        self.assertIn("cần chuyển 6", picking.dlm_banner_message)

    def test_doi_khu_nguon_thi_tinh_lai(self):
        """Đổi "Từ vị trí" phải tính lại ngay, nếu không dải đứng hình nói sai.

        Chính là ca `location_id` chưa có trong @api.depends của dải thông báo.
        """
        # Đích là Xưởng, không phải Kho thành phẩm: vật tư vào kho thành phẩm
        # nay bị chặn hẳn (xem TestFinishedGoodsWarehouseKinds) và dải đỏ đó sẽ
        # che mất thứ ca này muốn đo. Khu thay thế (đang có hàng) phải là khu
        # CHỌN-TAY-ĐƯỢC: Chờ kiểm/Chờ trả nay bị chặn hẳn khỏi phiếu chuyển (khu
        # quá cảnh, §4.1.1). Phế liệu chờ bán là ô cạnh Kho nguyên vật liệu dưới
        # khu Kho nhà máy sản xuất (K15 — trước đó nó là khu con của Xưởng).
        self._stock(self.loc_xuong_pl, 10.0)
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=5.0)
        self.assertEqual(picking.dlm_banner_level, "warning",
                         "Kho vật tư không có hàng ⇒ phải cảnh báo.")

        picking.location_id = self.loc_xuong_pl
        self.assertEqual(picking.dlm_banner_level, "info",
                         "Đổi sang khu đang có 10 mà dải vẫn kêu thiếu.")

    def test_dong_da_xong_khong_bi_tinh_la_thieu(self):
        """Phiếu đã chuyển xong: hàng rời khu nguồn là đúng, không phải thiếu."""
        self._stock(self.loc_kho, 5.0)
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=5.0)
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        # K15 — đích là Xưởng ⇒ phải qua hai chữ ký mới xong. Xem
        # test_workshop_handover.py cho chính luồng này.
        picking.action_dlm_handover()
        picking.action_dlm_confirm_receipt()

        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.dlm_banner_level, "success",
                         "Phiếu xong rồi mà còn kêu thiếu hàng.")


@tagged("post_install", "-at_install", "dl_inventory")
class TestFinishedGoodsWarehouseKinds(DlInventoryCase):
    """Kho thành phẩm chỉ chứa hàng để bán.

    Luật do người dùng chốt 2026-08-12: Đại Linh chỉ bán sản phẩm thương mại và
    sản phẩm gia công hoàn chỉnh. Kho thành phẩm là nơi phiếu Giao hàng lấy hàng
    (§5.3) nên vật tư lọt vào đây sớm muộn cũng bị giao cho khách.

    Luật neo vào vị trí đích, không neo vào nút lối tắt: hai lối tắt đi từ cùng
    một khu nguồn, và khi người dùng sửa tay ô vị trí sau khi bấm nút thì nút
    không biết được điều đó.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.trading = cls.env["product.product"].create({
            "name": "Bản lề inox nhập khẩu (test)",
            "product_kind": "trading",
        })
        # Hai loại Đại Linh TỰ LÀM — không bao giờ đi qua khu nhập hàng.
        cls.manufactured = cls.env["product.product"].create({
            "name": "Cửa cuốn hoàn chỉnh (test)",
            "product_kind": "manufactured",
        })
        cls.btp = cls.env["product.product"].create({
            "name": "Thanh thép đã cắt (test)",
            "product_kind": "material_processed",
        })

    def _stock(self, product, location, qty):
        self.env["stock.quant"]._update_available_quantity(
            product, location, qty)

    def _transfer(self, dest, product=None):
        product = product or self.material
        return self.env["stock.picking"].create({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("sequence_code", "=", "CK")], limit=1).id,
            "location_id": self.loc_kho.id,
            "location_dest_id": dest.id,
            "move_ids": [(0, 0, {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": 2.0,
                "product_uom": product.uom_id.id,
                "location_id": self.loc_kho.id,
                "location_dest_id": dest.id,
            })],
        })

    # ── Lớp 1: dropdown ──────────────────────────────────────────────────────
    #
    # Từ 2026-08-12 danh sách là LOẠI TRỪ, và chỉ theo luật cố định "khu nào
    # chứa hàng gì" (§4.2) ở CẢ HAI đầu phiếu — hết hàng ở nơi lấy KHÔNG còn là
    # lý do để ẩn mặt hàng (xem test_smart_domains).
    def test_dropdown_sang_kho_thanh_pham_bo_vat_tu(self):
        """Vật tư không được mời vào Kho thành phẩm; hàng gia công thì được.

        Nguồn là XƯỞNG chứ không phải Kho vật tư: từ 2026-08-12 Kho vật tư chỉ
        còn chứa vật tư nên tuyến Kho vật tư → Kho thành phẩm không còn loại
        chung nào (hàng TM đã vào TP thẳng ở bước kiểm). Xưởng ∩ Kho thành phẩm
        = {gia công} — đúng thứ Kho thành phẩm sinh ra để chứa.
        """
        picking = self._transfer(self.loc_tp)
        picking.location_id = self.loc_xuong

        blocked = picking.dlm_blocked_product_ids
        self.assertIn(self.material, blocked,
                      "Vật tư vẫn được mời vào Kho thành phẩm.")
        self.assertNotIn(self.manufactured, blocked,
                         "Hàng gia công hoàn chỉnh là thứ Kho thành phẩm chứa.")

    def test_tuyen_vat_tu_ra_xuong_chi_con_vat_tu_va_btp(self):
        """🔴 Ca người dùng báo: "vật tư ra xưởng mà" — danh sách chỉ được có
        thứ ĐƯA VÀO SẢN XUẤT, không kèm hàng thương mại, không kèm cả danh mục.

        Rơi ra từ giao hai luật, không phải từ cái nút vừa bấm:
        Kho nguyên vật liệu {vật tư, BTP} ∩ Xưởng {vật tư, BTP, gia công}
        = {vật tư, BTP}.

        K15 — BTP nay ĐƯỢC (trước đây bị cấm). Nó nằm chung ô với vật tư từ khi
        hai ô gộp lại, và người dùng chốt tuyến này chở "vật tư hoặc bán thành
        phẩm đến xưởng để đội công nhân làm".
        """
        picking = self._transfer(self.loc_xuong)
        blocked = picking.dlm_blocked_product_ids

        self.assertNotIn(self.material, blocked,
                         "Tuyến vật tư ra xưởng mà lại cấm vật tư.")
        self.assertNotIn(self.btp, blocked,
                         "BTP nằm cùng ô với vật tư và cũng đưa vào sản xuất — "
                         "cấm nó là chặn nửa tuyến bàn giao.")
        self.assertIn(self.trading, blocked,
                      "Hàng thương mại mua về để bán thẳng, không vào xưởng.")
        self.assertIn(self.manufactured, blocked,
                      "Sản phẩm gia công không nằm ở Kho nguyên vật liệu.")

    def test_hang_gia_cong_van_quay_lai_xuong_de_sua(self):
        """Siết xưởng không được chặn nhầm luồng SỬA HÀNG.

        Kho thành phẩm {thương mại, gia công} ∩ xưởng {vật tư, BTP, gia công}
        = {gia công} — đúng thứ cần mang đi sửa.
        """
        picking = self._transfer(self.loc_xuong)
        picking.location_id = self.loc_tp
        blocked = picking.dlm_blocked_product_ids
        self.assertNotIn(self.manufactured, blocked,
                         "Hàng gia công phải quay lại xưởng sửa được.")
        self.assertIn(self.trading, blocked)

    def test_dua_hang_thuong_mai_vao_xuong_bi_chan_dung_ly_do(self):
        """Câu chặn phải nói đúng khu — không được bê nguyên câu của Kho thành
        phẩm ("thứ lọt vào đây sớm muộn cũng bị giao cho khách") sang xưởng."""
        picking = self._transfer(self.loc_xuong, product=self.trading)
        self.assertTrue(picking.dlm_blocked)
        message = picking.dlm_banner_message
        self.assertIn(self.loc_xuong.display_name, message)
        self.assertIn("đưa vào sản xuất", message,
                      "Chặn ở xưởng mà giải thích bằng lý do của kho khác.")
        self.assertNotIn("giao cho khách", message)

    def test_doi_dich_thi_loc_lai(self):
        """Sửa tay ô "Đến vị trí" sau khi bấm lối tắt: danh sách phải theo kịp."""
        self._stock(self.material, self.loc_kho, 197.0)
        picking = self._transfer(self.loc_xuong)
        self.assertNotIn(self.material, picking.dlm_blocked_product_ids)

        picking.location_dest_id = self.loc_tp
        self.assertIn(self.material, picking.dlm_blocked_product_ids,
                      "Đổi đích sang Kho thành phẩm mà danh sách đứng hình.")

    def test_khu_con_cua_kho_thanh_pham_cung_bi_rang(self):
        """Luật theo cây vị trí, không phải đúng một bản ghi.

        Hôm nay DL/TP chưa có khu con; ngày ai đó chia "DL/TP/Khu A" mà luật chỉ
        khớp đúng DL/TP thì vật tư lại vào được, không lỗi nào nổ.
        """
        khu_con = self.env["stock.location"].create({
            "name": "Khu A (test)",
            "usage": "internal",
            "location_id": self.loc_tp.id,
        })
        self._stock(self.material, self.loc_kho, 197.0)
        picking = self._transfer(khu_con)

        self.assertIn(self.material, picking.dlm_blocked_product_ids)
        self.assertTrue(picking.dlm_blocked)

    # ── Lớp 2: chặn thật khi xác nhận ────────────────────────────────────────
    def test_vat_tu_bi_day_sang_kho_thanh_pham_van_bi_chan(self):
        """🔴 Lá chắn CHẶN không dựa vào dropdown.

        Dropdown chỉ lọc dòng THÊM MỚI. Thêm dòng vật tư theo tuyến hợp lệ (ra
        xưởng) rồi sửa TAY ô "Đến vị trí" thành Kho thành phẩm: đích áp cho cả
        dòng đã có, vật tư âm thầm sai chỗ mà không ô nào đổi màu — guard xác
        nhận phải bắt.
        """
        self._stock(self.material, self.loc_kho, 197.0)
        picking = self._transfer(self.loc_xuong)
        self.assertFalse(picking.dlm_blocked)

        picking.location_dest_id = self.loc_tp

        self.assertTrue(picking.dlm_blocked, "Vật tư sang Kho thành phẩm mà "
                                             "không ai chặn.")
        self.assertEqual(picking.dlm_banner_level, "danger")
        self.assertIn(self.material.display_name, picking.dlm_banner_message,
                      "Dải phải gọi tên mặt hàng sai, không nói chung chung.")
        with self.assertRaises(UserError):
            picking.action_confirm()

    def test_sp_thuong_mai_sang_kho_thanh_pham_van_chay(self):
        """Kho thành phẩm NHẬN được hàng thương mại — guard đích không chặn oan.

        Luồng thường ngày, hàng TM vào TP thẳng ở bước kiểm (không qua phiếu
        này). Nhưng tuyến chuyển tay Kho vật tư → TP vẫn phải thông cho hàng TM:
        đó là đường dọn tồn TM cũ còn kẹt ở Kho vật tư sau khi rút gọn luồng
        (migration 17.0.3.0.0 chỉ LOG, thủ kho tự chuyển). Guard xác nhận neo
        vào loại hàng ở ĐÍCH, mà TP chứa được hàng thương mại nên không chặn.
        """
        self._stock(self.trading, self.loc_kho, 10.0)
        picking = self._transfer(self.loc_tp, product=self.trading)

        self.assertFalse(picking.dlm_blocked)
        picking.action_confirm()
        self.assertNotEqual(picking.state, "draft")

    def test_dai_nhap_noi_ro_vi_sao_danh_sach_ngan_di(self):
        """Dropdown thiếu món mà không giải thích thì thành bí ẩn.

        Nơi lấy (Kho nguyên vật liệu: vật tư + BTP) giao nơi nhận (Xưởng sản
        xuất: vật tư + BTP + gia công) ⇒ còn ĐÚNG vật tư + BTP. Dải phải nói ra
        kết quả GIAO đó, không phải luật của riêng một đầu — ghép hai luật lại
        sẽ lòi ra "Gia công", thứ tuyến này không chuyển được.
        """
        self._stock(self.material, self.loc_kho, 10.0)
        picking = self._transfer(self.loc_xuong)
        self.assertEqual(picking.dlm_banner_level, "info")
        self.assertIn("chỉ chuyển được", picking.dlm_banner_message)
        self.assertIn("Vật tư", picking.dlm_banner_message)
        self.assertIn("Bán thành phẩm", picking.dlm_banner_message,
                      "BTP nằm cùng ô với vật tư từ K15, phải có trong danh sách.")
        self.assertNotIn("Gia công", picking.dlm_banner_message,
                         "Liệt kê cả loại mà nơi LẤY không chứa được.")


@tagged("post_install", "-at_install", "dl_inventory")
class TestTransferFormWording(DlInventoryCase):
    """Màn Chuyển kho phải đọc được mà không cần giải nghĩa."""

    def _arch(self):
        return self.env.ref("dl_inventory.view_dl_transfer_form").arch

    def test_nut_loi_tat_khong_viet_tat(self):
        """Nhãn nút lối tắt phải nói đủ chữ — thủ kho mới vào không đoán được các
        viết tắt kiểu TM/TP là gì."""
        arch = self._arch()
        self.assertIn("Vật tư ra xưởng", arch)
        self.assertIn("Gom phế liệu", arch)
        self.assertNotIn("Hàng TM sang kho TP", arch)

    def test_cot_thuc_chuyen_an_khi_con_nhap(self):
        """Lúc nháp "Thực chuyển" luôn 0 (chưa giữ chỗ), hiện ra chỉ gây hiểu
        nhầm là phải tự điền."""
        self.assertIn(
            """column_invisible="parent.state == 'draft'\"""", self._arch(),
            "Cột Thực chuyển vẫn hiện lúc nháp.")

    def test_nhan_cot_nhu_cau_dong_bo_voi_man_giao_hang(self):
        """"Số lượng" quá mơ hồ cạnh "Thực chuyển". Màn Giao hàng đã dùng cặp
        "Cần giao"/"Thực giao", chuyển kho phải cùng một lối nói."""
        self.assertIn('string="Cần chuyển"', self._arch())
