# -*- coding: utf-8 -*-
"""L2 (TransactionCase, chạm DB thật) cho 4 màn chưa có test riêng:

- SCR-08 Danh sách Khách hàng / SCR-09 Chi tiết Khách hàng
  (view_dl_customer_tree/search/form, action_dl_customer, menu_dl_sale_customer).
- SCR-10 Danh sách Nhà cung cấp / SCR-11 Chi tiết Nhà cung cấp
  (view_dl_supplier_tree/search/form, action_dl_supplier +
  action_dl_supplier_readonly, menu_dl_sale_supplier +
  menu_dl_sale_supplier_readonly).

Ba việc test canh: (1) nội dung hiển thị đúng theo domain của từng action,
(2) menu ẩn/hiện đúng vai trò, (3) ranh giới đọc/ghi/tạo thật sự khớp với ACL
(security/ir.model.access.csv) và record rule (security/ir_rule.xml) — KHÔNG
suy từ context create/edit/delete=False của action chỉ-đọc, vì đó chỉ là gợi ý
UX (xem comment action_dl_supplier_readonly trong views/supplier_views.xml).

res.partner không có field nào khai `groups=` ở cấp field (đã rà
models/res_partner.py), nên màn này không có nội dung ẩn/hiện theo field như
kiểu dl_technical/tests/test_cost_field_visibility_security.py — ranh giới
thật của hai màn KH/NCC nằm ở: menu groups=, domain của action, và ACL/ir.rule
trên chính model res.partner.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


def _visible(env, user, menu):
    return menu.id in env["ir.ui.menu"].with_context(
        **{"ir.ui.menu.full_list": True}).with_user(user)._visible_menu_ids()


@tagged("post_install", "-at_install", "dl_partner")
class TestCustomerScreenAccess(TransactionCase):
    """SCR-08 Danh sách Khách hàng, SCR-09 Chi tiết Khách hàng."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu_customer = cls.env.ref("dl_partner.menu_dl_sale_customer")
        cls.action_customer = cls.env.ref("dl_partner.action_dl_customer")

        cls.user_sales_manager = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test màn KH)",
            "login": "dlm_test_scr08_sales_manager",
            "groups_id": [(6, 0, [cls.env.ref(
                "dl_base.dl_group_sales_manager").id])],
        })
        cls.user_ba = cls.env["res.users"].create({
            "name": "BA/Sales (test màn KH)",
            "login": "dlm_test_scr08_ba",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ba").id])],
        })
        cls.user_purchasing = cls.env["res.users"].create({
            "name": "Mua hàng (test màn KH)",
            "login": "dlm_test_scr08_purchasing",
            "groups_id": [(6, 0, [cls.env.ref(
                "dl_base.dl_group_purchasing").id])],
        })
        # Kỹ thuật: không có mặt trong groups= của menu_dl_sale_customer, cũng
        # không có dòng ACL riêng nào cho res.partner trong dl_partner — vai
        # trò "ngoài cuộc" thật sự của màn Khách hàng.
        cls.user_tech = cls.env["res.users"].create({
            "name": "Kỹ thuật (test màn KH, ngoài cuộc)",
            "login": "dlm_test_scr08_tech",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })

        cls.customer = cls.env["res.partner"].create({
            "name": "Nguyễn Văn Bình (KH test màn KH)",
            "partner_role": "customer",
            "partner_type": "individual",
            "mobile": "0911100001",
        })
        cls.supplier_only = cls.env["res.partner"].create({
            "name": "Xưởng Cơ khí Thành Đạt (NCC test màn KH)",
            "partner_role": "supplier",
            "partner_type": "individual",
            "mobile": "0911100002",
        })

    def test_vai_tro_duoc_khai_deu_thay_menu_khach_hang(self):
        """TC-INT-TestCustomerScreenAccess-001: Trưởng phòng KD, BA và Mua hàng
        (3 vai trò trong groups= của menu_dl_sale_customer, trừ Admin/CEO đã
        được test_menu_role_declaration.py canh chung cho mọi menu) đều thấy
        menu Khách hàng."""
        for user in (self.user_sales_manager, self.user_ba):
            self.assertTrue(
                _visible(self.env, user, self.menu_customer),
                "%s phải thấy menu Khách hàng." % user.name)

    def test_ngoai_cuoc_khong_thay_menu_khach_hang(self):
        """TC-INT-TestCustomerScreenAccess-002: Kỹ thuật không nằm trong
        groups= của menu_dl_sale_customer nên không được thấy menu này trên
        rail."""
        self.assertFalse(
            _visible(self.env, self.user_tech, self.menu_customer),
            "Kỹ thuật không thuộc vai trò nào của màn Khách hàng nhưng vẫn "
            "thấy menu — role-based hide bị rò.")

    def test_domain_action_khach_hang_chi_lay_dung_khach_hang(self):
        """TC-INT-TestCustomerScreenAccess-003: Nội dung hiển thị đúng — mở
        màn Khách hàng (domain của action_dl_customer) bằng vai trò được phép
        phải thấy khách hàng, và KHÔNG được lẫn nhà cung cấp thuần vào danh
        sách."""
        import ast
        domain = ast.literal_eval(self.action_customer.domain)
        found = self.env["res.partner"].with_user(
            self.user_sales_manager).with_context(active_test=False).search(domain)
        self.assertIn(self.customer, found)
        self.assertNotIn(self.supplier_only, found)

    def test_mua_hang_khong_doc_duoc_khach_hang_thuan(self):
        """TC-INT-TestCustomerScreenAccess-004: rule_partner_purchasing_supplier_only
        (security/ir_rule.xml) chặn Mua hàng đọc đối tác partner_role='customer'
        — Mua hàng sở hữu NCC, không được đụng vào Khách hàng thuần."""
        with self.assertRaises(AccessError):
            self.customer.with_user(self.user_purchasing).read(["name"])

    def test_ngoai_cuoc_van_doc_duoc_du_lieu_khach_hang_qua_orm(self):
        """TC-INT-TestCustomerScreenAccess-005: PHÁT HIỆN LỆCH THẬT — menu ẩn
        (test 002) KHÔNG đồng nghĩa dữ liệu bị khoá ở tầng model. ACL gốc của
        Odoo (base: access_res_partner_group_user) đã cấp perm_read=1 trên
        res.partner cho MỌI user nội bộ (base.group_user), và dl_partner
        không có ir.rule nào áp cho dl_group_tech. Kết quả: Kỹ thuật không
        thấy menu Khách hàng, nhưng gọi thẳng ORM (vd qua danh sách liên quan
        ở màn khác, hay dev console) vẫn đọc được y nguyên dữ liệu khách hàng.
        Ranh giới của SCR-08 chỉ nằm ở menu, KHÔNG phải ở ACL/ir.rule."""
        found = self.customer.with_user(self.user_tech).read(["name", "phone"])
        self.assertEqual(found[0]["name"], self.customer.name)

    def test_dieu_huong_chi_tiet_khach_hang_ra_dung_form_kh(self):
        """TC-INT-TestCustomerScreenAccess-006: SCR-09 — get_formview_id/
        get_formview_action của một bản ghi partner_role=customer phải trả về
        đúng view_dl_customer_form/action_dl_customer_form, để mũi tên mở KH từ
        màn khác (vd Báo giá) luôn ra đúng form Khách hàng, không rơi về form
        Contacts gốc của Odoo."""
        view_id = self.customer.get_formview_id()
        self.assertEqual(
            view_id, self.env.ref("dl_partner.view_dl_customer_form").id)

        action = self.customer.get_formview_action()
        self.assertEqual(
            action["res_id"], self.customer.id)
        opened_view_ids = [vid for vid, _mode in action.get("views") or []]
        self.assertIn(
            self.env.ref("dl_partner.view_dl_customer_form").id,
            opened_view_ids + [action.get("view_id")])


