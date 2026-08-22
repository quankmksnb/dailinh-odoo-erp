# -*- coding: utf-8 -*-
"""L2 (TransactionCase, chạm DB thật) cho product.product._check_dlm_name_duplicate()
(dl_technical/models/dl_product.py). Sheet nguồn: TestProductNameDuplicate.

Constraint chặn cứng SP gia công/BTP trùng hệt tên (đã chuẩn hoá) với SP chính
thức đã có, ở mọi đường tạo (form/RPC/import). SP tạm từ RFQ
(is_rfq_provisional=True) được miễn khi còn tạm.
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical")
class TestProductNameDuplicate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env["product.category"].create({
            "name": "Nhóm test trùng tên (test dup 001)"})
        cls.existing = cls.env["product.product"].create({
            "name": "Bàn học sinh",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })

    def test_official_duplicate_name_blocked(self):
        """TC-INT-TestProductNameDuplicate-001: đã có SP gia công chính thức
        tên 'Bàn học sinh'; tạo SP mới cùng product_kind, tên chuẩn hoá trùng
        hệt (khác hoa/thường + thừa khoảng trắng), is_rfq_provisional=False ->
        ValidationError chứa 'Đã tồn tại sản phẩm cùng tên' và tên nhóm."""
        with self.assertRaises(ValidationError) as err:
            self.env["product.product"].create({
                "name": "  BÀN học SINH  ",
                "categ_id": self.categ.id,
                "product_kind": "manufactured",
                "is_rfq_provisional": False,
            })

        message = str(err.exception)
        self.assertIn("Đã tồn tại sản phẩm cùng tên", message)
        self.assertIn(self.categ.display_name, message)

    def test_provisional_duplicate_name_is_exempt(self):
        """Đối chứng: SP tạm từ RFQ (is_rfq_provisional=True) được miễn kiểm
        tra trùng tên khi còn tạm — không raise dù tên trùng hệt."""
        provisional = self.env["product.product"].create({
            "name": "Bàn học sinh",
            "categ_id": self.categ.id,
            "product_kind": "manufactured",
            "is_rfq_provisional": True,
            "dlm_lifecycle_state": "draft",
        })

        self.assertTrue(provisional.is_rfq_provisional)
        self.assertEqual(provisional.name, "Bàn học sinh")

    def test_official_duplicate_material_processed_also_blocked(self):
        """Constraint áp dụng cho cả bán thành phẩm (material_processed), không
        chỉ SP gia công."""
        semi = self.env.ref("dl_product.categ_root_material", raise_if_not_found=False)
        categ = semi or self.categ
        existing_semi = self.env["product.product"].create({
            "name": "Tấm thép đã cắt (test dup 001c)",
            "categ_id": categ.id,
            "product_kind": "material_processed",
            "dlm_lifecycle_state": "active",
        })

        with self.assertRaises(ValidationError):
            self.env["product.product"].create({
                "name": "tấm thép đã cắt (test dup 001c)",
                "categ_id": categ.id,
                "product_kind": "material_processed",
                "is_rfq_provisional": False,
            })

        self.assertTrue(existing_semi)
