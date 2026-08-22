# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.drawing. Sheet nguồn: DlDrawing.

Chỉ test _check_product_kind() (LK-05/LX-07): bản vẽ kỹ thuật chỉ gắn được
cho sản phẩm gia công (manufactured) / bán thành phẩm (material_processed).
Các action_confirm/action_archive/... đụng self.write/self.search thật nên là
L2, không test ở đây."""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_drawing import DlDrawing


class TestCheckProductKind(unittest.TestCase):
    def test_material_kind_raises(self):
        """TC-UNIT-DlDrawing-001: sản phẩm là vật tư thô (product_kind=material)
        thì _check_product_kind() báo lỗi ValidationError."""
        product = SimpleNamespace(product_kind="material", display_name="Tôn 1mm")
        rec = SimpleNamespace(product_id=product)
        with self.assertRaises(ValidationError):
            DlDrawing._check_product_kind([rec])

    def test_manufactured_kind_passes(self):
        """Sản phẩm gia công (manufactured) thì không báo lỗi."""
        product = SimpleNamespace(product_kind="manufactured", display_name="Bàn hợp kim")
        rec = SimpleNamespace(product_id=product)
        DlDrawing._check_product_kind([rec])  # không raise

    def test_material_processed_kind_passes(self):
        """Bán thành phẩm (material_processed) thì không báo lỗi."""
        product = SimpleNamespace(product_kind="material_processed", display_name="Khung bàn")
        rec = SimpleNamespace(product_id=product)
        DlDrawing._check_product_kind([rec])  # không raise

    def test_no_product_passes(self):
        """Chưa chọn sản phẩm (product_id rỗng) thì bỏ qua kiểm tra."""
        rec = SimpleNamespace(product_id=None)
        DlDrawing._check_product_kind([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
