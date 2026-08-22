# -*- coding: utf-8 -*-
"""L2 Integration test (TransactionCase, DB thật) cho dl.rbac.feature, service quản lý
vai trò/phân quyền cho màn "Phân quyền" (dl_base/models/dl_rbac.py).
Sheet nguồn: DlRbacFeature trong Report_5_1_UnitTests_L1.xlsx."""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_base")
class TestDlRbacFeature(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rbac = cls.env["dl.rbac.feature"]
        cls.admin_user = cls.env["res.users"].create({
            "name": "Admin test RBAC", "login": "admin_rbac_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        cls.non_admin_user = cls.env["res.users"].create({
            "name": "Sales test RBAC", "login": "sales_rbac_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_non_admin_blocked_from_rbac_write(self):
        """TC-UNIT-DlRbacFeature-001: user không thuộc nhóm admin gọi create_role
        thì bị chặn bằng AccessError."""
        with self.assertRaises(AccessError):
            self.Rbac.with_user(self.non_admin_user).create_role("Vai trò test 001")

    def test_create_role_empty_name_raises(self):
        """TC-UNIT-DlRbacFeature-002: admin tạo vai trò với tên chỉ toàn khoảng
        trắng thì báo lỗi ValidationError."""
        with self.assertRaises(ValidationError):
            self.Rbac.with_user(self.admin_user).create_role("   ")

    def test_create_role_duplicate_name_raises(self):
        """TC-UNIT-DlRbacFeature-003: tạo vai trò trùng tên (so sánh ilike, không
        phân biệt hoa/thường) với vai trò đã có thì báo lỗi ValidationError."""
        Rbac = self.Rbac.with_user(self.admin_user)
        Rbac.create_role("Vai trò trùng tên RBAC003")
        with self.assertRaises(ValidationError):
            Rbac.create_role("vai trò trùng tên rbac003")  # so ilike, không phân biệt hoa/thường

    def test_create_role_happy_creates_group(self):
        """TC-UNIT-DlRbacFeature-004: tạo vai trò hợp lệ kèm ghi chú thì phải tạo
        được res.groups tương ứng, giữ đúng comment và tự động implied nhóm
        base.group_user."""
        Rbac = self.Rbac.with_user(self.admin_user)
        group_id = Rbac.create_role("Vai trò test 004", comment="Ghi chú test")
        group = self.env["res.groups"].sudo().browse(group_id)
        self.assertTrue(group.exists())
        self.assertEqual(group.comment, "Ghi chú test")
        self.assertIn(self.env.ref("base.group_user"), group.implied_ids)

    def test_delete_role_system_role_blocked(self):
        """TC-UNIT-DlRbacFeature-005: vai trò do module cài (có external id) không được xoá."""
        system_group = self.env.ref("dl_base.dl_group_tech")
        with self.assertRaises(ValidationError):
            self.Rbac.with_user(self.admin_user).delete_role(system_group.id)

    def test_delete_role_admin_created_role_succeeds(self):
        """TC-UNIT-DlRbacFeature-006: xoá vai trò do admin tự tạo (không phải
        module cài) phải thành công và group tương ứng không còn tồn tại."""
        Rbac = self.Rbac.with_user(self.admin_user)
        group_id = Rbac.create_role("Vai trò xoá được 006")
        self.assertTrue(Rbac.delete_role(group_id))
        self.assertFalse(self.env["res.groups"].sudo().browse(group_id).exists())

    def test_set_operation_enable_then_disable_resyncs_membership(self):
        """TC-UNIT-DlRbacFeature-007: bật một operation-group cho vai trò phải
        thêm group vào implied_ids và cộng thành viên vai trò vào op-group; tắt
        lại phải gỡ implied_ids và thu hồi membership thật sự, không chỉ gỡ implied."""
        Rbac = self.Rbac.with_user(self.admin_user)
        role_id = Rbac.create_role("Vai trò cho op-group 007")
        role = self.env["res.groups"].sudo().browse(role_id)
        op_group = self.env["res.groups"].sudo().create({
            "name": "Op-group test 007 (kỹ thuật)",
        })
        member = self.env["res.users"].create({
            "name": "Thành viên vai trò 007", "login": "member_rbac_007",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, role_id])],
        })

        Rbac.set_operation(role_id, op_group.id, True)
        self.assertIn(op_group, role.implied_ids)
        self.assertIn(member, op_group.users,
                       "Thành viên vai trò phải được cộng vào op-group sau resync")

        Rbac.set_operation(role_id, op_group.id, False)
        self.assertNotIn(op_group, role.implied_ids)
        self.assertNotIn(member, op_group.users,
                          "Gỡ implied phải thu hồi membership thật sự, không chỉ gỡ implied_ids")
