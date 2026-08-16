# -*- coding: utf-8 -*-
"""K17 — Bằng chứng hàng loại: chụp một lần, đọc được ở cả ba chặng.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §6.4, §6.4.1.

Vì sao bộ test này tồn tại: trước K17, tất cả những gì Đại Linh cầm đi đòi NCC là
một dropdown "Hàng lỗi / hư hỏng" và một dòng ghi chú. NCC chối thì không có gì
để đưa ra. Ảnh chụp lúc mở hàng là thứ duy nhất đổi được kết quả cuộc đàm phán —
mà giá trị của nó nằm trọn ở hai tính chất, hai tính chất đó chính là hai nhóm
test ở đây:

    ĐI ĐƯỢC   ảnh chụp ở phiếu [2] phải tự có mặt ở [3] và [9], vì người cần
              xem (Mua hàng, người duyệt ghi giảm) không phải người đã chụp.
    KHOÁ ĐƯỢC ảnh thêm được SAU KHI biết NCC cãi gì thì không còn là bằng
              chứng — nó thành lời khai. Khoá phải nằm ở tầng server, không chỉ
              readonly trên view.

Sai lặng lẽ đáng sợ nhất ở đây: `ir.attachment` giữ `res_id=0` (bẫy đã vấp ở
RFQ). Không lỗi nào nổ lúc thủ kho upload — chỉ tới khi Mua hàng mở phiếu trả
mới ăn AccessError, đúng lúc cần ảnh nhất.
"""

