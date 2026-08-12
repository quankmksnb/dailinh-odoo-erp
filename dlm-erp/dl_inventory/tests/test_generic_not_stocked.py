# -*- coding: utf-8 -*-
"""K3 — Sản phẩm dùng chung (generic) KHÔNG được tồn kho.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §3.5 (ngoại lệ cho LK-14).

Vì sao đây là lỗi NGHIỆP VỤ chứ không phải báo cáo bẩn: Odoo giữ hàng (reserve)
theo `product_id`, KHÔNG theo kích thước. Nếu "Bàn thép" là storable và trong
kho có 5 cái gồm nhiều cỡ, một đơn đặt 1200×800 sẽ được Odoo giữ nhầm một cái
1000×600 rồi báo "đủ hàng" — tới lúc giao mới lộ. Không chặn được bằng cấu hình.
"""

from odoo.tests.common import tagged

from .common import DlInventoryCase


@tagged("post_install", "-at_install", "dl_inventory")
class TestGenericNotStocked(DlInventoryCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({"name": "Bàn thép (test)"})
        cls.generic = cls.env["product.product"].create({
            "name": "Bàn thép khung hộp (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
        })

    def test_gan_lam_generic_thi_thanh_consu(self):
        """§3.5 — Vừa gán làm SP dùng chung của BOM mẫu ⇒ hết tồn kho được."""
        self.assertEqual(
            self.generic.detailed_type, "product",
            "Bối cảnh: SP gia công mặc định storable (LK-14).")

        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép (test)",
            "product_category_id": self.categ.id,
            "generic_product_id": self.generic.id,
        })

        self.generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(
            self.generic.detailed_type, "consu",
            "SP dùng chung phải là 'consu' — nếu storable, Odoo sẽ giữ nhầm "
            "hàng khác kích thước rồi báo đủ hàng.")

    def test_gan_generic_bang_write_cung_thanh_consu(self):
        """§3.5 — Cùng luật khi gán SAU (sửa BOM mẫu đã có), không chỉ lúc tạo."""
        template = self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép rỗng (test)",
            "product_category_id": self.categ.id,
        })
        template.generic_product_id = self.generic

        self.generic.invalidate_recordset(["detailed_type"])
        self.assertEqual(self.generic.detailed_type, "consu")

    def test_generic_khong_tao_duoc_ton_kho(self):
        """§3.5 — Hệ quả cuối cùng: generic không bao giờ có mặt trong kho.

        Đây mới là điều người dùng thấy: màn Tồn kho sạch, không có hàng trăm mã
        tồn 0 vĩnh viễn.
        """
        self.env["dl.bom.template"].create({
            "name": "Mẫu bàn thép (test 2)",
            "product_category_id": self.categ.id,
            "generic_product_id": self.generic.id,
        })
        self.generic.invalidate_recordset(["detailed_type", "is_storable"]
                                          if "is_storable" in self.generic._fields
                                          else ["detailed_type"])

        quants = self.env["stock.quant"].search(
            [("product_id", "=", self.generic.id)])
        self.assertFalse(quants, "SP dùng chung không được có tồn kho.")
