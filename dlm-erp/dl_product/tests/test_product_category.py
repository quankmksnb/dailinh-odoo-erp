# -*- coding: utf-8 -*-
"""L2 (TransactionCase, chạm DB thật) cho product.category (dl_product).
Sheet nguồn: TestProductCategory.

Hai constraint ở dl_product/models/dl_product_category.py:
- _dlm_check_archive_active_products(): chặn archive nhóm còn SP đang hoạt động.
- _check_branch_products(): chặn kéo nhóm sang nhánh khác khi trong nhóm đã có
  sản phẩm sai loại (nhánh Thành phẩm chỉ chứa gia công/thương mại, nhánh Vật
  tư chỉ chứa vật tư/bán thành phẩm).
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_product")
class TestProductCategory(TransactionCase):

    def test_archive_blocked_when_active_product_inside(self):
        """TC-INT-TestProductCategory-001: nhóm còn 1 sản phẩm
        dlm_lifecycle_state='active' bên trong (kể cả nhóm con) thì không
        archive (write active=False) được — phải báo ValidationError kèm tên
        nhóm và số lượng sản phẩm đang hoạt động."""
        categ = self.env["product.category"].create({
            "name": "Nhóm test lưu trữ (test cat 001)"})
        self.env["product.product"].create({
            "name": "SP đang hoạt động (test cat 001)",
            "categ_id": categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "active",
        })

        with self.assertRaises(ValidationError) as err:
            categ.write({"active": False})

        self.assertIn(categ.display_name, str(err.exception))
        self.assertIn("đang hoạt", str(err.exception))

    def test_archive_allowed_when_no_active_product(self):
        """Đối chứng: nhóm không còn sản phẩm active (SP đã Ngừng sử dụng) thì
        archive được bình thường, không raise."""
        categ = self.env["product.category"].create({
            "name": "Nhóm test lưu trữ OK (test cat 001b)"})
        product = self.env["product.product"].create({
            "name": "SP đã ngừng (test cat 001b)",
            "categ_id": categ.id,
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "obsolete",
        })

        categ.write({"active": False})

        self.assertFalse(categ.active)
        self.assertEqual(product.dlm_lifecycle_state, "obsolete")

    def test_move_category_blocked_when_wrong_kind_product_inside(self):
        """TC-INT-TestProductCategory-002: nhóm đang ở nhánh Vật tư, chứa 1
        sản phẩm product_kind='material' (đúng nhánh hiện tại). Kéo nhóm sang
        làm con của gốc Thành phẩm (đổi nhánh sang 'finished') thì phải bị
        chặn, vì SP vật tư bên trong trở thành sai loại cho nhánh mới —
        ValidationError phải liệt kê đúng sản phẩm sai loại."""
        material_root = self.env.ref("dl_product.categ_root_material")
        finished_root = self.env.ref("dl_product.categ_root_finished")

        categ = self.env["product.category"].create({
            "name": "Nhóm test đổi nhánh (test cat 002)",
            "parent_id": material_root.id,
        })
        self.assertEqual(categ.dl_branch, "material", "Tiền đề: nhóm đang ở nhánh Vật tư")

        product = self.env["product.product"].create({
            "name": "Vật tư test (test cat 002)",
            "categ_id": categ.id,
            "product_kind": "material",
        })

        with self.assertRaises(ValidationError) as err:
            categ.write({"parent_id": finished_root.id})

        self.assertIn(product.display_name, str(err.exception))

    def test_move_category_allowed_when_kind_matches_new_branch(self):
        """Đối chứng: kéo nhóm (chỉ chứa SP đúng loại cho nhánh MỚI) sang nhánh
        khác thì không bị chặn."""
        material_root = self.env.ref("dl_product.categ_root_material")
        finished_root = self.env.ref("dl_product.categ_root_finished")

        categ = self.env["product.category"].create({
            "name": "Nhóm test đổi nhánh OK (test cat 002b)",
            "parent_id": material_root.id,
        })
        # Không có sản phẩm nào bên trong nhóm -> không có gì để sai loại.
        categ.write({"parent_id": finished_root.id})

        self.assertEqual(categ.dl_branch, "finished")
