# -*- coding: utf-8 -*-
"""Integration test (L2, TransactionCase, DB thật) cho quyền truy cập màn "Đơn vị
tính" (dl_config/views/uom_views.xml, action_dl_uom, menu_dl_config_uom).

Màn này dùng thẳng model chuẩn Odoo `uom.uom`/`uom.category` — dl_config chỉ
thêm view + ACL riêng (dl_config/security/ir.model.access.csv), không có model
hay logic Python riêng, nên trước giờ chưa có test nào canh quyền theo vai trò
cho hai model này ở tầng dl_config.

Lưu ý quan trọng khi đọc test này: module `uom` gốc của Odoo đã tự cấp quyền
ĐỌC uom.uom/uom.category cho MỌI user nội bộ (access_uom_uom_user/
access_uom_category_user → base.group_user, perm read=1). dl_config chỉ thêm
2 dòng ACL cấp quyền GHI đầy đủ (create/write/unlink) cho CEO và Admin/IT. Vì
vậy một vai trò không có dòng ACL riêng (ví dụ Thủ kho) vẫn ĐỌC được đơn vị
tính — chỉ bị chặn ở thao tác GHI.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_config")
class TestDlUomScreenAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Uom = cls.env["uom.uom"]
        cls.UomCategory = cls.env["uom.category"]
        cls.ceo_user = cls.env["res.users"].create({
            "name": "CEO test UoM", "login": "ceo_uom_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_ceo").id,
            ])],
        })
        cls.admin_user = cls.env["res.users"].create({
            "name": "Admin test UoM", "login": "admin_uom_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        # Thủ kho: vai trò cố ý không có dòng ACL riêng nào cho uom.uom/
        # uom.category ở dl_config, chỉ hưởng quyền đọc mặc định từ module
        # uom gốc.
        cls.warehouse_user = cls.env["res.users"].create({
            "name": "Thủ kho test UoM", "login": "warehouse_uom_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_warehouse").id,
            ])],
        })

    def test_ceo_and_admin_can_crud_uom_category(self):
        """TC-INT-DlUomScreenAccess-001: CEO và Admin/IT tạo, sửa, xóa được
        uom.category (nhóm đơn vị tính) nhờ dòng ACL access_dl_uom_categ_ceo/
        access_dl_uom_categ_admin.
        """
        for user in (self.ceo_user, self.admin_user):
            category = self.UomCategory.with_user(user).create({
                "name": "Nhóm test %s" % user.login,
            })
            category.write({"name": "Nhóm test %s đã sửa" % user.login})
            category.unlink()

    def test_ceo_and_admin_can_crud_uom(self):
        """TC-INT-DlUomScreenAccess-002: CEO và Admin/IT tạo, sửa, xóa được
        uom.uom (đơn vị tính) nhờ dòng ACL access_dl_uom_ceo/access_dl_uom_admin.
        """
        for user in (self.ceo_user, self.admin_user):
            category = self.UomCategory.create({
                "name": "Nhóm cho đơn vị test %s" % user.login,
            })
            uom = self.Uom.with_user(user).create({
                "name": "Đơn vị test %s" % user.login,
                "category_id": category.id,
                "uom_type": "reference",
                "factor": 1.0,
            })
            uom.write({"rounding": 0.5})
            uom.unlink()

    def test_role_without_acl_can_read_but_not_write_uom(self):
        """TC-INT-DlUomScreenAccess-003: Thủ kho (vai trò không có dòng ACL
        ghi riêng cho uom.uom/uom.category) vẫn đọc được đơn vị tính/nhóm đơn
        vị nhờ ACL đọc mặc định của module uom gốc, nhưng bị chặn AccessError
        khi tạo, sửa hoặc xóa — vì dl_config không cấp quyền ghi cho vai trò
        này.
        """
        category = self.UomCategory.create({"name": "Nhóm test 003"})
        uom = self.Uom.create({
            "name": "Đơn vị test 003",
            "category_id": category.id,
            "uom_type": "reference",
            "factor": 1.0,
        })

        # Đọc được — kế thừa ACL đọc mặc định của module uom gốc.
        read_uom = self.Uom.with_user(self.warehouse_user).browse(uom.id)
        self.assertEqual(read_uom.name, "Đơn vị test 003")
        read_category = self.UomCategory.with_user(
            self.warehouse_user).browse(category.id)
        self.assertEqual(read_category.name, "Nhóm test 003")

        # Không được tạo/sửa/xóa.
        with self.assertRaises(AccessError):
            self.Uom.with_user(self.warehouse_user).create({
                "name": "Đơn vị bị chặn 003",
                "category_id": category.id,
                "uom_type": "reference",
                "factor": 1.0,
            })
        with self.assertRaises(AccessError):
            self.Uom.with_user(self.warehouse_user).browse(uom.id).write(
                {"rounding": 0.5})
        with self.assertRaises(AccessError):
            self.Uom.with_user(self.warehouse_user).browse(uom.id).unlink()
        with self.assertRaises(AccessError):
            self.UomCategory.with_user(self.warehouse_user).create(
                {"name": "Nhóm bị chặn 003"})