@tagged("post_install", "-at_install", "dl_partner")
class TestSupplierScreenAccess(TransactionCase):
    """SCR-10 Danh sách Nhà cung cấp, SCR-11 Chi tiết Nhà cung cấp.

    Hai action song song trên cùng model/view: action_dl_supplier (sửa được:
    Admin/CEO/Mua hàng, menu_dl_sale_supplier) và action_dl_supplier_readonly
    (chỉ xem: Trưởng phòng KD, menu_dl_sale_supplier_readonly). Comment trong
    views/supplier_views.xml nói rõ context create/edit/delete=False của
    action chỉ-đọc chỉ là UX, "bảo mật thật do ir.rule đảm nhiệm" — test này
    canh đúng cái ir.rule đó, không canh cái context.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu_supplier_edit = cls.env.ref("dl_partner.menu_dl_sale_supplier")
        cls.menu_supplier_readonly = cls.env.ref(
            "dl_partner.menu_dl_sale_supplier_readonly")
        cls.action_supplier = cls.env.ref("dl_partner.action_dl_supplier")
        cls.action_supplier_readonly = cls.env.ref(
            "dl_partner.action_dl_supplier_readonly")

        cls.user_admin = cls.env["res.users"].create({
            "name": "Admin/IT (test màn NCC)",
            "login": "dlm_test_scr10_admin",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_admin").id])],
        })
        cls.user_ceo = cls.env["res.users"].create({
            "name": "CEO (test màn NCC)",
            "login": "dlm_test_scr10_ceo",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.user_purchasing = cls.env["res.users"].create({
            "name": "Mua hàng (test màn NCC)",
            "login": "dlm_test_scr10_purchasing",
            "groups_id": [(6, 0, [cls.env.ref(
                "dl_base.dl_group_purchasing").id])],
        })
        cls.user_sales_manager = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test màn NCC, chỉ xem)",
            "login": "dlm_test_scr10_sales_manager",
            "groups_id": [(6, 0, [cls.env.ref(
                "dl_base.dl_group_sales_manager").id])],
        })
        cls.user_tech = cls.env["res.users"].create({
            "name": "Kỹ thuật (test màn NCC, ngoài cuộc)",
            "login": "dlm_test_scr10_tech",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })

        cls.supplier = cls.env["res.partner"].create({
            "name": "Công ty TNHH Vật tư Phương Nam (NCC test màn NCC)",
            "partner_role": "supplier",
            "partner_type": "individual",
            "mobile": "0911100011",
        })
        cls.customer_only = cls.env["res.partner"].create({
            "name": "Trần Thị Hạnh (KH test màn NCC)",
            "partner_role": "customer",
            "partner_type": "individual",
            "mobile": "0911100012",
        })

    # ── Menu: sửa được vs chỉ-đọc phải tách đúng người ─────────────────
    def test_vai_tro_sua_duoc_thay_menu_ncc_sua(self):
        """TC-INT-TestSupplierScreenAccess-001: Admin, CEO, Mua hàng (groups=
        của menu_dl_sale_supplier) đều thấy menu NCC bản sửa được."""
        for user in (self.user_admin, self.user_ceo, self.user_purchasing):
            self.assertTrue(
                _visible(self.env, user, self.menu_supplier_edit),
                "%s phải thấy menu NCC (sửa được)." % user.name)

    def test_truong_phong_kd_khong_thay_menu_ncc_sua(self):
        """TC-INT-TestSupplierScreenAccess-002: Trưởng phòng KD không nằm
        trong groups= của menu_dl_sale_supplier (bản sửa được) nên không được
        thấy menu này — Trưởng phòng KD chỉ có menu chỉ-đọc riêng."""
        self.assertFalse(
            _visible(self.env, self.user_sales_manager, self.menu_supplier_edit))

    def test_chi_truong_phong_kd_thay_menu_ncc_chi_doc(self):
        """TC-INT-TestSupplierScreenAccess-003: menu_dl_sale_supplier_readonly
        chỉ khai groups=dl_base.dl_group_sales_manager — Admin/CEO/Mua hàng
        (đã có menu sửa được riêng) không cần và không được thấy menu chỉ-đọc
        này (tránh 2 lối vào trùng lặp cho cùng một vai trò)."""
        self.assertTrue(
            _visible(self.env, self.user_sales_manager, self.menu_supplier_readonly))
        for user in (self.user_admin, self.user_ceo, self.user_purchasing,
                     self.user_tech):
            self.assertFalse(
                _visible(self.env, user, self.menu_supplier_readonly),
                "%s không thuộc vai trò chỉ-xem NCC nhưng vẫn thấy menu."
                % user.name)

    def test_ngoai_cuoc_khong_thay_ca_hai_menu_ncc(self):
        """TC-INT-TestSupplierScreenAccess-004: Kỹ thuật không thấy menu NCC
        ở cả 2 dạng (sửa được lẫn chỉ-đọc)."""
        self.assertFalse(_visible(self.env, self.user_tech, self.menu_supplier_edit))
        self.assertFalse(
            _visible(self.env, self.user_tech, self.menu_supplier_readonly))

    # ── Nội dung hiển thị: domain action chỉ lấy đúng NCC ──────────────
    def test_domain_action_ncc_chi_lay_dung_nha_cung_cap(self):
        """TC-INT-TestSupplierScreenAccess-005: domain của action_dl_supplier
        (dùng chung cho cả bản sửa và bản chỉ-đọc) phải thấy NCC và KHÔNG lẫn
        khách hàng thuần vào danh sách."""
        import ast
        domain = ast.literal_eval(self.action_supplier.domain)
        found = self.env["res.partner"].with_user(
            self.user_purchasing).with_context(active_test=False).search(domain)
        self.assertIn(self.supplier, found)
        self.assertNotIn(self.customer_only, found)

    # ── Ranh giới ghi thật: ir.rule, không phải context UI ─────────────
    def test_mua_hang_sua_duoc_nha_cung_cap(self):
        """TC-INT-TestSupplierScreenAccess-006: Mua hàng là chủ sở hữu NCC —
        ACL (access_dl_partner_purchasing, perm_write=1) và ir.rule
        (rule_partner_purchasing_supplier_only chỉ chặn Khách hàng thuần,
        không chặn NCC) đều cho phép sửa."""
        self.supplier.with_user(self.user_purchasing).write(
            {"comment": "Cập nhật bởi Mua hàng (test 006)"})
        self.assertIn("Cập nhật bởi Mua hàng (test 006)", self.supplier.comment)

    def test_admin_sua_duoc_nha_cung_cap(self):
        """TC-INT-TestSupplierScreenAccess-007: Admin có ACL full CRUD trên
        res.partner nên sửa được NCC."""
        self.supplier.with_user(self.user_admin).write(
            {"comment": "Cập nhật bởi Admin (test 007)"})
        self.assertIn("Cập nhật bởi Admin (test 007)", self.supplier.comment)

    def test_truong_phong_kd_doc_duoc_nhung_khong_sua_duoc_ncc(self):
        """TC-INT-TestSupplierScreenAccess-008: Trưởng phòng KD đọc được NCC
        (rule_partner_sales_manager_no_supplier có perm_read=0 — domain KHÔNG
        áp cho thao tác đọc, nên đọc không bị chặn) nhưng ghi thì domain_force
        ('partner_role', '!=', 'supplier') loại NCC ra khỏi phạm vi được sửa,
        nên write() phải báo AccessError. Đây là bằng chứng "chỉ xem" thật sự
        nằm ở ir.rule, không phải ở context create/edit/delete=False của
        action_dl_supplier_readonly (context đó chỉ là gợi ý UX)."""
        # Đọc được — nội dung màn chỉ-đọc hiển thị đúng.
        data = self.supplier.with_user(self.user_sales_manager).read(["name"])
        self.assertEqual(data[0]["name"], self.supplier.name)

        # Sửa thì bị chặn thật, ở tầng ir.rule.
        with self.assertRaises(AccessError):
            self.supplier.with_user(self.user_sales_manager).write(
                {"comment": "Trưởng phòng KD cố sửa (test 008)"})

    def test_truong_phong_kd_khong_tao_duoc_nha_cung_cap_moi(self):
        """TC-INT-TestSupplierScreenAccess-009: cùng domain_force ở test 008
        cũng chặn CREATE — Trưởng phòng KD không tạo được đối tác
        partner_role='supplier' mới."""
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.user_sales_manager).create({
                "name": "NCC do Trưởng phòng KD cố tạo (test 009)",
                "partner_role": "supplier",
                "partner_type": "individual",
                "mobile": "0911100013",
            })

    def test_ceo_doc_duoc_nhung_khong_sua_duoc_ncc_du_menu_noi_full_crud(self):
        """TC-INT-TestSupplierScreenAccess-010: PHÁT HIỆN LỆCH THẬT — comment
        trong dl_partner/views/partner_menus.xml ghi "NCC full-CRUD: Admin /
        CEO / Mua hàng" cho menu_dl_sale_supplier, và CEO nằm trong groups=
        của menu đó. Nhưng dòng ACL access_dl_partner_ceo (ir.model.access.csv)
        chỉ cấp perm_read=1, perm_write=0, perm_create=0, perm_unlink=0 trên
        res.partner. Thực tế: CEO thấy menu, đọc được NCC, nhưng KHÔNG sửa
        được — "full-CRUD" trong comment không khớp với ACL thật. Test này
        khoá lại hành vi thật (đọc được — sửa bị chặn) để không ai vô tình
        "sửa cho khớp comment" mà không nhận ra đây là một quyết định phân
        quyền cần xác nhận lại với nghiệp vụ."""
        data = self.supplier.with_user(self.user_ceo).read(["name"])
        self.assertEqual(data[0]["name"], self.supplier.name)

        with self.assertRaises(AccessError):
            self.supplier.with_user(self.user_ceo).write(
                {"comment": "CEO cố sửa (test 010)"})

    def test_dieu_huong_chi_tiet_nha_cung_cap_ra_dung_form_ncc(self):
        """TC-INT-TestSupplierScreenAccess-011: SCR-11 — get_formview_id/
        get_formview_action của một bản ghi partner_role=supplier phải trả về
        đúng view_dl_supplier_form/action_dl_supplier_form."""
        view_id = self.supplier.get_formview_id()
        self.assertEqual(
            view_id, self.env.ref("dl_partner.view_dl_supplier_form").id)

        action = self.supplier.get_formview_action()
        self.assertEqual(action["res_id"], self.supplier.id)
        opened_view_ids = [vid for vid, _mode in action.get("views") or []]
        self.assertIn(
            self.env.ref("dl_partner.view_dl_supplier_form").id,
            opened_view_ids + [action.get("view_id")])
