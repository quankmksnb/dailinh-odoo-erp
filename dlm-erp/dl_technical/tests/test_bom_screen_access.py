# -*- coding: utf-8 -*-
"""L2 Integration test cho SCR-17..22 (FDS): Danh sách/Chi tiết BOM (dl.bom),
Danh sách/Chi tiết BOM mẫu (dl.bom.template), Danh sách/Chi tiết Bản vẽ kỹ
thuật (dl.drawing).

Khác test_cost_field_visibility_security.py (che field chi phí theo groups=
trên view) và test_bom_btp_linkage.py (nghiệp vụ liên kết BOM/BTP/bản vẽ),
test này canh ranh giới ĐỌC/GHI Ở CẤP BẢN GHI (ir.model.access.csv) cho 3
model trên: vai trò nào chỉ được xem, vai trò nào được sửa, vai trò nào
không có quyền gì.

Theo PRD, CEO và Trưởng phòng KD được xem BOM/giá nhưng KHÔNG được sửa (chỉ
Kỹ thuật/Admin mới sửa). Rà ACL thật (dl_technical/security/ir.model.access.csv)
xác nhận đúng cho dl.bom và dl.bom.template — nhưng NV Kinh doanh (BA) cũng có
quyền đọc y hệt CEO/Trưởng phòng KD trên 2 model này (không phải "không có
quyền gì" như đôi khi bị hiểu nhầm). Riêng dl.drawing thì Trưởng phòng KD
KHÔNG có dòng ACL nào cả (không đọc được), khác với dl.bom/dl.bom.template —
xem menus.xml (menu_drawing) đã ghi chú chủ đích này. Test dưới đây khẳng
định đúng các lệch nhau này bằng ACL thật, không suy đoán.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical", "dl_security")
class TestBomScreenAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_categ = cls.env["product.category"].create({
            "name": "Nhóm TP (test màn hình BOM)",
            "parent_id": cls.env.ref("dl_product.categ_root_finished").id,
        })
        cls.material = cls.env["product.product"].create({
            "name": "Vật tư (test màn hình BOM)", "product_kind": "material",
        })
        cls.product = cls.env["product.product"].create({
            "name": "SP (test màn hình BOM)",
            "product_kind": "manufactured",
            "categ_id": cls.finished_categ.id,
        })
        cls.bom = cls.env["dl.bom"].create({
            "product_id": cls.product.id,
            "bom_type": "template",
            "line_ids": [(0, 0, {
                "material_id": cls.material.id,
                "quantity": 1.0,
            })],
        })
        cls.template = cls.env["dl.bom.template"].create({
            "name": "BOM mẫu (test màn hình BOM)",
            "product_category_id": cls.finished_categ.id,
            "line_ids": [(0, 0, {
                "material_id": cls.material.id,
                "quantity": 1.0,
            })],
        })
        cls.drawing = cls.env["dl.drawing"].create({
            "name": "Bản vẽ (test màn hình BOM)",
            "product_id": cls.product.id,
            "version": 1,
        })

    def _user(self, group_xmlid, login):
        return self.env["res.users"].create({
            "name": login,
            "login": login,
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref(group_xmlid).id,
            ])],
        })

    def _assert_read_only(self, record, user, model_name):
        """Đọc được, nhưng write/create/unlink đều phải raise AccessError."""
        # Đọc được — không raise.
        record.with_user(user).read(["name"])
        with self.assertRaises(AccessError):
            record.with_user(user).write({"note": "note test màn hình"})
        with self.assertRaises(AccessError):
            self.env[model_name].with_user(user).create(
                self._minimal_vals(model_name))
        with self.assertRaises(AccessError):
            record.with_user(user).unlink()

    def _assert_no_access(self, record, user):
        """Không có dòng ACL nào khớp — kể cả đọc cũng phải raise AccessError."""
        with self.assertRaises(AccessError):
            record.with_user(user).read(["name"])

    def _minimal_vals(self, model_name):
        if model_name == "dl.bom":
            return {
                "product_id": self.product.id,
                "bom_type": "template",
                "line_ids": [(0, 0, {
                    "material_id": self.material.id, "quantity": 1.0})],
            }
        if model_name == "dl.bom.template":
            # Nhóm sản phẩm riêng cho mỗi lần gọi — cls.template đã chiếm
            # version=1 cho finished_categ, và version truyền vào create()
            # không đáng tin cậy tránh unique(product_category_id, version)
            # (dl_bom_template_categ_version_uniq) nên dùng hẳn nhóm mới,
            # chưa từng có bản ghi nào, để không thể đụng constraint.
            fresh_categ = self.env["product.category"].create({
                "name": "Nhóm TP tạo trái phép (test màn hình BOM)",
                "parent_id": self.env.ref("dl_product.categ_root_finished").id,
            })
            return {
                "name": "BOM mẫu tạo trái phép",
                "product_category_id": fresh_categ.id,
                "line_ids": [(0, 0, {
                    "material_id": self.material.id, "quantity": 1.0})],
            }
        return {
            "name": "Bản vẽ tạo trái phép",
            "product_id": self.product.id,
            # cls.drawing đã chiếm version=1 cho sản phẩm này (không có logic
            # tự dời version như dl.bom) — dùng version khác để tránh đụng
            # unique(product_id, version).
            "version": 2,
        }

    # ================================================================
    # SCR-17/18 — Danh sách/Chi tiết BOM (dl.bom)
    # ================================================================
    def test_scr17_18_ceo_can_read_not_write_bom(self):
        """TC-INT-TestBomScreenAccess-001: CEO mở được màn Danh sách/Chi tiết
        BOM (SCR-17/18) và đọc được bản ghi, nhưng sửa/tạo mới/xóa đều bị
        AccessError — CEO chỉ xem, không sửa BOM đúng PRD.
        """
        ceo = self._user("dl_base.dl_group_ceo", "ceo_scr1718")
        self._assert_read_only(self.bom, ceo, "dl.bom")

    def test_scr17_18_sales_manager_can_read_not_write_bom(self):
        """TC-INT-TestBomScreenAccess-002: Trưởng phòng KD mở được màn
        Danh sách/Chi tiết BOM (SCR-17/18) và đọc được bản ghi, nhưng sửa/tạo
        mới/xóa đều bị AccessError.
        """
        sm = self._user("dl_base.dl_group_sales_manager", "sm_scr1718")
        self._assert_read_only(self.bom, sm, "dl.bom")

    def test_scr17_18_ba_can_read_not_write_bom(self):
        """TC-INT-TestBomScreenAccess-003: NV Kinh doanh (BA) cũng đọc được
        dl.bom giống hệt CEO/Trưởng phòng KD (ACL cấp read=1 cho cả ba vai
        trò) dù BA không có mục BOM trên sidebar (menu_bom_parent không khai
        nhóm BA) — đây là quyền model thật, không phải "không quyền gì".
        Sửa/tạo mới/xóa vẫn bị AccessError.
        """
        ba = self._user("dl_base.dl_group_ba", "ba_scr1718")
        self._assert_read_only(self.bom, ba, "dl.bom")

    def test_scr17_18_tech_can_write_but_not_unlink_bom(self):
        """TC-INT-TestBomScreenAccess-004: Kỹ thuật sửa được và tạo mới được
        BOM (đúng PRD — Kỹ thuật có toàn quyền biên tập), nhưng xóa hẳn
        (unlink) vẫn bị AccessError vì ACL Tech chỉ cấp read/write/create,
        không cấp unlink.
        """
        tech = self._user("dl_base.dl_group_tech", "tech_scr1718")
        bom_tech = self.bom.with_user(tech)
        bom_tech.write({"note": "Kỹ thuật sửa ghi chú"})
        self.assertEqual(bom_tech.note, "Kỹ thuật sửa ghi chú")
        new_bom = self.env["dl.bom"].with_user(tech).create(
            self._minimal_vals("dl.bom"))
        self.assertTrue(new_bom.exists())
        with self.assertRaises(AccessError):
            new_bom.unlink()

    def test_scr17_18_admin_full_crud_bom(self):
        """TC-INT-TestBomScreenAccess-005: Admin/IT có toàn quyền CRUD trên
        dl.bom, kể cả unlink — khác Kỹ thuật.
        """
        admin = self._user("dl_base.dl_group_admin", "admin_scr1718")
        new_bom = self.env["dl.bom"].with_user(admin).create(
            self._minimal_vals("dl.bom"))
        new_bom.write({"note": "Admin sửa ghi chú"})
        new_bom.unlink()
        self.assertFalse(new_bom.exists())

    def test_scr17_18_purchasing_and_warehouse_cannot_read_bom(self):
        """TC-INT-TestBomScreenAccess-006: Mua hàng và Thủ kho không có dòng
        ACL nào cho dl.bom — mở màn BOM (SCR-17/18) phải bị AccessError ngay
        từ bước đọc, không chỉ bị ẩn menu.
        """
        purchasing = self._user("dl_base.dl_group_purchasing", "pur_scr1718")
        warehouse = self._user("dl_base.dl_group_warehouse", "wh_scr1718")
        self._assert_no_access(self.bom, purchasing)
        self._assert_no_access(self.bom, warehouse)

    # ================================================================
    # SCR-19/20 — Danh sách/Chi tiết BOM mẫu (dl.bom.template)
    # ================================================================
    def test_scr19_20_ceo_can_read_not_write_bom_template(self):
        """TC-INT-TestBomScreenAccess-007: CEO mở được màn Danh sách/Chi tiết
        BOM mẫu (SCR-19/20) và đọc được bản ghi, nhưng sửa/tạo mới/xóa đều bị
        AccessError.
        """
        ceo = self._user("dl_base.dl_group_ceo", "ceo_scr1920")
        self._assert_read_only(self.template, ceo, "dl.bom.template")

    def test_scr19_20_sales_manager_can_read_not_write_bom_template(self):
        """TC-INT-TestBomScreenAccess-008: Trưởng phòng KD mở được màn Danh
        sách/Chi tiết BOM mẫu (SCR-19/20) và đọc được bản ghi, nhưng sửa/tạo
        mới/xóa đều bị AccessError.
        """
        sm = self._user("dl_base.dl_group_sales_manager", "sm_scr1920")
        self._assert_read_only(self.template, sm, "dl.bom.template")

    def test_scr19_20_tech_can_write_but_not_unlink_bom_template(self):
        """TC-INT-TestBomScreenAccess-009: Kỹ thuật sửa/tạo mới được BOM mẫu,
        nhưng xóa hẳn vẫn bị AccessError giống dl.bom (ACL Tech không cấp
        unlink).
        """
        tech = self._user("dl_base.dl_group_tech", "tech_scr1920")
        tpl_tech = self.template.with_user(tech)
        tpl_tech.write({"product_qty": 5.0})
        self.assertEqual(tpl_tech.product_qty, 5.0)
        new_tpl = self.env["dl.bom.template"].with_user(tech).create(
            self._minimal_vals("dl.bom.template"))
        self.assertTrue(new_tpl.exists())
        with self.assertRaises(AccessError):
            new_tpl.unlink()

    def test_scr19_20_admin_full_crud_bom_template(self):
        """TC-INT-TestBomScreenAccess-010: Admin/IT có toàn quyền CRUD trên
        dl.bom.template, kể cả unlink.
        """
        admin = self._user("dl_base.dl_group_admin", "admin_scr1920")
        new_tpl = self.env["dl.bom.template"].with_user(admin).create(
            self._minimal_vals("dl.bom.template"))
        new_tpl.write({"product_qty": 5.0})
        new_tpl.unlink()
        self.assertFalse(new_tpl.exists())

    def test_scr19_20_purchasing_and_warehouse_cannot_read_bom_template(self):
        """TC-INT-TestBomScreenAccess-011: Mua hàng và Thủ kho không có dòng
        ACL nào cho dl.bom.template — mở màn BOM mẫu (SCR-19/20) phải bị
        AccessError ngay từ bước đọc.
        """
        purchasing = self._user("dl_base.dl_group_purchasing", "pur_scr1920")
        warehouse = self._user("dl_base.dl_group_warehouse", "wh_scr1920")
        self._assert_no_access(self.template, purchasing)
        self._assert_no_access(self.template, warehouse)

    # ================================================================
    # SCR-21/22 — Danh sách/Chi tiết Bản vẽ kỹ thuật (dl.drawing)
    # ================================================================
    def test_scr21_22_ceo_can_read_not_write_drawing(self):
        """TC-INT-TestBomScreenAccess-012: CEO mở được màn Danh sách/Chi tiết
        Bản vẽ kỹ thuật (SCR-21/22) và đọc được bản ghi, nhưng sửa/tạo
        mới/xóa đều bị AccessError.
        """
        ceo = self._user("dl_base.dl_group_ceo", "ceo_scr2122")
        self._assert_read_only(self.drawing, ceo, "dl.drawing")

    def test_scr21_22_sales_manager_cannot_read_drawing(self):
        """TC-INT-TestBomScreenAccess-013: Khác hẳn dl.bom/dl.bom.template,
        Trưởng phòng KD KHÔNG có dòng ACL nào cho dl.drawing (chủ đích, xem
        chú thích menu_drawing trong menus.xml) — mở màn Bản vẽ kỹ thuật
        (SCR-21/22) phải bị AccessError ngay từ bước đọc, không chỉ bị ẩn
        menu. Đây là lệch thật so với suy nghĩ "CEO và Trưởng phòng KD đều
        xem được BOM/bản vẽ" nếu áp dụng đồng nhất cho cả 3 model.
        """
        sm = self._user("dl_base.dl_group_sales_manager", "sm_scr2122")
        self._assert_no_access(self.drawing, sm)

    def test_scr21_22_tech_can_write_but_not_unlink_drawing(self):
        """TC-INT-TestBomScreenAccess-014: Kỹ thuật sửa/tạo mới được bản vẽ,
        nhưng xóa hẳn vẫn bị AccessError (ACL Tech không cấp unlink, giống
        dl.bom/dl.bom.template).
        """
        tech = self._user("dl_base.dl_group_tech", "tech_scr2122")
        drawing_tech = self.drawing.with_user(tech)
        drawing_tech.write({"name": "Kỹ thuật sửa tên bản vẽ"})
        self.assertEqual(drawing_tech.name, "Kỹ thuật sửa tên bản vẽ")
        new_drawing = self.env["dl.drawing"].with_user(tech).create(
            self._minimal_vals("dl.drawing"))
        self.assertTrue(new_drawing.exists())
        with self.assertRaises(AccessError):
            new_drawing.unlink()

    def test_scr21_22_admin_full_crud_drawing(self):
        """TC-INT-TestBomScreenAccess-015: Admin/IT có toàn quyền CRUD trên
        dl.drawing, kể cả unlink.
        """
        admin = self._user("dl_base.dl_group_admin", "admin_scr2122")
        new_drawing = self.env["dl.drawing"].with_user(admin).create(
            self._minimal_vals("dl.drawing"))
        new_drawing.write({"version": 2})
        new_drawing.unlink()
        self.assertFalse(new_drawing.exists())

    def test_scr21_22_ba_purchasing_warehouse_cannot_read_drawing(self):
        """TC-INT-TestBomScreenAccess-016: NV Kinh doanh, Mua hàng và Thủ kho
        đều không có dòng ACL nào cho dl.drawing — mở màn Bản vẽ kỹ thuật
        (SCR-21/22) phải bị AccessError ngay từ bước đọc.
        """
        ba = self._user("dl_base.dl_group_ba", "ba_scr2122")
        purchasing = self._user("dl_base.dl_group_purchasing", "pur_scr2122")
        warehouse = self._user("dl_base.dl_group_warehouse", "wh_scr2122")
        self._assert_no_access(self.drawing, ba)
        self._assert_no_access(self.drawing, purchasing)
        self._assert_no_access(self.drawing, warehouse)


if __name__ == "__main__":
    import unittest
    unittest.main()
