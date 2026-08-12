# -*- coding: utf-8 -*-
"""RS-06, RS-07, RS-11 — Ca ngoại lệ: chặn đúng chỗ, báo bằng tiếng Việt.

Rà soát: docs/Ra_soat_phan_he_kho_2026-08-12.md

Nguyên tắc đã chốt (memory `rfq-sales-hard-constrains-ux-branch`): ràng buộc
**sửa-được-trên-form** phải báo INLINE — dải đỏ + ẩn nút, không bắn modal. Guard
server chỉ là lưới cuối cho đường RPC.

Ca đắt nhất trong file này là RS-07: kiểm kê ở khu Chờ trả NCC xoá đúng số hàng
mà phiếu trả (nháp) đang tham chiếu — mất bằng chứng khiếu nại NCC, không lỗi
nào nổ.
"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestQcEntryEase(DlInventoryCase):
    """RS-06 — Gõ Loại thì tự hạ Đạt."""

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
        """Chỉ can thiệp khi vượt — không được sửa số người dùng gõ vô cớ."""
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
        """Method đúng chưa đủ — client phải thật sự gọi nó khi gõ.

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
    """RS-07 — Khu quá cảnh: tồn chỉ đổi qua phiếu."""

    def test_hai_khu_qua_canh_bi_danh_dau(self):
        self.assertTrue(self.loc_qc.dlm_no_inventory,
                        "Khu Chờ kiểm phải bị cấm kiểm kê tay.")
        self.assertTrue(self.loc_tra.dlm_no_inventory,
                        "Khu Chờ trả NCC phải bị cấm kiểm kê tay.")

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
        self.assertTrue(quant, "Hàng loại phải đang nằm ở khu Chờ trả NCC.")
        quant.inventory_quantity = 0.0
        with self.assertRaises(UserError):
            quant._apply_inventory()

    def test_man_kiem_ke_khong_liet_ke_khu_qua_canh(self):
        from odoo.tools.safe_eval import safe_eval
        domain = safe_eval(
            self.env.ref("dl_inventory.action_dl_stock_inventory").domain)
        locations = self.env["stock.quant"].search(domain).location_id
        self.assertNotIn(self.loc_tra, locations)
        self.assertNotIn(self.loc_qc, locations)


@tagged("post_install", "-at_install", "dl_inventory")
class TestConfirmValidation(DlInventoryCase):
    """RS-11 — Năm ca ngoại lệ từng rơi xuống thông báo tiếng Anh."""

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
        picking = self._transfer(self.loc_kho, self.loc_kho)
        self.assertTrue(picking.dlm_blocked,
                        "Nguồn trùng đích ⇒ phải chặn xác nhận.")
        self.assertEqual(picking.dlm_banner_level, "danger")
        self.assertIn("cùng một chỗ", picking.dlm_banner_message)
        with self.assertRaises(UserError):
            picking.action_confirm()

    def test_chuyen_kho_hop_le_khong_bi_chan(self):
        picking = self._transfer(self.loc_kho, self.loc_xuong)
        self.assertFalse(picking.dlm_blocked)
        picking.action_confirm()
        self.assertNotEqual(picking.state, "draft")

    def test_dong_so_luong_0_bi_chan_va_neu_ten(self):
        picking = self._transfer(self.loc_kho, self.loc_xuong, qty=0.0)
        self.assertTrue(picking.dlm_blocked)
        self.assertIn(self.material.display_name, picking.dlm_banner_message,
                      "Dải phải nêu ĐÍCH DANH dòng sai, không nói chung chung.")
        with self.assertRaises(UserError):
            picking.action_confirm()

    def test_phieu_nhan_dong_so_luong_0_bi_chan(self):
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
