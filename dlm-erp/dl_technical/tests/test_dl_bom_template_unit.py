# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.template. Sheet nguồn:
DlBomTemplate.

Chỉ test _check_generic_product_category(): nhóm của mẫu phải bằng nhóm của
sản phẩm dùng chung. Các method khác (generate_instance, _version_domain,
_dlm_validate_param_values...) đụng self.env/self.search thật nên là L2,
không test ở đây."""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_bom_template import DlBomTemplate


class TestCheckGenericProductCategory(unittest.TestCase):
    def test_mismatched_category_raises(self):
        """TC-UNIT-DlBomTemplate-001: sản phẩm dùng chung thuộc nhóm khác
        nhóm của mẫu thì _check_generic_product_category() báo lỗi
        ValidationError."""
        categ_a = SimpleNamespace(display_name="Nhóm A")
        categ_b = SimpleNamespace(display_name="Nhóm B")
        product = SimpleNamespace(categ_id=categ_a, display_name="Bàn thép")
        rec = SimpleNamespace(generic_product_id=product, product_category_id=categ_b)
        with self.assertRaises(ValidationError):
            DlBomTemplate._check_generic_product_category([rec])

    def test_matching_category_passes(self):
        """Nhóm của sản phẩm dùng chung khớp nhóm của mẫu thì không báo lỗi."""
        categ_a = SimpleNamespace(display_name="Nhóm A")
        product = SimpleNamespace(categ_id=categ_a, display_name="Bàn thép")
        rec = SimpleNamespace(generic_product_id=product, product_category_id=categ_a)
        DlBomTemplate._check_generic_product_category([rec])  # không raise

    def test_no_generic_product_passes(self):
        """Mẫu chưa gán sản phẩm dùng chung (mẫu chép tay) thì không kiểm tra."""
        rec = SimpleNamespace(
            generic_product_id=None,
            product_category_id=SimpleNamespace(display_name="Nhóm A"))
        DlBomTemplate._check_generic_product_category([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
