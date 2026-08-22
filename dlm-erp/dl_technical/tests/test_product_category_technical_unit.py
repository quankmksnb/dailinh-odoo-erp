# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho phần mở rộng product.category ở
dl_technical (class ProductCategoryTechnical). Sheet nguồn:
ProductCategoryTechnical.

Chỉ test _dlm_check_bom_template_id() (LK-04/§3.1-L2): BOM mẫu mặc định của
nhóm phải cùng nhóm và đã duyệt (confirmed/locked). Các method khác
(_dlm_parametric_generic_ids) đụng self.env["dl.bom.template"].search() thật
nên là L2, không test ở đây."""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_product import ProductCategoryTechnical


class TestDlmCheckBomTemplateId(unittest.TestCase):
    def test_template_of_other_category_raises(self):
        """TC-UNIT-ProductCategoryTechnical-001: BOM mẫu mặc định thuộc nhóm
        khác thì _dlm_check_bom_template_id() báo lỗi ValidationError."""
        other_categ = SimpleNamespace(display_name="Nhóm khác")
        tmpl = SimpleNamespace(product_category_id=other_categ, status="confirmed", name="Mẫu A")
        rec = SimpleNamespace(bom_template_id=tmpl, display_name="Nhóm Bàn")
        with self.assertRaises(ValidationError):
            ProductCategoryTechnical._dlm_check_bom_template_id([rec])

    def test_template_not_approved_raises(self):
        """BOM mẫu cùng nhóm nhưng chưa duyệt (status='draft') thì cũng báo
        lỗi ValidationError."""
        tmpl = SimpleNamespace(status="draft", name="Mẫu A")
        rec = SimpleNamespace(bom_template_id=tmpl, display_name="Nhóm Bàn")
        tmpl.product_category_id = rec  # cùng nhóm
        with self.assertRaises(ValidationError):
            ProductCategoryTechnical._dlm_check_bom_template_id([rec])

    def test_valid_template_passes(self):
        """BOM mẫu cùng nhóm và đã duyệt (confirmed) thì không báo lỗi."""
        tmpl = SimpleNamespace(status="confirmed", name="Mẫu A")
        rec = SimpleNamespace(bom_template_id=tmpl, display_name="Nhóm Bàn")
        tmpl.product_category_id = rec  # cùng nhóm
        ProductCategoryTechnical._dlm_check_bom_template_id([rec])  # không raise

    def test_no_template_passes(self):
        """Nhóm chưa gán BOM mẫu mặc định (bom_template_id rỗng) thì bỏ qua
        kiểm tra."""
        rec = SimpleNamespace(bom_template_id=None, display_name="Nhóm Bàn")
        ProductCategoryTechnical._dlm_check_bom_template_id([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
