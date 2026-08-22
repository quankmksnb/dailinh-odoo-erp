# -*- coding: utf-8 -*-
"""Integration test (L2, TransactionCase, DB thật) cho res.users dlm_*,
service quản lý user cho màn "Quản lý User" (dl_config/models/res_users.py).
Sheet nguồn: ResUsers trong Report_5_2_IntegrationTests_L2.xlsx.
"""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_config")
class TestResUsers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Users = cls.env["res.users"]
        cls.admin_user = cls.Users.create({
            "name": "Admin test ResUsers", "login": "admin_resusers_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        cls.non_admin_user = cls.Users.create({
            "name": "Sales test ResUsers", "login": "sales_resusers_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_non_admin_blocked_from_dlm_methods(self):
        """TC-INT-ResUsers-001: user không thuộc nhóm admin gọi dlm_create_user() thì bị
        AccessError.
        """
        with self.assertRaises(AccessError):
            self.Users.with_user(self.non_admin_user).dlm_create_user({
                "name": "X", "login": "x_blocked_test"})

    def test_create_user_missing_name_or_login_raises(self):
        """TC-INT-ResUsers-002: dlm_create_user() thiếu name hoặc thiếu login (chuỗi rỗng)
        thì báo lỗi ValidationError.
        """
        Users = self.Users.with_user(self.admin_user)
        with self.assertRaises(ValidationError):
            Users.dlm_create_user({"name": "", "login": "a@b.com"})
        with self.assertRaises(ValidationError):
            Users.dlm_create_user({"name": "A", "login": ""})

    def test_create_user_duplicate_login_raises(self):
        """TC-INT-ResUsers-003: kể cả user đã bị khoá (active=False) vẫn tính là trùng, vì
        search dùng active_test=False.
        """
        Users = self.Users.with_user(self.admin_user)
        user_id = Users.dlm_create_user({
            "name": "Tôn test 003", "login": "ton_resusers_003@dailinh.vn"})
        self.Users.browse(user_id).sudo().active = False
        with self.assertRaises(ValidationError):
            Users.dlm_create_user({
                "name": "Tôn khác", "login": "ton_resusers_003@dailinh.vn"})

    def test_create_user_filters_non_dlm_role_groups(self):
        """TC-INT-ResUsers-004: chỉ giữ lại group thuộc category rbac dlm, group ngoài (ví
        dụ base.group_system) bị lọc bỏ để không leo thang quyền.
        """
        Users = self.Users.with_user(self.admin_user)
        dlm_role = self.env.ref("dl_base.dl_group_tech")
        non_dlm_group = self.env.ref("base.group_system")
        user_id = Users.dlm_create_user({
            "name": "User test 004", "login": "user_resusers_004@dailinh.vn",
            "role_ids": [dlm_role.id, non_dlm_group.id],
        })
        user = self.Users.sudo().browse(user_id)
        self.assertEqual(user.lang, "vi_VN")
        self.assertIn(dlm_role, user.groups_id)
        self.assertNotIn(non_dlm_group, user.groups_id)

    def test_cannot_lock_own_currently_logged_in_account(self):
        """TC-INT-ResUsers-005: admin gọi dlm_set_active() để khoá chính tài khoản đang
        đăng nhập của mình thì báo lỗi ValidationError.
        """
        Users = self.Users.with_user(self.admin_user)
        with self.assertRaises(ValidationError):
            Users.dlm_set_active(self.admin_user.id, False)

    def test_set_roles_replaces_dlm_roles_keeps_other_groups(self):
        """TC-INT-ResUsers-006: dlm_set_roles() thay role_a bằng role_b cho user thì role
        cũ bị gỡ, role mới được gán, còn group không thuộc DLM (other_group) vẫn giữ
        nguyên.
        """
        Users = self.Users.with_user(self.admin_user)
        role_a = self.env.ref("dl_base.dl_group_tech")
        role_b = self.env.ref("dl_base.dl_group_sales_manager")
        other_group = self.env.ref("base.group_partner_manager")
        target = self.Users.create({
            "name": "User test 006", "login": "user_resusers_006",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id, role_a.id, other_group.id,
            ])],
        })
        Users.dlm_set_roles(target.id, [role_b.id])
        target.invalidate_recordset()
        self.assertNotIn(role_a, target.groups_id)
        self.assertIn(role_b, target.groups_id)
        self.assertIn(other_group, target.groups_id,
                       "Group không thuộc DLM phải giữ nguyên, không bị đụng")

    def test_list_users_hides_technical_accounts(self):
        """TC-INT-ResUsers-007: dlm_list_users() không trả về các tài khoản kỹ thuật hệ
        thống (user_root, default_user) trong danh sách.
        """
        Users = self.Users.with_user(self.admin_user)
        result = Users.dlm_list_users()
        ids = {row["id"] for row in result}
        root = self.env.ref("base.user_root", raise_if_not_found=False)
        default = self.env.ref("base.default_user", raise_if_not_found=False)
        if root:
            self.assertNotIn(root.id, ids)
        if default:
            self.assertNotIn(default.id, ids)

    def test_set_backup_approver_sets_then_clears(self):
        """TC-INT-ResUsers-008: dlm_set_backup() gán backup approver cho user thì
        dl_backup_approver_id được set đúng; gọi lại với False thì xoá về rỗng.
        """
        Users = self.Users.with_user(self.admin_user)
        target = self.Users.create({
            "name": "User test 008", "login": "user_resusers_008"})
        backup = self.Users.create({
            "name": "Backup test 008", "login": "backup_resusers_008"})
        Users.dlm_set_backup(target.id, backup.id)
        self.assertEqual(target.dl_backup_approver_id, backup)
        Users.dlm_set_backup(target.id, False)
        target.invalidate_recordset()
        self.assertFalse(target.dl_backup_approver_id)
