# -*- coding: utf-8 -*-
"""Menu khai vai trò nào thì vai trò đó phải THẬT SỰ thấy menu đó.

Loại lỗi được canh ở đây thuộc dạng **sai lặng lẽ nhất trong repo**: Odoo tự ẩn
một menu khi vai trò không đọc được model của action (`ir_ui_menu._visible_menu_ids`
gọi `ir.model.access.check(model, 'read', False)`). Không có lỗi nào nổ, không có
dòng log nào — mục chỉ đơn giản không xuất hiện trên rail.

Hệ quả: thuộc tính `groups=` trên `<menuitem>` NÓI DỐI mà không ai biết. Đọc XML
tưởng đã cấp quyền cho vai trò đó, còn người dùng thật thì không bao giờ thấy
màn hình. Đã xảy ra thật với "Bản vẽ kỹ thuật" cấp cho Trưởng phòng KD trong khi
`dl.drawing` không có dòng ACL nào cho vai trò này (rà soát 2026-08-20).

Test chạy với TOÀN BỘ module đã cài, nên nó canh cho mọi module — module mới
thêm menu sai cũng đỏ ở đây, không cần viết lại test.
"""

from odoo.tests.common import TransactionCase, tagged

# 7 vai trò nghiệp vụ. Không lấy động từ category RBAC: vai trò do Admin tạo tay
# trên màn Phân quyền cũng nằm trong category đó, và quyền của chúng là chuyện
# của người quản trị, không phải bất biến của code.
ROLE_XMLIDS = [
    "dl_base.dl_group_ceo",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ba",
    "dl_base.dl_group_tech",
    "dl_base.dl_group_sales_manager",
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_warehouse",
]


@tagged("post_install", "-at_install", "dl_base")
class TestMenuRoleDeclaration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = cls.env.ref("dl_base.menu_dl_root")
        cls.roles = {}
        cls.users = {}
        for xmlid in ROLE_XMLIDS:
            group = cls.env.ref(xmlid)
            cls.roles[group.id] = group
            # Mỗi vai trò một user thật: chỉ user thật mới kéo theo implied_ids
            # (base.group_user, stock.group_stock_user của Thủ kho...) — thứ
            # quyết định phần lớn quyền đọc nền.
            cls.users[group.id] = cls.env["res.users"].create({
                "name": group.name,
                "login": "dlm_test_%s" % xmlid.split(".")[-1],
                "groups_id": [(6, 0, [group.id])],
            })

    def _dl_menus(self):
        """Mọi menu con cháu của app DLM-ERP (kể cả menu đã ẩn khỏi rail)."""
        return self.env["ir.ui.menu"].with_context(**{
            "ir.ui.menu.full_list": True,
        }).search([("id", "child_of", self.root.id), ("id", "!=", self.root.id)])

    def test_moi_vai_tro_khai_tren_menu_deu_thuc_su_thay_menu(self):
        lies = []
        for menu in self._dl_menus():
            if not menu.action:
                continue  # menu container — tính khả dụng suy ra từ menu con
            for group in menu.groups_id:
                if group.id not in self.roles:
                    continue  # nhóm thao tác / nhóm kỹ thuật — không phải vai trò
                user = self.users[group.id]
                visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
                if menu.id not in visible:
                    lies.append("%s (%s) khai cho vai trò %s" % (
                        menu.complete_name, menu.action.display_name, group.name))
        self.assertFalse(lies, (
            "Menu khai vai trò nhưng Odoo ẩn mất vì vai trò không đọc được model "
            "của action. Cấp ACL đọc, hoặc gỡ vai trò khỏi groups= — đừng để lệch:\n  "
            + "\n  ".join(sorted(lies))))
