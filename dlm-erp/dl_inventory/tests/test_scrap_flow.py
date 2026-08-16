# -*- coding: utf-8 -*-
"""K7: Phế liệu, cân thực tế, bán, và đối chiếu với dự toán.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §7, §11.8, §12.1 (tiêu chí verify K7).

Bất biến quan trọng nhất không phải là con số tồn, mà là dải chú thích luôn
hiện: giá trị phế liệu đã được trừ vào giá vốn lúc báo giá, nên tiền bán phế
liệu là thu về khoản đã tính trước. Thiếu câu đó, người đọc dễ cộng nhầm vào
lãi và tính hai lần (§7.2).
"""

from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestScrapFlow(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loc_scrap = cls.env.ref("dl_inventory.stock_location_xuong_pl")
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        # Phế liệu không theo lô (§3.4): vụn gom từ nhiều lô trong cùng thùng.
        cls.scrap = cls.env["product.product"].create({
            "name": "Phế liệu thép (test)",
            "product_kind": "material",
            "uom_id": cls.uom_kg.id,
            "uom_po_id": cls.uom_kg.id,
        })
        cls.scrap.tracking = "none"
        cls.scrap.sudo().list_price = 8000.0
        cls.scrap_buyer = cls.env["res.partner"].create({
            "name": "Vựa ve chai (test)"})

    def _weigh_in(self, qty):
        """Cân thực tế: đường duy nhất để phế liệu vào kho ở B1 (§7.3)."""
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.scrap.id,
            "location_id": self.loc_scrap.id,
            "inventory_quantity": qty,
        })
        quant.action_apply_inventory()
        return quant

    def test_can_thuc_te_50kg_ban_het_thi_ton_ve_0(self):
        """Tiêu chí verify K7: nhập tay 50kg, bán 50kg, tồn phải về 0."""
        self._weigh_in(50.0)
        self.assertEqual(self._qty_at(self.loc_scrap, self.scrap), 50.0)

        quants = self.env["stock.quant"].search([
            ("location_id", "=", self.loc_scrap.id),
            ("product_id", "=", self.scrap.id),
        ])
        action = quants.action_dlm_sell_scrap()
        picking = self.env["stock.picking"].browse(action["res_id"])

        self.assertEqual(picking.state, "draft",
                         "Phiếu bán phế liệu để nháp: giá và bên mua còn phải "
                         "thoả thuận.")
        self.assertEqual(picking.move_ids.product_uom_qty, 50.0)
        self.assertEqual(picking.location_id, self.loc_scrap)

        picking.partner_id = self.scrap_buyer
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 50.0
        picking.move_ids.picked = True
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        self.assertEqual(self._qty_at(self.loc_scrap, self.scrap), 0.0)

    def test_khong_chon_dong_nao_thi_bao_loi_ro(self):
        """Bấm Bán phế liệu khi chưa chọn dòng thì phải nói rõ cần làm gì."""
        from odoo.exceptions import UserError
        with self.assertRaises(UserError) as caught:
            self.env["stock.quant"].browse().action_dlm_sell_scrap()
        self.assertIn("Chọn ít nhất một dòng", str(caught.exception))

    def test_thanh_tien_bang_so_luong_nhan_don_gia(self):
        """§11.8: cột Thành tiền là thứ người dùng dùng để mặc cả với bên mua.

        Đơn giá ở đây là giá bán phế liệu, không phải giá vốn, nên không vi
        phạm §8.3 ("Thủ kho không thấy giá").
        """
        quant = self._weigh_in(12.5)
        self.assertEqual(quant.dlm_scrap_unit_price, 8000.0)
        self.assertEqual(quant.dlm_scrap_value, 100000.0)

    def test_dai_chu_thich_luon_hien_va_khong_dong_duoc(self):
        """🔴 §7.2: dải "không phải lợi nhuận tăng thêm" là bắt buộc.

        Kiểm hai điều: route trả về nội dung, và nội dung không mang
        `data-o-hide-banner` (thứ duy nhất làm banner của Odoo đóng được).
        """
        from odoo.addons.dl_inventory.controllers.scrap_banner import (
            dlm_scrap_banner_html)

        html = dlm_scrap_banner_html()
        self.assertIn("không phải lợi nhuận tăng thêm", html)
        self.assertNotIn("data-o-hide-banner", html)

        arch = self.env.ref("dl_inventory.view_dl_scrap_quant_tree").arch
        self.assertIn("/dl_inventory/scrap_banner", arch,
                      "Màn Phế liệu phải gắn dải chú thích.")

    # 🔴 K16 — hai test của màn "Đối chiếu thu hồi" đã gỡ cùng chính màn đó:
    # bỏ cách tính % thu hồi thì không còn DỰ TOÁN để đối chiếu với số cân được.
    # Vòng phản hồi thay thế nằm ở test_workshop_batch (định mức vs thực cấp).