import base64
import io

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestQcEvidence(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Guard khoá bằng chứng bỏ qua `env.su`, mà env của TransactionCase chạy
        # dưới SUPERUSER_ID (thì su=True). Mọi ca kiểm khoá phải đi qua user thật,
        # không thì test xanh trong khi lá chắn không hề chạy.
        cls.thukho = cls.env["res.users"].create({
            "name": "thukho_k17", "login": "thukho_k17",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_warehouse").id])],
        })

    # ── Tiện ích ─────────────────────────────────────────────────────────────
    def _anh(self, name="thep-gi-01.jpg"):
        """Ảnh y như widget many2many_binary tạo ra: CHƯA có res_id."""
        attachment = self.env["ir.attachment"].create({
            "name": name,
            "datas": base64.b64encode(b"anh-gia-lap-cho-test"),
        })
        self.assertFalse(
            attachment.res_id,
            "Ca test phải bắt đầu từ attachment mồ côi — đó mới là thứ bẫy "
            "res_id=0 nói tới.")
        return attachment

    def _qc_co_hang_loai(self, dat=92.0, loai=8.0, so_anh=1):
        """Phiếu kiểm đã điền kết quả + đính ảnh, CHƯA xác nhận."""
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        # Ảnh THẬT: từ khi lưới giải mã ảnh để nhúng thumbnail, bytes rác rơi
        # xuống nhánh "ảnh hỏng" — nền chung phải dùng ca bình thường.
        anh = self.env["ir.attachment"]
        for i in range(so_anh):
            anh |= self._anh_that("thep-gi-%02d.png" % (i + 1))
        move.write({
            "quantity": dat,
            "picked": True,
            "dlm_qty_rejected": loai,
            "dlm_reject_reason": "defect",
            "dlm_evidence_ids": [(6, 0, anh.ids)],
        })
        return receipt, qc, move, anh

    # ── Nhóm 1: ảnh ĐI ĐƯỢC hết chuỗi chứng từ ──────────────────────────────
    def test_anh_duoc_dong_dau_ve_dung_dong(self):
        """TC-INT-TestQcEvidence-001: Bẫy res_id=0 — ảnh phải được neo về dòng kiểm ngay
        khi ghi.

        Nếu đỏ: thủ kho upload xong thấy bình thường, nhưng Mua hàng mở phiếu trả sẽ ăn
        AccessError — attachment res_id=0 chỉ người tạo và admin đọc được. Hỏng đúng lúc
        cần ảnh nhất, và không ai đoán ra vì sao.
        """
        _receipt, _qc, move, anh = self._qc_co_hang_loai()

        self.assertEqual(anh.res_model, "stock.move")
        self.assertEqual(anh.res_id, move.id)

    def test_anh_sang_phieu_tra_ncc(self):
        """TC-INT-TestQcEvidence-002: §6.4 — Ảnh phải có mặt trên phiếu [3], nơi Mua hàng
        thật sự dùng nó.

        Đây là lý do tồn tại của cả tính năng: người chụp (thủ kho) và người đàm phán
        (Mua hàng) là hai người khác nhau, ngồi hai chỗ khác nhau.
        """
        _receipt, qc, _move, anh = self._qc_co_hang_loai(so_anh=2)
        qc.action_dlm_validate_qc()

        tra = qc._dlm_vendor_returns()
        self.assertEqual(len(tra), 1)
        dong_tra = tra.move_ids.filtered(lambda m: m.product_id == self.material)
        self.assertEqual(dong_tra.dlm_evidence_ids, anh,
                         "Phiếu trả NCC phải đọc được đúng bộ ảnh của dòng kiểm.")
        self.assertEqual(dong_tra.dlm_evidence_count, 2)

    def test_khong_nhan_ban_file(self):
        """TC-INT-TestQcEvidence-003: Ba chặng dùng CHUNG bản ghi ir.attachment, không copy
        file.

        Copy thì filestore phình theo mỗi chặng (ảnh điện thoại 3–5MB/tấm), và tệ hơn:
        xoá một bản không xoá bản kia thì hai chặng nói hai chuyện khác nhau về cùng một
        lô hàng.
        """
        _receipt, qc, move, anh = self._qc_co_hang_loai()
        qc.action_dlm_validate_qc()

        tra = qc._dlm_vendor_returns()
        dong_tra = tra.move_ids.filtered(lambda m: m.product_id == self.material)
        self.assertEqual(dong_tra.dlm_evidence_ids.ids, anh.ids,
                         "Phải là CÙNG bản ghi attachment, không phải bản sao.")
        self.assertEqual(move.dlm_evidence_ids.ids, anh.ids,
                         "Dòng kiểm gốc vẫn giữ nguyên bằng chứng của nó.")

    def test_anh_sang_dong_tach_trong_phieu_kiem(self):
        """TC-INT-TestQcEvidence-004: Dòng tách chở hàng sang khu Chờ trả cũng phải mang
        theo bằng chứng.

        Cùng lý do đã áp cho lý do/ghi chú: ai nhìn thấy hàng đi đâu thì phải nhìn thấy
        luôn vì sao nó đi.
        """
        _receipt, qc, _move, anh = self._qc_co_hang_loai()
        qc.action_dlm_validate_qc()

        dong_tach = qc.move_ids.filtered(
            lambda m: m.location_dest_id == self.loc_tra)
        self.assertTrue(dong_tach, "Phải có dòng chở hàng loại sang Chờ trả.")
        self.assertEqual(dong_tach.dlm_evidence_ids, anh)

    def test_anh_sang_phieu_hoa_phe_lieu(self):
        """TC-INT-TestQcEvidence-005: §6.4.1 — Kết cục hay gặp nhất: NCC giảm trừ công nợ,
        mình giữ hàng.

        Phiếu [9] là chứng từ ghi giảm tài sản, và người ký nó không phải người đã cầm 8
        cây thép gỉ trên tay. Không kéo ảnh tới đây thì bằng chứng đứt đúng ở chặng cần
        nó nhất.
        """
        scrap = self.env["product.product"].search(
            [("dlm_is_scrap", "=", True)], limit=1)
        if not scrap:
            scrap = self.env["product.product"].create({
                "name": "Phế liệu thép (test K17)",
                "product_kind": "material", "dlm_is_scrap": True})
        scrap.tracking = "none"
        self.material.dlm_mass_per_unit = 6.0

        _receipt, qc, _move, anh = self._qc_co_hang_loai()
        qc.action_dlm_validate_qc()
        tra = qc._dlm_vendor_returns()
        tra.action_cancel()

        hpl = tra.action_dlm_to_scrap()
        picking = self.env["stock.picking"].browse(hpl["res_id"])
        dong_bo = picking.move_ids.filtered(
            lambda m: m.product_id == self.material)
        self.assertEqual(dong_bo.dlm_evidence_ids, anh,
                         "Phiếu hoá phế liệu phải mang theo bằng chứng hàng lỗi.")

    # ── Nhóm 2: ảnh KHOÁ ĐƯỢC ───────────────────────────────────────────────
    def test_khoa_sau_khi_xac_nhan_kiem(self):
        """TC-INT-TestQcEvidence-006: Xác nhận kiểm xong là bằng chứng đóng băng — chặn ở
        tầng SERVER.

        Readonly trên view không đủ: sửa qua RPC vẫn lọt, và lá chắn chỉ còn là trang
        trí. Bằng chứng sửa được sau khi biết NCC cãi gì thì vô giá trị.
        """
        _receipt, qc, move, _anh = self._qc_co_hang_loai()
        qc.action_dlm_validate_qc()

        move_as_wh = move.with_user(self.thukho)
        self.assertTrue(move_as_wh.dlm_evidence_locked)
        with self.assertRaises(UserError):
            move_as_wh.write({"dlm_evidence_ids": [(6, 0, self._anh().ids)]})

    def test_mua_hang_khong_them_duoc_anh_tren_phieu_tra(self):
        """TC-INT-TestQcEvidence-007: Dòng phiếu trả NCC luôn khoá, kể cả khi phiếu còn
        nháp.

        Ảnh thuộc về thời điểm mở hàng, không thuộc về lúc thương lượng. Mở cho Mua hàng
        thêm ảnh là mở đúng cửa mà cả tính năng này sinh ra để đóng.
        """
        _receipt, qc, _move, _anh = self._qc_co_hang_loai()
        qc.action_dlm_validate_qc()

        tra = qc._dlm_vendor_returns()
        self.assertEqual(tra.state, "draft", "Phiếu trả vẫn đang nháp.")
        dong_tra = tra.move_ids.filtered(
            lambda m: m.product_id == self.material).with_user(self.thukho)
        self.assertTrue(dong_tra.dlm_evidence_locked,
                        "Phiếu trả chỉ ĐỌC bằng chứng, không ghi.")
        with self.assertRaises(UserError):
            dong_tra.write({"dlm_evidence_ids": [(6, 0, self._anh().ids)]})

    def test_truoc_khi_xac_nhan_thi_sua_duoc(self):
        """TC-INT-TestQcEvidence-008: Mặt còn lại của khoá: đang kiểm thì phải chụp
        thêm/bớt được thoải mái.
        """
        _receipt, _qc, move, anh = self._qc_co_hang_loai()
        move_as_wh = move.with_user(self.thukho)

        self.assertFalse(move_as_wh.dlm_evidence_locked)
        them = self._anh("thep-gi-99.jpg")
        move_as_wh.write({"dlm_evidence_ids": [(4, them.id)]})
        self.assertEqual(move_as_wh.dlm_evidence_count, len(anh) + 1)

    # ── Nhóm 3: nhắc chứ KHÔNG chặn ─────────────────────────────────────────
    def test_thieu_anh_chi_canh_bao_khong_chan(self):
        """TC-INT-TestQcEvidence-009: Thiếu ảnh không được chặn xác nhận kiểm.

        Chặn thì thủ kho ca đêm sẽ chụp bừa cho qua cổng — được một trường bắt buộc chứa
        rác, tệ hơn trường trống vì nó tạo cảm giác đã có bằng chứng. Dải cảnh báo phải
        gọi đích danh mặt hàng, không nói chung chung.
        """
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        qc.move_ids.filtered(lambda m: m.product_id == self.material).write({
            "quantity": 92.0, "picked": True,
            "dlm_qty_rejected": 8.0, "dlm_reject_reason": "defect"})

        self.assertFalse(qc.dlm_blocked, "Thiếu ảnh KHÔNG được chặn nút.")
        self.assertEqual(qc.dlm_banner_level, "warning")
        self.assertIn("ảnh bằng chứng", qc.dlm_banner_message)
        self.assertIn(self.material.display_name, qc.dlm_banner_message)

        qc.action_dlm_validate_qc()
        self.assertEqual(qc.state, "done")

    def test_co_anh_thi_khong_nhac_nua(self):
        """TC-INT-TestQcEvidence-010: Đã chụp rồi mà dải vẫn nhắc là dạy người dùng bỏ qua
        dải.
        """
        _receipt, qc, _move, _anh = self._qc_co_hang_loai()

        self.assertEqual(qc.dlm_banner_level, "warning")
        self.assertNotIn("ảnh bằng chứng", qc.dlm_banner_message)
        self.assertFalse(qc._dlm_evidence_missing_names())

    def test_chatter_ghi_co_bao_nhieu_anh(self):
        """TC-INT-TestQcEvidence-011: Dấu vết còn lại sau khi phiếu bị lật đi lật lại phải
        tự nói ra điều đó.
        """
        _receipt, qc, _move, _anh = self._qc_co_hang_loai(so_anh=2)
        qc.action_dlm_validate_qc()

        body = "".join(qc.message_ids.mapped("body"))
        self.assertIn("2</b> ảnh", body)

    def test_chatter_noi_ro_khi_khong_co_anh(self):
        """TC-INT-TestQcEvidence-012: Im lặng ở đây bị đọc thành "chắc có ảnh đâu đó" —
        phải nói thẳng.
        """
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        qc.move_ids.filtered(lambda m: m.product_id == self.material).write({
            "quantity": 92.0, "picked": True,
            "dlm_qty_rejected": 8.0, "dlm_reject_reason": "defect"})
        qc.action_dlm_validate_qc()

        body = "".join(qc.message_ids.mapped("body"))
        self.assertIn("không có ảnh", body)

    # ── Nhóm 4: biên bản PDF gửi NCC ────────────────────────────────────────
    # Bằng chứng nằm trong Odoo là bằng chứng CHƯA dùng được: NCC không đăng
    # nhập ERP của Đại Linh. Tờ biên bản này là chặng cuối của cả chuỗi.
    def _anh_that(self, name="thep-gi-that.png"):
        """Ảnh PNG THẬT — nền chung cho cả lưới thumbnail lẫn biên bản PDF.

        Kích thước cố ý LỚN hơn khung 480px để ca thu nhỏ thật sự chạy.
        """
        from PIL import Image as PILImage
        buf = io.BytesIO()
        PILImage.new("RGB", (900, 700), (180, 30, 30)).save(buf, format="PNG")
        return self.env["ir.attachment"].create({
            "name": name,
            "datas": base64.b64encode(buf.getvalue()),
            "mimetype": "image/png",
        })

    def _phieu_tra(self, anh=None):
        """Phiếu trả NCC nháp, sinh từ một lần kiểm có hàng loại."""
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]
        move.write({
            "quantity": 92.0, "picked": True,
            "dlm_qty_rejected": 8.0, "dlm_reject_reason": "defect",
            "dlm_reject_note": "Gỉ sét mặt ngoài, 8 cây",
            "dlm_evidence_ids": [(6, 0, (anh or self.env["ir.attachment"]).ids)],
        })
        qc.action_dlm_validate_qc()
        return qc._dlm_vendor_returns()

    def test_bien_ban_khong_co_gia(self):
        """TC-INT-TestQcEvidence-013: Biên bản nói về hàng, không phải tiền.

        In số tiền lên tờ giấy đưa cho NCC trước khi đàm phán là tự chốt mức giảm trừ hộ
        họ. Giá mua lại càng không có lý do gì phải in ra rồi đưa cho chính người bán.
        """
        tra = self._phieu_tra()
        rows = tra._dlm_reject_report_rows()

        self.assertTrue(rows)
        for row in rows:
            for key in row:
                for token in ("price", "cost", "amount", "value", "gia"):
                    self.assertNotIn(
                        token, key,
                        "Biên bản gửi NCC không được mang dữ liệu tiền ('%s')."
                        % key)

    def test_bien_ban_lay_duoc_so_lo_khi_con_nhap(self):
        """TC-INT-TestQcEvidence-014: Lô phải ra được lúc phiếu còn nháp — đó mới là lúc
        cần in.

        `move.lot_ids` của phiếu trả trống khi chưa giữ chỗ. Không có đường lùi về tồn
        thật thì biên bản đi đàm phán mà cột Số lô để trắng — mất đúng mắt xích tra
        ngược về chuyến giao.
        """
        tra = self._phieu_tra()
        self.assertEqual(tra.state, "draft")

        rows = tra._dlm_reject_report_rows()
        self.assertTrue(rows[0]["lots"],
                        "Cột Số lô không được để trắng trên phiếu nháp.")
        self.assertTrue(rows[0]["lots"].startswith("LO/"))

    def test_dung_duoc_pdf(self):
        """TC-INT-TestQcEvidence-015: Biên bản dựng ra phải là PDF thật, có nhúng ảnh.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        noi_dung = tra._dlm_build_reject_report()

        self.assertTrue(noi_dung.startswith(b"%PDF"))
        self.assertGreater(len(noi_dung), 1000)

    def test_anh_hong_khong_giet_ca_bien_ban(self):
        """TC-INT-TestQcEvidence-016: Một tấm ảnh đọc không được thì bỏ tấm đó, không bỏ cả
        tờ giấy.

        Mất một tấm vẫn còn biên bản để ký; nổ cả hàm là Mua hàng ra gặp NCC tay không,
        mà lỗi thì hiện ra đúng lúc sắp đi họp.
        """
        hong = self._anh("anh-hong.jpg")          # bytes rác, mimetype ảnh
        tra = self._phieu_tra(anh=hong + self._anh_that())

        noi_dung = tra._dlm_build_reject_report()
        self.assertTrue(noi_dung.startswith(b"%PDF"))

    def test_nut_in_luu_dau_vet_va_tra_link_tai_ve(self):
        """TC-INT-TestQcEvidence-017: Bản đưa cho NCC là chứng từ đối ngoại thì phải lưu
        lại được cái đã đưa.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        so_tin_truoc = len(tra.message_ids)

        action = tra.action_dlm_print_reject_report()

        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("download=true", action["url"])
        dinh_kem = self.env["ir.attachment"].search([
            ("res_model", "=", "stock.picking"), ("res_id", "=", tra.id),
            ("mimetype", "=", "application/pdf")])
        self.assertTrue(dinh_kem, "Biên bản phải được lưu lại trên phiếu.")
        self.assertIn("Bien_ban_hang_khong_dat", dinh_kem[0].name)
        self.assertGreater(len(tra.message_ids), so_tin_truoc,
                           "Chatter phải ghi lại lần lập biên bản.")

    def test_khong_lap_bien_ban_tu_phieu_khac(self):
        """TC-INT-TestQcEvidence-018: Biên bản chỉ có nghĩa trên phiếu trả NCC — phiếu kiểm
        không có đối tác để gửi, in ra là một tờ giấy nói sai chuyện.
        """
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)

        with self.assertRaises(UserError):
            qc.action_dlm_print_reject_report()

    # ── Nhóm 5: xem được ẢNH, không phải xem danh sách file ─────────────────
    def test_anh_nhung_thang_khong_qua_url(self):
        """TC-INT-TestQcEvidence-019: Ảnh phải nhúng thẳng, không trỏ qua /web/image.

        Bản đầu dùng `<img src="/web/image/ir.attachment/...">` và ảnh vỡ ngay khi thủ
        kho vừa upload. Truy ngược thì tầng server sạch hết (`check('read')` pass với
        `res_id=0`, `_find_record` pass, route hợp lệ) thì chỗ gãy nằm ngoài tầm quan
        sát. Nhúng thẳng thì cả đoạn đường đó không còn tồn tại để mà gãy.
        """
        _receipt, _qc, move, _anh = self._qc_co_hang_loai(so_anh=2)
        html = move.dlm_evidence_gallery or ""

        self.assertIn("dl-evi-gallery", html)
        self.assertEqual(html.count("<img"), 2, "Phải có đúng 2 thumbnail.")
        self.assertEqual(html.count("data:image/jpeg;base64,"), 2)
        self.assertNotIn(
            "/web/image/", html,
            "Còn URL /web/image là lỗi ảnh vỡ còn đường quay lại.")

    def test_anh_nhung_giai_ma_duoc_that(self):
        """TC-INT-TestQcEvidence-020: Chuỗi base64 nhúng vào phải là ảnh thật mở ra được.

        Không có ca này thì `data:image/jpeg;base64,` rỗng hoặc rác vẫn "đúng định dạng"
        với mọi phép kiểm chuỗi — và trình duyệt lại hiện đúng cái biểu tượng ảnh vỡ mà
        bản này sinh ra để diệt.
        """
        from PIL import Image as PILImage

        anh = self._anh_that()
        thumb = anh._dlm_evidence_thumb()
        self.assertTrue(thumb, "Phải dựng được thumbnail.")

        img = PILImage.open(io.BytesIO(base64.b64decode(thumb)))
        img.verify()
        self.assertLessEqual(max(img.size), 480, "Phải thu nhỏ trước khi nhúng.")

    def test_luoi_anh_co_khi_chua_luu(self):
        """TC-INT-TestQcEvidence-021: Thấy ảnh NGAY khi vừa chọn file, không phải lưu rồi
        mở lại.

        `many2many_binary` tạo attachment ngay lúc upload nên id đã có thật — compute
        chạy được trên bản ghi chưa lưu. Mất tính chất này thì thủ kho up xong nhìn vào
        khoảng trắng và tưởng hệ thống nuốt ảnh.
        """
        anh = self._anh_that()
        nhap = self.env["stock.move"].new({"dlm_evidence_ids": [(6, 0, anh.ids)]})

        self.assertIn("data:image/jpeg;base64,", nhap.dlm_evidence_gallery or "")

    def test_anh_res_id_0_van_hien(self):
        """TC-INT-TestQcEvidence-022: Đúng ca thủ kho gặp: ảnh vừa upload còn `res_id=0`.

        Đây là trạng thái giữa lúc chọn file và lúc bấm Lưu — cũng chính là lúc người ta
        nhìn vào hộp để kiểm tra mình vừa chụp cái gì.
        """
        mo_coi = self._anh_that("chua-dong-dau.png")
        self.assertFalse(mo_coi.res_id, "Ca test phải chạy với attachment mồ côi.")

        nhap = self.env["stock.move"].new(
            {"dlm_evidence_ids": [(6, 0, mo_coi.ids)]})
        self.assertIn("data:image/jpeg;base64,", nhap.dlm_evidence_gallery or "")

    def test_file_khong_phai_anh_van_duoc_neu_ten(self):
        """TC-INT-TestQcEvidence-023: PDF/video không xem trực tiếp được, nhưng phải biết
        là có.
        """
        pdf = self.env["ir.attachment"].create({
            "name": "chung-thu-kiem-dinh.pdf",
            "datas": base64.b64encode(b"%PDF-1.4 gia lap"),
            "mimetype": "application/pdf",
        })
        _receipt, _qc, move, _anh = self._qc_co_hang_loai(so_anh=1)
        move.write({"dlm_evidence_ids": [(4, pdf.id)]})
        html = move.dlm_evidence_gallery or ""

        self.assertEqual(html.count("<img"), 1, "Chỉ ảnh mới thành thumbnail.")
        self.assertIn("chung-thu-kiem-dinh.pdf", html)

    def test_anh_hong_rot_xuong_link_khong_giet_luoi(self):
        """TC-INT-TestQcEvidence-024: Ảnh hỏng (bytes rác, mimetype ảnh) chỉ mất tấm đó.

        `_anh()` tạo đúng loại này. Không nuốt lỗi thì cả hộp bằng chứng trắng xoá vì
        một file hỏng — và người dùng mất luôn những tấm còn tốt.
        """
        hong = self._anh("anh-hong.jpg")
        tot = self._anh_that()
        nhap = self.env["stock.move"].new(
            {"dlm_evidence_ids": [(6, 0, (hong + tot).ids)]})
        html = nhap.dlm_evidence_gallery or ""

        self.assertEqual(html.count("<img"), 1, "Tấm tốt vẫn phải hiện.")
        self.assertIn("anh-hong.jpg", html, "Tấm hỏng vẫn phải được nêu tên.")

    def test_chua_co_anh_thi_noi_thang(self):
        """TC-INT-TestQcEvidence-025: Khoảng trắng bị đọc thành "hỏng", phải nói rõ là chưa
        có.
        """
        receipt = self._receive(self._make_receipt(qty=100.0), qty=100.0)
        qc = self._qc_picking(receipt)
        move = qc.move_ids.filtered(lambda m: m.product_id == self.material)[:1]

        self.assertIn("Chưa có ảnh", move.dlm_evidence_gallery or "")

    def test_so_luong_hien_dung_o_moi_chang(self):
        """TC-INT-TestQcEvidence-026: Hộp ảnh trên phiếu trả từng hiện "Số loại 0".

        Một con số SAI đặt ngay cạnh bằng chứng là chỗ tệ nhất để đặt nó: người đọc hoặc
        tin nhầm, hoặc mất tin vào cả tấm ảnh bên cạnh.
        """
        _receipt, qc, move, _anh = self._qc_co_hang_loai(dat=92.0, loai=8.0)
        self.assertEqual(move.dlm_reject_qty_shown, 8.0,
                         "Ở phiếu kiểm: số bị loại.")

        qc.action_dlm_validate_qc()
        dong_tra = qc._dlm_vendor_returns().move_ids.filtered(
            lambda m: m.product_id == self.material)
        self.assertEqual(dong_tra.dlm_reject_qty_shown, 8.0,
                         "Ở phiếu trả: nhu cầu của dòng CHÍNH LÀ số hàng lỗi.")

    def test_cot_lo_tren_phieu_tra_khong_de_trang(self):
        """TC-INT-TestQcEvidence-027: Cột Lô của phiếu trả phải có số NGAY khi còn nháp.

        `lot_ids` chỉ có sau khi giữ chỗ, mà nháp mới là trạng thái người ta nhìn màn
        này nhiều nhất. Để trắng thì vừa phí một cột, vừa lệch với biên bản PDF — tờ
        giấy in ra số lô đầy đủ còn màn hình thì không.
        """
        tra = self._phieu_tra()
        self.assertEqual(tra.state, "draft")
        dong = tra.move_ids.filtered(lambda m: m.product_id == self.material)

        self.assertFalse(dong.lot_ids, "Ca test phải chạy ở trạng thái CHƯA giữ chỗ.")
        self.assertTrue(dong.dlm_return_lot_display.startswith("LO/"),
                        "Cột Lô trên màn phải khớp với cột Lô trên biên bản.")
        self.assertEqual(
            dong.dlm_return_lot_display,
            tra._dlm_reject_report_rows()[0]["lots"],
            "Màn hình và biên bản PDF phải đọc cùng một nguồn.")

    # ── Giao diện ───────────────────────────────────────────────────────────
    def test_nut_bang_chung_co_nhan_chu(self):
        """TC-INT-TestQcEvidence-028: Cột nút trong list Odoo có <th> rỗng
        (list_renderer.xml).

        Icon máy ảnh trần đứng dưới tiêu đề trắng thì không hover thì không ai đoán được
        nó làm gì — mà đây là nút cho một tính năng mới, chưa ai có thói quen. Nhãn chữ
        là thứ duy nhất nói ra được điều đó.
        """
        for xml_id in ("dl_inventory.view_dl_qc_form",
                       "dl_inventory.view_dl_vendor_return_form",
                       "dl_inventory.view_dl_to_scrap_form"):
            arch = self.env.ref(xml_id).get_combined_arch()
            self.assertIn("action_dlm_open_evidence", arch)
            vi_tri = arch.index("action_dlm_open_evidence")
            self.assertIn(
                'string="Bằng chứng"', arch[vi_tri:vi_tri + 400],
                "%s: nút bằng chứng thiếu nhãn chữ, chỉ còn icon." % xml_id)

    def test_hop_anh_khong_lo_gia(self):
        """TC-INT-TestQcEvidence-029: §8.3 — Thủ kho đếm hàng, không định giá. Hộp ảnh cũng
        vậy.
        """
        view = self.env.ref("dl_inventory.view_dl_move_evidence_form")
        for token in ("standard_price", "price_unit", "value", "amount"):
            self.assertNotIn(
                token, view.arch,
                "Hộp ảnh bằng chứng không được có ô liên quan tới giá ('%s')."
                % token)

    def test_nut_mo_hop_anh_tro_dung_view(self):
        """TC-INT-TestQcEvidence-030: Nút trên dòng phải mở đúng hộp ảnh, không rơi về form
        stock.move gốc.

        Rơi về form native là bày nguyên bộ ô vị trí/số lượng/giá cho thủ kho sửa tay —
        cùng loại rò rỉ mà RS-02 dựng bảng `_DLM_FORM_BY_KIND` để bịt.
        """
        _receipt, _qc, move, _anh = self._qc_co_hang_loai()
        action = move.action_dlm_open_evidence()

        self.assertEqual(action["res_model"], "stock.move")
        self.assertEqual(action["res_id"], move.id)
        self.assertEqual(action["target"], "new")
        self.assertEqual(
            action["views"][0][0],
            self.env.ref("dl_inventory.view_dl_move_evidence_form").id)

    # ── Nhóm 6: gửi biên bản cho NCC bằng email ─────────────────────────────
    def test_gui_bien_ban_dinh_san_pdf_va_dung_ncc(self):
        """TC-INT-TestQcEvidence-031: Thư mở ra phải đã có biên bản và đã điền đúng NCC.

        Đỏ = Mua hàng vẫn phải tải PDF rồi gõ tay địa chỉ — đúng việc thủ công mà K17
        sinh ra để thay thế, và gõ tay là gửi nhầm nhà cung cấp.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        tra.partner_id.email = "ncc.bienban@test.local"

        action = tra.action_dlm_email_reject_report()

        ctx = action["context"]
        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(ctx["default_partner_ids"],
                         [(6, 0, tra.partner_id.ids)])
        dinh_kem = self.env["ir.attachment"].browse(
            ctx["default_attachment_ids"][0][2])
        self.assertEqual(dinh_kem.mimetype, "application/pdf")
        self.assertIn("Bien_ban_hang_khong_dat", dinh_kem.name)
        # Neo vào chính phiếu: ba tháng sau còn tra được đã đưa NCC cái gì.
        self.assertEqual(dinh_kem.res_model, "stock.picking")
        self.assertEqual(dinh_kem.res_id, tra.id)

    def test_thu_gui_ncc_khong_co_gia(self):
        """TC-INT-TestQcEvidence-032: Cùng luật với tờ biên bản: thư nói về hàng, không
        phải tiền.

        Số tiền giảm trừ là kết quả đàm phán. Viết ra trước là tự chốt mức hộ NCC — sửa
        "cho đầy đủ" ở thư mà quên luật này là hỏng đúng chỗ tờ giấy đã cẩn thận tránh.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        tra.partner_id.email = "ncc.bienban@test.local"

        body = tra.action_dlm_email_reject_report()["context"]["default_body"]

        for tu_tien in ("giảm trừ", "bồi thường", "VNĐ", "₫"):
            self.assertNotIn(tu_tien, body)

    def test_thu_kho_khong_gui_duoc_bien_ban_cho_ncc(self):
        """TC-INT-TestQcEvidence-033: IN thì thủ kho làm được, gửi thì không — quan hệ với
        NCC là của Mua hàng, cùng lằn kiểm soát chéo của đơn mua.

        Lá chắn phải ở tầng server: `groups=` trên view chỉ giấu nút, RPC vẫn gọi thẳng
        được. `env.su` của TransactionCase bỏ qua ACL nên phải chạy bằng vai trò thật.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        tra.partner_id.email = "ncc.bienban@test.local"
        thu_kho = self.env["res.users"].create({
            "name": "Thủ kho (gửi biên bản)", "login": "thukho_send_bb_test",
            "email": "thukho.sendbb@test.local",
            "groups_id": [(6, 0, [
                self.env.ref("dl_base.dl_group_warehouse").id])],
        })
        self.env.invalidate_all()

        with self.assertRaises(UserError):
            tra.with_user(thu_kho).action_dlm_email_reject_report()

        # Nhưng IN thì vẫn phải được — nút kia cố ý không khoá vai trò.
        tra.with_user(thu_kho).action_dlm_print_reject_report()

    def test_ncc_chua_co_email_thi_chan_som(self):
        """TC-INT-TestQcEvidence-034: Chặn trước khi mở trình soạn thư: composer mở ra với
        ô người nhận rỗng thì người dùng bấm Gửi rồi tưởng đã gửi — im lặng.
        """
        tra = self._phieu_tra(anh=self._anh_that())
        tra.partner_id.email = False

        with self.assertRaises(UserError):
            tra.action_dlm_email_reject_report()
