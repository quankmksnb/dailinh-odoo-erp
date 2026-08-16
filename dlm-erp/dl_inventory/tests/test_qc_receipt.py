# -*- coding: utf-8 -*-
"""K5: kiểm hàng NCC, hàng đạt vào kho, hàng loại sang khu chờ trả.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §6, §11.3, §11.4.

Bộ test này quan trọng vì bước kiểm là chỗ duy nhất trong hệ thống phân biệt
được "NCC giao thiếu" với "NCC giao hàng kém". Trộn hai thứ đó lại thì cuối năm
không ai trả lời được NCC nào hay giao thiếu, NCC nào hay giao hàng hỏng, trong
khi đó chính là căn cứ để đàm phán lại giá hoặc bỏ nhà cung cấp.

Lỗi âm thầm đáng sợ nhất ở đây: hàng loại không đi đâu cả. Phiếu vẫn xác nhận,
tồn kho vẫn có số, nhưng 8 cây thép gỉ nằm lẫn trong kho vật tư và có thể bị
cắt vào sản phẩm của khách.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestQcReceipt(DlInventoryCase):

    def _qc_ready(self, receipt_qty=100.0):
        """Nhận hàng xong, trả về phiếu kiểm đang chờ."""
        receipt = self._receive(self._make_receipt(qty=receipt_qty),
                                qty=receipt_qty)
        return receipt, self._qc_picking(receipt)

    def _qc_move(self, qc):
        """Dòng của vật tư test. Lọc theo mặt hàng cho chắc: RS-01 đã chặn việc
        gộp phiếu kiểm nhiều NCC, nhưng lọc theo SP vẫn là cách bền nếu DB test
        chia sẻ còn phiếu kiểm cũ (sinh trước fix, group_id NULL)."""
        return qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]

    def _make_receipt_from(self, vendor, product, qty):
        """Phiếu nhận từ một NCC cụ thể, đã nhận đủ và xác nhận. Dùng cho các ca
        cần nhiều NCC cùng chờ kiểm (RS-01)."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.in_type_id.id,
            "partner_id": vendor.id,
            "location_id": self.loc_vendors.id,
            "location_dest_id": self.loc_qc.id,
            "move_ids": [(0, 0, {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
                "location_id": self.loc_vendors.id,
                "location_dest_id": self.loc_qc.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return self._receive(picking, qty=qty)

    def _fill_qc(self, qc, passed, rejected, reason="defect", note=False):
        move = self._qc_move(qc)
        move.write({
            "quantity": passed,
            "picked": True,
            "dlm_qty_rejected": rejected,
            "dlm_reject_reason": reason if rejected else False,
            "dlm_reject_note": note,
        })
        return move

    # Luồng chính
    def test_dat_92_loai_8_hang_di_dung_hai_noi(self):
        """§6.4: kiểm 92 đạt, 8 loại thì kho phải nhận đủ 92, khu chờ trả NCC có 8, khu kiểm sạch.

        Nếu fail: hàng loại bị lẫn vào kho vật tư và có thể bị cắt vào sản phẩm giao khách,
        đây là lỗi tốn kém nhất của phân hệ này.
        """
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)

        qc.action_dlm_validate_qc()

        self.assertEqual(qc.state, "done")
        self.assertEqual(self._qty_at(self.loc_kho), 92.0)
        self.assertEqual(self._qty_at(self.loc_tra), 8.0)
        self.assertEqual(self._qty_at(self.loc_qc), 0.0,
                         "Khu Chờ kiểm phải sạch: không được để hàng lửng lơ.")

    def test_hang_thuong_mai_dat_vao_thang_kho_thanh_pham(self):
        """§5.3 — Đạt + hàng thương mại đi THẲNG vào Kho thành phẩm.

        Hàng thương mại mua về là để bán, kiểm đạt xong là sẵn sàng giao. Nếu
        đỏ: nó rơi vào Kho vật tư (khu chỉ chứa vật tư) và phải làm thêm một
        phiếu chuyển kho tay mà người ta hay quên — đúng bước thừa mà rút gọn
        luồng 2026-08-12 đã bỏ.
        """
        trading = self.env["product.product"].create({
            "name": "Bản lề inox nhập (test)", "product_kind": "trading"})
        receipt = self._receive(
            self._make_receipt(product=trading, qty=20.0), qty=20.0)
        qc = self._qc_picking(receipt)
        qc.move_ids.filtered(lambda m: m.product_id == trading).write({
            "quantity": 20.0, "picked": True})

        qc.action_dlm_validate_qc()

        self.assertEqual(qc.state, "done")
        self.assertEqual(self._qty_at(self.loc_tp, product=trading), 20.0,
                         "Hàng thương mại đạt phải vào THẲNG Kho thành phẩm.")
        self.assertEqual(self._qty_at(self.loc_kho, product=trading), 0.0,
                         "Không được dừng ở Kho vật tư — khu đó chỉ chứa vật tư.")

    def test_hang_thuong_mai_dat_va_loai_tach_ba_nga(self):
        """Ngả 3 và ngả 2 cùng một phiếu: TM Đạt → TP, TM Loại → Chờ trả nhà cung cấp."""
        trading = self.env["product.product"].create({
            "name": "Ổ khoá nhập (test)", "product_kind": "trading"})
        receipt = self._receive(
            self._make_receipt(product=trading, qty=20.0), qty=20.0)
        qc = self._qc_picking(receipt)
        qc.move_ids.filtered(lambda m: m.product_id == trading).write({
            "quantity": 17.0, "picked": True,
            "dlm_qty_rejected": 3.0, "dlm_reject_reason": "defect"})

        qc.action_dlm_validate_qc()

        self.assertEqual(self._qty_at(self.loc_tp, product=trading), 17.0)
        self.assertEqual(self._qty_at(self.loc_tra, product=trading), 3.0)
        self.assertEqual(self._qty_at(self.loc_kho, product=trading), 0.0)

    def test_kiem_du_khong_de_ra_phieu_kiem_thua(self):
        """🔴 Kiểm hết 100 (92+8) thì không được sinh phiếu kiểm chờ tiếp.

        Đây là cái bẫy của cách tách dòng: nhu cầu dòng gốc vẫn là 100 trong khi
        thực hiện chỉ 92, nên Odoo đẻ ra một phiếu kiểm chờ 8 đơn vị đã sang khu
        trả hàng rồi. Thủ kho sẽ thấy một phiếu "chờ kiểm" không bao giờ làm được.
        """
        receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        # Neo vào backorder_id chứ không quét cả loại phiếu: DB dev có sẵn
        # phiếu kiểm treo từ trước, quét rộng là bắt nhầm chúng.
        con_lai = self.env["stock.picking"].search([("backorder_id", "=", qc.id)])
        self.assertFalse(
            con_lai, "Kiểm hết rồi mà vẫn còn phiếu kiểm treo: %s"
            % con_lai.mapped("name"))
        self.assertEqual(receipt.state, "done")

    def test_kiem_do_dang_thi_tach_phan_chua_kiem(self):
        """Kiểm 90 đạt và 8 loại trên 100 thì 2 đơn vị chưa kiểm phải sang phiếu mới.

        Ngược với ca trên: ở đây phần dư là hàng thật chưa ai nhìn tới. Nuốt mất
        nó là 2 cây thép biến khỏi sổ sách mà không lỗi nào nổ.
        """
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=90.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        # Neo vào backorder_id chứ không quét cả loại phiếu: DB dev có sẵn
        # phiếu kiểm treo từ trước, quét rộng là bắt nhầm chúng.
        con_lai = self.env["stock.picking"].search([("backorder_id", "=", qc.id)])
        self.assertTrue(con_lai, "Phần chưa kiểm phải tách sang phiếu kiểm mới.")
        self.assertEqual(sum(con_lai.move_ids.mapped("product_uom_qty")), 2.0)
        self.assertEqual(self._qty_at(self.loc_qc), 2.0)

    def test_ca_dong_bi_loai(self):
        """Loại sạch 100/100 thì không có gì vào kho, tất cả sang khu chờ trả."""
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=0.0, rejected=100.0, reason="wrong_item")
        qc.action_dlm_validate_qc()

        self.assertEqual(self._qty_at(self.loc_kho), 0.0)
        self.assertEqual(self._qty_at(self.loc_tra), 100.0)

    def test_hang_loai_giu_nguyen_lo(self):
        """§6.4: hàng loại vẫn thuộc lô đã nhận.

        Mất lô ở đây là mất bằng chứng "lô LO/2026/xxxxx của NCC này có 8 cây
        gỉ", khiếu nại NCC tụt xuống thành lời nói suông.
        """
        receipt, qc = self._qc_ready()
        lot = receipt.move_line_ids.lot_id
        self.assertTrue(lot, "Phiếu nhận phải tự sinh lô (K3).")

        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        quant_tra = self.env["stock.quant"].search([
            ("location_id", "=", self.loc_tra.id),
            ("product_id", "=", self.material.id),
        ])
        self.assertEqual(quant_tra.lot_id, lot,
                         "Hàng ở khu Chờ trả nhà cung cấp phải giữ đúng lô đã nhận.")

    # RS-01: nhóm cung ứng tách phiếu kiểm theo từng NCC
    def test_hai_ncc_ra_hai_phieu_kiem_rieng(self):
        """🔴 RS-01: hai phiếu nhận của hai NCC phải ra hai phiếu kiểm riêng.

        Nếu fail: phiếu kiểm gộp hàng nhiều NCC, ô Nhà cung cấp trống, đúng như
        ảnh chụp DL/KC/00463 gom 3 NCC. Đây là gốc của việc trả nhầm NCC.
        """
        vendor_b = self.env["res.partner"].create({"name": "NCC Sơn (test)"})
        product_b = self.env["product.product"].create({
            "name": "Sơn tĩnh điện (test)", "product_kind": "material"})

        receipt_a = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        receipt_b = self._make_receipt_from(vendor_b, product_b, 50.0)

        qc_a = self._qc_picking(receipt_a)
        qc_b = self._qc_picking(receipt_b)

        self.assertTrue(qc_a and qc_b, "Cả hai phiếu nhận phải tự sinh phiếu kiểm.")
        self.assertNotEqual(qc_a, qc_b,
                            "Hai NCC phải ra hai phiếu kiểm riêng, không gộp.")
        self.assertEqual(qc_a.partner_id, self.vendor,
                         "Phiếu kiểm A phải mang đúng NCC A (không để trống).")
        self.assertEqual(qc_b.partner_id, vendor_b)
        self.assertEqual(qc_a.move_ids.product_id, self.material,
                         "Phiếu kiểm A chỉ được chứa hàng của NCC A.")
        self.assertEqual(qc_b.move_ids.product_id, product_b)

    def test_hai_lan_nhan_cung_mot_ncc_van_hai_phieu_kiem(self):
        """🔴 RS-01: đơn vị tách là lần nhận, không phải nhà cung cấp.

        Cùng một NCC giao hai chuyến trong ngày vẫn phải ra hai phiếu kiểm: hàng
        lỗi ở chuyến nào thì khiếu nại theo chứng từ của chuyến đó.
        """
        receipt_1 = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        receipt_2 = self._receive(self._make_receipt(qty=30.0), qty=30.0)

        qc_1 = self._qc_picking(receipt_1)
        qc_2 = self._qc_picking(receipt_2)
        self.assertNotEqual(qc_1, qc_2,
                            "Mỗi lần nhận hàng phải có phiếu kiểm riêng.")
        self.assertEqual(qc_1.origin, receipt_1.name,
                         "Phiếu kiểm phải chỉ đúng phiếu nhận đã sinh ra nó.")
        self.assertEqual(qc_2.origin, receipt_2.name)

    def test_khong_gop_phieu_kiem_ngay_ca_khi_thieu_nhom_cung_ung(self):
        """🔴 RS-01: mất nhóm cung ứng cũng không được gộp hai phiếu nhận.

        Nhóm cung ứng là cơ chế chuẩn của Odoo nhưng vẫn là một ô có thể trống:
        dữ liệu cũ, phiếu tạo tay, hoặc một đường xác nhận khác ghi đè. Chính ca
        này đã xảy ra thật trên dlm_dev (DL/KC/00003 gom DL/NH/00003 và
        DL/NH/00004). Bất biến "một phiếu nhận = một phiếu kiểm" phải đứng vững
        cả khi nhóm biến mất.
        """
        vendor_b = self.env["res.partner"].create({"name": "NCC Sơn (test)"})
        product_b = self.env["product.product"].create({
            "name": "Sơn tĩnh điện (test)", "product_kind": "material"})

        Picking = type(self.env["stock.picking"])
        goc = Picking._dlm_group_receipt_moves
        Picking._dlm_group_receipt_moves = lambda self: True
        try:
            receipt_a = self._receive(self._make_receipt(qty=100.0), qty=100.0)
            receipt_b = self._make_receipt_from(vendor_b, product_b, 50.0)
        finally:
            Picking._dlm_group_receipt_moves = goc

        qc_a = self._qc_picking(receipt_a)
        qc_b = self._qc_picking(receipt_b)
        self.assertFalse(qc_a.move_ids.group_id,
                         "Ca test phải thật sự chạy ở trạng thái KHÔNG có nhóm.")
        self.assertNotEqual(qc_a, qc_b,
                            "Thiếu nhóm vẫn không được nhồi chung phiếu kiểm.")
        self.assertEqual(qc_a.move_ids.product_id, self.material)
        self.assertEqual(qc_b.move_ids.product_id, product_b)

    def test_tra_hang_ghi_dung_ncc_khi_nhieu_ncc_cho_kiem(self):
        """🔴 RS-01 + RS-08: loại hàng NCC B thì phiếu trả phải ghi đúng NCC B.

        Ca tốn tiền nhất: hàng của nhiều NCC cùng nằm khu Chờ kiểm. Loại hàng
        NCC nào thì phiếu trả phải về đúng NCC đó, và trỏ về phiếu nhận gốc
        (không phải phiếu kiểm, RS-08).
        """
        vendor_b = self.env["res.partner"].create({"name": "NCC Sơn (test)"})
        product_b = self.env["product.product"].create({
            "name": "Sơn tĩnh điện (test)", "product_kind": "material"})

        # NCC A nhận trước (hàng A nằm sẵn khu Chờ kiểm), NCC B nhận sau.
        self._receive(self._make_receipt(qty=100.0), qty=100.0)
        receipt_b = self._make_receipt_from(vendor_b, product_b, 50.0)

        qc_b = self._qc_picking(receipt_b)
        move_b = qc_b.move_ids.filtered(lambda m: m.product_id == product_b)
        move_b.write({
            "quantity": 42.0, "picked": True,
            "dlm_qty_rejected": 8.0, "dlm_reject_reason": "defect"})
        qc_b.action_dlm_validate_qc()

        returns = qc_b._dlm_vendor_returns()
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.partner_id, vendor_b,
                         "Phiếu trả phải ghi ĐÚNG NCC của mặt hàng bị loại.")
        self.assertEqual(returns.dlm_origin_picking_id, receipt_b,
                         "RS-08 — trỏ về phiếu NHẬN gốc, không phải phiếu kiểm.")

    # Phiếu trả NCC
    def test_sinh_phieu_tra_ncc_o_trang_thai_nhap(self):
        """§6.4: có hàng loại thì sinh phiếu trả NCC, để nháp cho Mua hàng.

        Để nháp là cố ý: trả hàng là việc đối ngoại (đổi hàng, giảm trừ công
        nợ...). Tự xác nhận là thủ kho vô tình quyết thay Mua hàng.
        """
        receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        returns = qc._dlm_vendor_returns()
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.state, "draft", "Phiếu trả phải để NHÁP.")
        self.assertEqual(returns.partner_id, self.vendor)
        self.assertEqual(returns.dlm_origin_picking_id, receipt,
                         "Phiếu trả phải neo về phiếu NHẬN để đối chiếu hoá đơn NCC.")
        self.assertEqual(sum(returns.move_ids.mapped("product_uom_qty")), 8.0)
        self.assertEqual(returns.location_id, self.loc_tra)

    def test_phieu_tra_tra_duoc_tu_ca_hai_chang(self):
        """Đứng ở phiếu nhận hay phiếu kiểm đều mở được phiếu trả."""
        receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        self.assertEqual(qc.dlm_return_count, 1)
        self.assertEqual(receipt.dlm_return_count, 1)
        self.assertEqual(
            qc.action_dlm_open_returns()["res_model"], "stock.picking")

    def test_giao_viec_cho_mua_hang(self):
        """§6.4: phiếu trả nháp không ai biết thì sẽ nằm im mãi, nên phải giao việc."""
        purchasing = self.env.ref("dl_base.dl_group_purchasing")
        buyer = self.env["res.users"].create({
            "name": "muahang_k5", "login": "muahang_k5",
            "groups_id": [(6, 0, [purchasing.id])],
        })

        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        returns = qc._dlm_vendor_returns()
        self.assertIn(buyer, returns.activity_ids.user_id,
                      "Mua hàng phải nhận được việc xử lý phiếu trả.")

    # Ràng buộc QC-01..04: báo inline, chặn ở server
    def test_qc02_dat_cong_loai_vuot_so_ncc_giao(self):
        """QC-02: 95 đạt cộng 8 loại trên 100 giao là con số không tồn tại."""
        _receipt, qc = self._qc_ready()
        move = self._fill_qc(qc, passed=95.0, rejected=8.0)

        self.assertTrue(move.dlm_qc_over, "Dòng phải tự tô cờ vượt số.")
        self.assertTrue(qc.dlm_blocked)
        self.assertEqual(qc.dlm_banner_level, "danger")
        with self.assertRaises(UserError):
            qc.action_dlm_validate_qc()

    def test_qc03_co_hang_loai_ma_khong_ly_do(self):
        """QC-03: "8 cây loại" không kèm lý do thì không đàm phán được với NCC."""
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0, reason=False)

        self.assertTrue(qc.dlm_blocked)
        with self.assertRaises(UserError):
            qc.action_dlm_validate_qc()

    def test_qc04_ly_do_khac_phai_ghi_ro(self):
        """QC-04: lý do "Khác" mà bỏ trống ghi chú là không ghi gì cả."""
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0, reason="other")

        self.assertTrue(qc.dlm_blocked)
        with self.assertRaises(UserError):
            qc.action_dlm_validate_qc()

        self._qc_move(qc).dlm_reject_note = "Sơn tróc mảng lớn"
        qc.invalidate_recordset()
        self.assertFalse(qc.dlm_blocked)

    def test_dai_thong_bao_neu_ro_dong_nao_sai(self):
        """§11.4: dải đỏ phải gọi tên dòng cụ thể, không nói chung chung.

        "Thiếu lý do loại" trên phiếu 20 dòng buộc thủ kho tự dò từng dòng.
        """
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0, reason=False)

        self.assertIn(self.material.display_name, qc.dlm_banner_message)

    # Ranh giới giữa "giao thiếu" và "hàng lỗi"
    def test_giao_thieu_khong_bien_thanh_hang_loai(self):
        """🔴 §6.1: NCC giao 95/100 là giao thiếu, không phải hàng lỗi.

        Nếu fail: hệ thống ghi NCC giao hàng kém trong khi thật ra họ chỉ giao
        thiếu, đây là hai vấn đề khác nhau, hai cách xử lý khác nhau.
        """
        receipt = self._make_receipt(qty=100.0)
        receipt.move_ids.quantity = 95.0
        receipt.move_ids.picked = True
        receipt.with_context(skip_backorder=True).button_validate()

        self.assertEqual(receipt.state, "done")
        self.assertEqual(sum(receipt.move_ids.mapped("dlm_qty_rejected")), 0.0,
                         "Giao thiếu KHÔNG được ghi vào số hàng loại.")
        self.assertEqual(receipt.dlm_qc_state, "none",
                         "Chip kiểm hàng chỉ thuộc về phiếu kiểm.")

        backorder = self.env["stock.picking"].search([
            ("backorder_id", "=", receipt.id)])
        self.assertTrue(backorder, "Phần giao thiếu phải thành phiếu chờ giao tiếp.")

    def test_dai_canh_bao_giao_thieu_neu_he_qua(self):
        """§11.3: dải cảnh báo phải nói hệ quả, không chỉ nêu sự kiện."""
        receipt = self._make_receipt(qty=100.0)
        receipt.move_ids.quantity = 95.0

        self.assertEqual(receipt.dlm_banner_level, "warning")
        self.assertIn("chờ giao tiếp", receipt.dlm_banner_message)

    # Nút phụ và trạng thái hiển thị
    def test_dat_tat_ca(self):
        """§11.4: ca phổ biến nhất (hàng về đủ và tốt) chỉ tốn một cú bấm."""
        _receipt, qc = self._qc_ready()
        qc.action_dlm_pass_all()

        self.assertEqual(self._qc_move(qc).quantity, 100.0)
        self.assertEqual(qc.dlm_qty_rejected_total, 0.0)
        self.assertFalse(qc.dlm_blocked)

        qc.action_dlm_validate_qc()
        self.assertEqual(self._qty_at(self.loc_kho), 100.0)
        self.assertEqual(qc.dlm_qc_state, "passed")

    def test_chip_ket_qua_kiem(self):
        """Chip trên list: đọc được chất lượng hàng mà không phải mở phiếu."""
        _receipt, qc = self._qc_ready()
        self.assertEqual(qc.dlm_qc_state, "pending")

        self._fill_qc(qc, passed=92.0, rejected=8.0)
        self.assertEqual(qc.dlm_qc_state, "has_reject")
        self.assertEqual(qc.dlm_qty_rejected_total, 8.0)

    def test_phieu_xong_khong_con_dai_do(self):
        """Sau khi xác nhận, dòng gốc bị thu hẹp nhu cầu nên phép so QC-02 hết
        nghĩa. Không tắt thì phiếu đã xong lại hiện dải đỏ vô cớ."""
        _receipt, qc = self._qc_ready()
        self._fill_qc(qc, passed=92.0, rejected=8.0)
        qc.action_dlm_validate_qc()

        self.assertFalse(qc.dlm_blocked)
        self.assertEqual(qc.dlm_banner_level, "warning")
        self.assertIn("Chờ trả nhà cung cấp", qc.dlm_banner_message)

    # Quyền và giao diện
    def test_man_kiem_hang_khong_lo_gia(self):
        """🔴 §8.3: Thủ kho đếm hàng, không định giá."""
        view = self.env.ref("dl_inventory.view_dl_qc_form")
        for token in ("standard_price", "price_unit", "value", "amount"):
            self.assertNotIn(
                token, view.arch,
                "Màn Kiểm hàng không được có ô liên quan tới giá ('%s')." % token)

    def test_thu_kho_kiem_duoc_hang(self):
        """Vai trò Thủ kho phải thực sự chạy được luồng kiểm, không chỉ xem."""
        user = self.env["res.users"].create({
            "name": "thukho_k5", "login": "thukho_k5",
            "groups_id": [(6, 0, [self.env.ref("dl_base.dl_group_warehouse").id])],
        })
        _receipt, qc = self._qc_ready()
        qc_as_wh = qc.with_user(user)
        self._fill_qc(qc_as_wh, passed=92.0, rejected=8.0)
        qc_as_wh.action_dlm_validate_qc()

        self.assertEqual(self._qty_at(self.loc_tra), 8.0)

    def test_man_nhan_hang_tao_duoc_phieu(self):
        """Màn Nhận hàng phải có nút Tạo, màn Kiểm hàng thì không.

        Đã vấp thật: một tree dùng chung cho cả hai màn, để create="0" là màn
        Nhận hàng mất nút Tạo, trong khi ô trạng thái rỗng của chính nó vẫn mời
        "tạo một phiếu nhận". Không lỗi nào nổ, chỉ là ngõ cụt.

        Lưu ý: `context="{'create': False}"` trên act_window không thay được vì
        Odoo 17 chỉ đọc `create` từ thuộc tính trên arch (web/views/utils.getActiveActions).
        """
        cases = [
            ("dl_inventory.action_dl_picking_receipt", True,
             "Thủ kho phải tạo được phiếu nhận khi NCC giao hàng."),
            ("dl_inventory.action_dl_picking_qc", False,
             "Phiếu kiểm do tuyến nhận 2 bước tự sinh — tạo tay là phiếu mồ côi."),
        ]
        for xml_id, can_create, message in cases:
            action = self.env.ref(xml_id)
            tree = action.view_ids.filtered(
                lambda v: v.view_mode == "tree").view_id
            # get_combined_arch: bản không cho tạo là view kế thừa, `arch` của nó
            # chỉ chứa chỉ thị vá, phải gộp với view cha mới ra arch thật.
            arch = tree.get_combined_arch()
            self.assertEqual('create="0"' not in arch, can_create, message)

    def test_man_nhan_hang_dien_san_loai_phieu(self):
        """Bấm Tạo là loại phiếu đã sẵn "Nhận hàng nhà cung cấp", không phải tự chọn."""
        action = self.env.ref("dl_inventory.action_dl_picking_receipt")
        self.assertIn("restricted_picking_type_code", action.context)

        picking = self.env["stock.picking"].with_context(
            restricted_picking_type_code="incoming").new({})
        self.assertEqual(picking.picking_type_id.code, "incoming")

    def test_menu_moi_co_action(self):
        """Bẫy CLAUDE.md: menu lá rỗng action biến mất khỏi rail, không lỗi nào nổ."""
        for xml_id in ("dl_inventory.menu_dl_picking_receipt",
                       "dl_inventory.menu_dl_picking_qc"):
            menu = self.env.ref(xml_id)
            self.assertTrue(menu.action, "%s thiếu action ⇒ mất khỏi rail." % xml_id)
            self.assertEqual(menu.parent_id,
                             self.env.ref("dl_base.menu_dl_inventory"))
