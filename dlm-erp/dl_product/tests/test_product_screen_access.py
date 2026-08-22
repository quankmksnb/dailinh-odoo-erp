# -*- coding: utf-8 -*-
"""L2 (TransactionCase, chạm DB thật) cho 7 màn dùng chung model
product.product / product.category / product.supplierinfo — kiểm tra đúng cơ
chế thực thi (ACL vs ir.rule vs domain action vs create=0/edit=0 ở arch view),
không suy đoán từ tên action.

SCR-12/13 Sản phẩm (danh sách + chi tiết) — test_dl_product_unit.py chỉ có L1
(logic model thuần), test_trading_ownership.py đã phủ kỹ ranh giới TPKD/Sales
trên SP thương mại (product_kind='trading') nên KHÔNG lặp lại ở đây — lớp
TestProductListAccess tập trung vào CEO/BA (view-only) so với Admin/Kỹ thuật
(full) trên SP GIA CÔNG, và một ca đối chứng cho thấy rule cũ của BA
(rule_product_ba_trading_write_create) đã hết tác dụng vì ACL write/create đã
về 0.

SCR-14/15 Vật tư (danh sách + chi tiết) — cùng model, đổi domain
product_kind. Điểm đặc biệt: BA không có menu Vật tư nào (menus.xml), nhưng
ACL product.product của BA vẫn perm_read=1 không phân biệt loại SP — nghĩa là
việc "BA không xem được Vật tư" chỉ là ẩn ở TẦNG MENU/ACTION, không phải chặn
đọc ở tầng model. Trưởng phòng KD có ACL perm_create=1 trên product.product
nhưng bị ir.rule (rule_product_sm_trading_write_create) khoá tạo/sửa vào đúng
product_kind='trading' — nên hoàn toàn không tạo được Vật tư dù ACL cho phép.

SCR-16 Nhóm sản phẩm — action_dl_category_full gộp 3 vai trò (Admin, Trưởng
KD, Kỹ thuật) nhưng KHÔNG đồng nghĩa "full CRUD" cho cả 3: ACL
(ir.model.access.csv) chỉ cấp perm_unlink=1 cho Admin — Trưởng KD/Kỹ thuật
tạo/sửa được (giới hạn nhánh qua ir.rule) nhưng KHÔNG xoá được.

SCR-33 Bảng giá Vật tư (product.supplierinfo) — ACL đơn giản, không có
ir.rule can thiệp: Admin/Mua hàng full, CEO/Trưởng KD chỉ đọc.

SCR-34 Bảng giá SP thương mại — domain action cố định product_kind='trading'.
Chú thích trong product_pricing_views.xml nói "CEO/Trưởng KD chỉ xem (ACL
read-only)" nhưng thực tế Trưởng KD (dl_group_sales_manager) vẫn có
perm_write=1 + ir.rule cho phép sửa đúng SP thương mại (đây chính là quyền
"chốt giá bán" ở test_trading_ownership) — chỉ CEO mới thực sự chỉ-xem. Đây
là sai lệch tài liệu (comment) so với code thật, không phải lỗi phân quyền.

SCR-35 Vật tư chờ định giá — không phải model riêng: filter domain của
product.product trên action_dl_material_needs_price, và cơ chế "chỉ xem" ở
đây nằm ở ARCH của view_dl_material_needs_price_tree (create="0" edit="0"),
KHÔNG phải ACL/ir.rule (Mua hàng vẫn có ACL/rule cho phép ghi product).
"""
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


def _domain_of(env, action_xmlid):
    """Domain THẬT của action, đọc thẳng từ record — test sẽ đỏ nếu domain
    trong XML bị sửa lệch, thay vì chép tay domain rồi tự kiểm tra chính nó."""
    action = env.ref(action_xmlid)
    return safe_eval(action.domain or "[]")


@tagged("post_install", "-at_install", "dl_product")
class TestProductListAccess(TransactionCase):
    """SCR-12/13 — Sản phẩm (product.product, product_kind gia công/thương
    mại). Bốn action: action_dl_product_full (Admin), action_dl_product_tech
    (Kỹ thuật), action_dl_product_view (Admin/BA/CEO — chỉ xem),
    action_dl_product_trading_ba (Trưởng KD — đã có test_trading_ownership).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env["res.users"].create({
            "name": "Quản trị (test màn SP)", "login": "admin_scr12_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_admin").id])],
        })
        cls.tech = cls.env["res.users"].create({
            "name": "Kỹ thuật (test màn SP)", "login": "tech_scr12_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })
        cls.ceo = cls.env["res.users"].create({
            "name": "CEO (test màn SP)", "login": "ceo_scr12_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.ba = cls.env["res.users"].create({
            "name": "NV Kinh doanh (test màn SP)", "login": "ba_scr12_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ba").id])],
        })
        cls.manufactured = cls.env["product.product"].create({
            "name": "Khung thép hàn CT-200 (test màn SP)",
            "product_kind": "manufactured",
        })

    def test_admin_can_create_manufactured_product(self):
        """TC-INT-TestProductListAccess-001: Admin (action_dl_product_full)
        tạo được SP gia công."""
        product = self.env["product.product"].with_user(self.admin).create({
            "name": "Trục vít me phi 20 (test màn SP 001)",
            "product_kind": "manufactured",
        })
        self.assertTrue(product.id)

    def test_technician_can_create_manufactured_product(self):
        """TC-INT-TestProductListAccess-002: Kỹ thuật (action_dl_product_tech)
        tạo được SP gia công — ACL access_dl_product_prod_tech không bị
        ir.rule nào giới hạn theo product_kind."""
        product = self.env["product.product"].with_user(self.tech).create({
            "name": "Bánh răng côn Z24 (test màn SP 002)",
            "product_kind": "manufactured",
        })
        self.assertTrue(product.id)

    def test_ceo_cannot_create_product(self):
        """TC-INT-TestProductListAccess-003: CEO (action_dl_product_view —
        chỉ xem) không tạo được SP nào — chặn ở ACL (perm_create=0), không
        phải ir.rule."""
        with self.assertRaises(AccessError):
            self.env["product.product"].with_user(self.ceo).create({
                "name": "SP gia công lạ (test màn SP 003)",
                "product_kind": "manufactured",
            })

    def test_ba_cannot_create_manufactured_product(self):
        """TC-INT-TestProductListAccess-004: BA (action_dl_product_view —
        chỉ xem) không tạo được SP gia công. test_trading_ownership đã canh
        SP thương mại; ca này canh thêm loại gia công để không bỏ sót."""
        with self.assertRaises(AccessError):
            self.env["product.product"].with_user(self.ba).create({
                "name": "SP gia công lạ khác (test màn SP 004)",
                "product_kind": "manufactured",
            })

    def test_ceo_cannot_write_product(self):
        """TC-INT-TestProductListAccess-005: CEO không sửa được SP đã có
        (ACL perm_write=0)."""
        with self.assertRaises(AccessError):
            self.manufactured.with_user(self.ceo).write({
                "name": "Khung thép hàn CT-200 sửa tên (test màn SP 005)"})

    def test_ba_cannot_write_trading_product_despite_legacy_rule(self):
        """TC-INT-TestProductListAccess-006: rule_product_ba_trading_write_create
        (ir_rule.xml) vẫn còn khai perm_write=1/perm_create=1 cho BA trên SP
        thương mại — NHƯNG ACL access_dl_product_prod_ba đã hạ perm_write về 0
        (2026-08-15, quyền chuyển cho Trưởng KD). ACL và ir.rule được AND lại
        nên BA vẫn bị chặn ghi kể cả trên đúng loại SP mà rule cũ cho phép —
        rule cũ chỉ còn nằm đó cho tương thích DB, không còn hiệu lực thật.
        Dùng field `dlm_waste_rate` (không nằm trong _DLM_PROTECTED_FIELDS)
        để canh đúng lớp ACL/ir.rule, không lẫn với guard field riêng của
        `list_price`."""
        trading = self.env["product.product"].create({
            "name": "Máy khoan cầm tay (test màn SP 006)",
            "product_kind": "trading",
        })
        with self.assertRaises(AccessError):
            trading.with_user(self.ba).write({"dlm_waste_rate": 1.5})

    def test_ba_can_still_read_product(self):
        """TC-INT-TestProductListAccess-007: Đối chứng — chặn ghi không kéo
        theo chặn đọc, BA vẫn cần xem SP để làm báo giá/RFQ (ACL perm_read=1)."""
        name = self.manufactured.with_user(self.ba).read(["name"])[0]["name"]
        self.assertEqual(name, "Khung thép hàn CT-200 (test màn SP)")


@tagged("post_install", "-at_install", "dl_product")
class TestMaterialListAccess(TransactionCase):
    """SCR-14/15 — Vật tư (cùng model product.product, domain
    product_kind in material/material_processed). Ba action:
    action_dl_material_full (Admin), action_dl_material_tech (Kỹ thuật),
    action_dl_material_view (Admin/CEO/Trưởng KD — KHÔNG có BA)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env["res.users"].create({
            "name": "Quản trị (test màn VT)", "login": "admin_scr14_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_admin").id])],
        })
        cls.tech = cls.env["res.users"].create({
            "name": "Kỹ thuật (test màn VT)", "login": "tech_scr14_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })
        cls.ceo = cls.env["res.users"].create({
            "name": "CEO (test màn VT)", "login": "ceo_scr14_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.tpkd = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test màn VT)", "login": "tpkd_scr14_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_sales_manager").id])],
        })
        cls.ba = cls.env["res.users"].create({
            "name": "NV Kinh doanh (test màn VT)", "login": "ba_scr14_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ba").id])],
        })
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 40x40x1.8 (test màn VT)",
            "product_kind": "material",
        })

    def test_admin_can_create_material(self):
        """TC-INT-TestMaterialListAccess-001: Admin (action_dl_material_full)
        tạo được Vật tư."""
        material = self.env["product.product"].with_user(self.admin).create({
            "name": "Thép tấm 5mm (test màn VT 001)",
            "product_kind": "material",
        })
        self.assertTrue(material.id)

    def test_technician_can_create_material(self):
        """TC-INT-TestMaterialListAccess-002: Kỹ thuật
        (action_dl_material_tech) tạo được Vật tư."""
        material = self.env["product.product"].with_user(self.tech).create({
            "name": "Thép ống phi 21 (test màn VT 002)",
            "product_kind": "material",
        })
        self.assertTrue(material.id)

    def test_ceo_cannot_create_material(self):
        """TC-INT-TestMaterialListAccess-003: CEO
        (action_dl_material_view — chỉ xem) không tạo được Vật tư, chặn ở
        ACL (perm_create=0)."""
        with self.assertRaises(AccessError):
            self.env["product.product"].with_user(self.ceo).create({
                "name": "Thép lạ (test màn VT 003)", "product_kind": "material"})

    def test_sales_manager_cannot_create_material_despite_acl_allowing_create(self):
        """TC-INT-TestMaterialListAccess-004: Trưởng KD cũng ở
        action_dl_material_view (chỉ xem) nhưng ACL access_dl_product_prod_sm
        lại cho perm_create=1 — khác CEO. Cái CHẶN THẬT ở đây là ir.rule
        rule_product_sm_trading_write_create: domain chỉ khớp
        product_kind='trading', nên tạo Vật tư vẫn bị AccessError dù ACL
        không cấm. Cơ chế enforcement của màn Vật tư cho vai trò này là
        ir.rule, không phải ACL."""
        with self.assertRaises(AccessError):
            self.env["product.product"].with_user(self.tpkd).create({
                "name": "Thép lạ 2 (test màn VT 004)", "product_kind": "material"})

    def test_ba_has_no_material_action_in_groups(self):
        """TC-INT-TestMaterialListAccess-005: đúng như menus.xml ghi chú
        ("Không có dl_group_ba — BA/Sales không xem Vật tư"), BA không nằm
        trong groups_id của bất kỳ action Vật tư nào."""
        ba_group = self.env.ref("dl_base.dl_group_ba")
        for xmlid in (
            "dl_product.action_dl_material_full",
            "dl_product.action_dl_material_tech",
            "dl_product.action_dl_material_view",
        ):
            action = self.env.ref(xmlid)
            self.assertNotIn(
                ba_group, action.groups_id,
                "%s không được gồm nhóm BA" % xmlid)

    def test_ba_can_still_read_material_at_model_level(self):
        """TC-INT-TestMaterialListAccess-006: mặc dù không action/menu Vật tư
        nào cấp cho BA (ca 005), ACL product.product của BA vẫn perm_read=1
        không phân biệt product_kind — nghĩa là việc "BA không xem được Vật
        tư" là ẩn ở tầng menu/action, KHÔNG phải chặn đọc ở tầng model."""
        name = self.material.with_user(self.ba).read(["name"])[0]["name"]
        self.assertEqual(name, "Thép hộp 40x40x1.8 (test màn VT)")


@tagged("post_install", "-at_install", "dl_product")
class TestCategoryAccess(TransactionCase):
    """SCR-16 — Nhóm sản phẩm (product.category). Hai action:
    action_dl_category_full (Admin, Trưởng KD, Kỹ thuật — KHÔNG đồng nghĩa
    full CRUD như nhau cho cả ba, xem test_unlink_* bên dưới) và
    action_dl_category_view (BA, CEO — chỉ xem, qua ACL lõi
    access_product_category_user)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env["res.users"].create({
            "name": "Quản trị (test màn nhóm SP)", "login": "admin_scr16_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_admin").id])],
        })
        cls.tech = cls.env["res.users"].create({
            "name": "Kỹ thuật (test màn nhóm SP)", "login": "tech_scr16_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_tech").id])],
        })
        cls.tpkd = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test màn nhóm SP)",
            "login": "tpkd_scr16_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_sales_manager").id])],
        })
        cls.ceo = cls.env["res.users"].create({
            "name": "CEO (test màn nhóm SP)", "login": "ceo_scr16_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.ba = cls.env["res.users"].create({
            "name": "NV Kinh doanh (test màn nhóm SP)", "login": "ba_scr16_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ba").id])],
        })
        cls.material_root = cls.env.ref("dl_product.categ_root_material")
        cls.finished_root = cls.env.ref("dl_product.categ_root_finished")

    def test_technician_can_create_category_in_material_branch(self):
        """TC-INT-TestCategoryAccess-001: Kỹ thuật tạo được nhóm dưới nhánh
        Vật tư (rule_category_tech_material khớp domain)."""
        categ = self.env["product.category"].with_user(self.tech).create({
            "name": "Thép hộp (test màn nhóm SP 001)",
            "parent_id": self.material_root.id,
        })
        self.assertTrue(categ.id)

    def test_technician_cannot_create_category_in_finished_branch(self):
        """TC-INT-TestCategoryAccess-002: Kỹ thuật KHÔNG tạo được nhóm dưới
        nhánh Thành phẩm — ACL cho perm_create=1 nhưng ir.rule
        rule_category_tech_material chỉ khớp domain dl_branch='material'."""
        with self.assertRaises(AccessError):
            self.env["product.category"].with_user(self.tech).create({
                "name": "Máy bơm (test màn nhóm SP 002)",
                "parent_id": self.finished_root.id,
            })

    def test_sales_manager_can_create_category_in_finished_branch(self):
        """TC-INT-TestCategoryAccess-003: đối xứng ca 001 — Trưởng KD tạo
        được nhóm dưới nhánh Thành phẩm (rule_category_sm_finished)."""
        categ = self.env["product.category"].with_user(self.tpkd).create({
            "name": "Máy bơm nước (test màn nhóm SP 003)",
            "parent_id": self.finished_root.id,
        })
        self.assertTrue(categ.id)

    def test_sales_manager_cannot_create_category_in_material_branch(self):
        """TC-INT-TestCategoryAccess-004: đối xứng ca 002 — Trưởng KD KHÔNG
        tạo được nhóm dưới nhánh Vật tư."""
        with self.assertRaises(AccessError):
            self.env["product.category"].with_user(self.tpkd).create({
                "name": "Thép hộp 2 (test màn nhóm SP 004)",
                "parent_id": self.material_root.id,
            })

    def test_ceo_cannot_create_category(self):
        """TC-INT-TestCategoryAccess-005: CEO (action_dl_category_view — chỉ
        xem) không tạo được nhóm nào — không có dòng ACL riêng cho CEO trên
        product.category, chỉ thừa hưởng ACL lõi access_product_category_user
        (perm_create=0)."""
        with self.assertRaises(AccessError):
            self.env["product.category"].with_user(self.ceo).create({
                "name": "Nhóm lạ (test màn nhóm SP 005)",
                "parent_id": self.material_root.id,
            })

    def test_ba_cannot_create_category(self):
        """TC-INT-TestCategoryAccess-006: tương tự CEO, BA cũng chỉ thừa
        hưởng ACL lõi chỉ-đọc."""
        with self.assertRaises(AccessError):
            self.env["product.category"].with_user(self.ba).create({
                "name": "Nhóm lạ 2 (test màn nhóm SP 006)",
                "parent_id": self.material_root.id,
            })

    def test_admin_can_unlink_category(self):
        """TC-INT-TestCategoryAccess-007: Admin xoá được nhóm rỗng
        (access_dl_category_admin perm_unlink=1)."""
        categ = self.env["product.category"].create({
            "name": "Nhóm để xoá (test màn nhóm SP 007)",
            "parent_id": self.material_root.id,
        })
        categ.with_user(self.admin).unlink()
        self.assertFalse(categ.exists())

    def test_technician_cannot_unlink_category_despite_full_action(self):
        """TC-INT-TestCategoryAccess-008: mô tả FDS gọi
        action_dl_category_full là "full CRUD" cho Admin/Trưởng KD/Kỹ thuật —
        SAI LỆCH so với code thật: access_dl_category_tech có
        perm_unlink=0, nên Kỹ thuật tạo/sửa được nhóm nhánh của mình nhưng
        KHÔNG xoá được, dù dùng chung action với Admin."""
        categ = self.env["product.category"].create({
            "name": "Nhóm không xoá được (test màn nhóm SP 008)",
            "parent_id": self.material_root.id,
        })
        with self.assertRaises(AccessError):
            categ.with_user(self.tech).unlink()

    def test_sales_manager_cannot_unlink_category_despite_full_action(self):
        """TC-INT-TestCategoryAccess-009: đối xứng ca 008 cho Trưởng KD
        (access_dl_category_sm cũng perm_unlink=0)."""
        categ = self.env["product.category"].create({
            "name": "Nhóm không xoá được 2 (test màn nhóm SP 009)",
            "parent_id": self.finished_root.id,
        })
        with self.assertRaises(AccessError):
            categ.with_user(self.tpkd).unlink()


@tagged("post_install", "-at_install", "dl_product")
class TestMaterialSupplierPriceAccess(TransactionCase):
    """SCR-33 — Bảng giá Vật tư (product.supplierinfo, dl_product_kind=
    'material'). Hai action: action_dl_supplierinfo_material_full
    (Admin, Mua hàng — sửa) và action_dl_supplierinfo_material_view
    (CEO, Trưởng KD — chỉ xem). Không có ir.rule can thiệp thêm — chặn hoàn
    toàn ở tầng ACL."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env["res.users"].create({
            "name": "Quản trị (test màn giá VT)", "login": "admin_scr33_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_admin").id])],
        })
        cls.purchasing = cls.env["res.users"].create({
            "name": "Mua hàng (test màn giá VT)", "login": "muahang_scr33_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })
        cls.ceo = cls.env["res.users"].create({
            "name": "CEO (test màn giá VT)", "login": "ceo_scr33_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.tpkd = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test màn giá VT)",
            "login": "tpkd_scr33_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_sales_manager").id])],
        })
        cls.vendor = cls.env["res.partner"].create({
            "name": "Thép Hòa Phát (test màn giá VT)",
            "partner_role": "supplier", "mobile": "0900000301"})
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 50x50x2.0 (test màn giá VT)",
            "product_kind": "material",
        })

    def _row_vals(self, price=8000.0):
        return {
            "partner_id": self.vendor.id,
            "product_tmpl_id": self.material.product_tmpl_id.id,
            "product_id": self.material.id,
            "price": price,
            "date_start": "2026-08-01",
        }

    def test_purchasing_can_create_material_price_row(self):
        """TC-INT-TestMaterialSupplierPriceAccess-001: Mua hàng
        (action_dl_supplierinfo_material_full) tạo được dòng giá NCC cho Vật
        tư."""
        row = self.env["product.supplierinfo"].with_user(
            self.purchasing).create(self._row_vals())
        self.assertTrue(row.id)
        self.assertEqual(row.dl_product_kind, "material")

    def test_admin_can_create_material_price_row(self):
        """TC-INT-TestMaterialSupplierPriceAccess-002: Admin cũng tạo được
        (access_dl_supplierinfo_admin full)."""
        row = self.env["product.supplierinfo"].with_user(
            self.admin).create(self._row_vals(9000.0))
        self.assertTrue(row.id)

    def test_ceo_cannot_create_material_price_row(self):
        """TC-INT-TestMaterialSupplierPriceAccess-003: CEO
        (action_dl_supplierinfo_material_view — chỉ xem) không tạo được dòng
        giá (access_dl_supplierinfo_ceo perm_create=0)."""
        with self.assertRaises(AccessError):
            self.env["product.supplierinfo"].with_user(self.ceo).create(
                self._row_vals())

    def test_sales_manager_cannot_create_material_price_row(self):
        """TC-INT-TestMaterialSupplierPriceAccess-004: Trưởng KD tương tự CEO
        trên màn này — access_dl_supplierinfo_sm perm_create=0 (khác hẳn
        quyền ghi product.product mà Trưởng KD có ở màn Sản phẩm)."""
        with self.assertRaises(AccessError):
            self.env["product.supplierinfo"].with_user(self.tpkd).create(
                self._row_vals())

    def test_ceo_cannot_write_existing_material_price_row(self):
        """TC-INT-TestMaterialSupplierPriceAccess-005: CEO cũng không sửa
        được dòng giá đã có (perm_write=0), chỉ đọc."""
        row = self.env["product.supplierinfo"].create(self._row_vals())
        with self.assertRaises(AccessError):
            row.with_user(self.ceo).write({"price": 10000.0})
        self.assertEqual(
            row.with_user(self.ceo).read(["price"])[0]["price"], 8000.0)

    def test_material_price_domain_excludes_trading(self):
        """TC-INT-TestMaterialSupplierPriceAccess-006: domain của action
        action_dl_supplierinfo_material_full/_view (dl_product_kind='material')
        thực sự loại được dòng giá của SP thương mại — kiểm bằng domain đọc
        thẳng từ action, không chép tay."""
        trading = self.env["product.product"].create({
            "name": "Máy bơm nước 1HP (test màn giá VT 006)",
            "product_kind": "trading",
        })
        trading_row = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": trading.product_tmpl_id.id,
            "product_id": trading.id,
            "price": 200000.0,
            "date_start": "2026-08-01",
        })
        material_row = self.env["product.supplierinfo"].create(self._row_vals())

        domain = _domain_of(self.env, "dl_product.action_dl_supplierinfo_material_full")
        found = self.env["product.supplierinfo"].search(domain).ids

        self.assertIn(material_row.id, found)
        self.assertNotIn(trading_row.id, found)


@tagged("post_install", "-at_install", "dl_product")
class TestTradingPriceListAccess(TransactionCase):
    """SCR-34 — Bảng giá SP thương mại (product.product,
    action_dl_product_pricing, domain product_kind='trading'). Nhóm:
    Admin, Mua hàng, CEO, Trưởng KD."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purchasing = cls.env["res.users"].create({
            "name": "Mua hàng (test bảng giá SP)", "login": "muahang_scr34_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })
        cls.ceo = cls.env["res.users"].create({
            "name": "CEO (test bảng giá SP)", "login": "ceo_scr34_test",
            "groups_id": [(6, 0, [cls.env.ref("dl_base.dl_group_ceo").id])],
        })
        cls.tpkd = cls.env["res.users"].create({
            "name": "Trưởng phòng KD (test bảng giá SP)",
            "login": "tpkd_scr34_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_sales_manager").id])],
        })
        cls.trading = cls.env["product.product"].create({
            "name": "Máy khoan bê tông (test bảng giá SP)",
            "product_kind": "trading",
        })

    def test_domain_shows_only_trading_kind(self):
        """TC-INT-TestTradingPriceListAccess-001: domain thật của
        action_dl_product_pricing chỉ lọc product_kind='trading' — SP gia
        công và Vật tư không lọt vào."""
        manufactured = self.env["product.product"].create({
            "name": "Khung máy CNC (test bảng giá SP 001)",
            "product_kind": "manufactured",
        })
        material = self.env["product.product"].create({
            "name": "Thép tấm (test bảng giá SP 001)",
            "product_kind": "material",
        })
        domain = _domain_of(self.env, "dl_product.action_dl_product_pricing")
        found = self.env["product.product"].search(
            domain + [("id", "in", [
                self.trading.id, manufactured.id, material.id])]).ids

        self.assertEqual(found, [self.trading.id])

    def test_purchasing_can_write_trading_product(self):
        """TC-INT-TestTradingPriceListAccess-002: Mua hàng ghi được SP
        thương mại (ACL perm_write=1 + ir.rule
        rule_product_purchasing_cost_write_only khớp domain trading/material)
        — action context chỉ khoá create/delete, không khoá edit."""
        self.trading.with_user(self.purchasing).write({
            "dlm_waste_rate": 0.0})
        # Không raise là đạt; đọc lại để chắc chắn đã thực sự ghi qua ORM.
        self.assertEqual(self.trading.dlm_waste_rate, 0.0)

    def test_purchasing_cannot_create_trading_product(self):
        """TC-INT-TestTradingPriceListAccess-003: action context đặt
        create=False khớp đúng ACL — Mua hàng perm_create=0 trên
        product.product."""
        with self.assertRaises(AccessError):
            self.env["product.product"].with_user(self.purchasing).create({
                "name": "SP thương mại lạ (test bảng giá SP 003)",
                "product_kind": "trading",
            })

    def test_ceo_cannot_write_trading_product(self):
        """TC-INT-TestTradingPriceListAccess-004: CEO thực sự chỉ xem trên
        màn này (ACL perm_write=0) — đúng với mô tả "chỉ xem" trong comment
        product_pricing_views.xml. Dùng field `dlm_waste_rate` (không nằm
        trong _DLM_PROTECTED_FIELDS) để canh đúng lớp ACL, tránh lẫn với
        guard field riêng của `list_price` (xem ca 005)."""
        with self.assertRaises(AccessError):
            self.trading.with_user(self.ceo).write({"dlm_waste_rate": 2.0})

    def test_sales_manager_can_write_trading_product_despite_view_label(self):
        """TC-INT-TestTradingPriceListAccess-005: sai lệch tài liệu — comment
        trong product_pricing_views.xml xếp Trưởng KD vào nhóm "chỉ xem (ACL
        read-only)" cùng CEO/Kế toán, nhưng thực tế Trưởng KD có
        perm_write=1 trên product.product + ir.rule
        rule_product_sm_trading_write_create khớp đúng product_kind='trading'
        — nên vẫn SỬA ĐƯỢC SP thương mại qua màn này (đây chính là quyền
        "chốt giá bán" đã được test_trading_ownership canh kỹ). Ca này canh
        cho đúng cái tên field khác (dlm_waste_rate không áp dụng cho
        trading) — dùng list_price qua đường mua-trước-bán-sau."""
        self.env["product.supplierinfo"].create({
            "partner_id": self.env["res.partner"].create({
                "name": "NCC máy khoan (test bảng giá SP 005)",
                "partner_role": "supplier", "mobile": "0900000302"}).id,
            "product_tmpl_id": self.trading.product_tmpl_id.id,
            "product_id": self.trading.id,
            "price": 100000.0,
            "date_start": "2026-08-01",
        }).action_approve()
        self.trading.invalidate_recordset()

        self.trading.with_user(self.tpkd).write({"list_price": 150000.0})

        self.assertEqual(self.trading.list_price, 150000.0)


@tagged("post_install", "-at_install", "dl_product")
class TestMaterialsAwaitingPricingDomain(TransactionCase):
    """SCR-35 — Vật tư chờ định giá (action_dl_material_needs_price). Không
    phải model riêng: domain lọc product.product theo product_kind='material'
    + dlm_supplier_price_state != 'applied' + dlm_lifecycle_state !=
    'obsolete'. Cơ chế "chỉ xem" của màn này nằm ở arch view
    (view_dl_material_needs_price_tree có create="0" edit="0"), không phải
    ACL/ir.rule — Mua hàng vẫn ghi được product.product bình thường qua nơi
    khác (xem TestTradingPriceListAccess.test_purchasing_can_write_trading_product)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purchasing = cls.env["res.users"].create({
            "name": "Mua hàng (test VT chờ định giá)",
            "login": "muahang_scr35_test",
            "groups_id": [(6, 0, [
                cls.env.ref("dl_base.dl_group_purchasing").id])],
        })
        cls.vendor = cls.env["res.partner"].create({
            "name": "NCC vật tư chờ giá (test VT chờ định giá)",
            "partner_role": "supplier", "mobile": "0900000401"})

    def _domain(self):
        return _domain_of(self.env, "dl_product.action_dl_material_needs_price")

    def _search(self, ids):
        return set(self.env["product.product"].search(
            self._domain() + [("id", "in", ids)]).ids)

    def test_material_with_no_supplier_price_is_included(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-001: Vật tư chưa có
        dòng giá NCC nào (dlm_supplier_price_state='none') phải nằm trong
        worklist."""
        material = self.env["product.product"].create({
            "name": "Thép ống phi 27 (test VT chờ định giá 001)",
            "product_kind": "material",
        })
        self.assertEqual(material.dlm_supplier_price_state, "none")
        self.assertEqual(self._search([material.id]), {material.id})

    def test_material_with_pending_price_is_included(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-002: Vật tư đã có dòng
        giá nhưng CHƯA áp dụng (state='pending') vẫn nằm trong worklist —
        domain chỉ loại 'applied', không loại 'pending'."""
        material = self.env["product.product"].create({
            "name": "Thép hộp 60x60x2.0 (test VT chờ định giá 002)",
            "product_kind": "material",
        })
        self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": material.product_tmpl_id.id,
            "product_id": material.id,
            "price": 12000.0,
            "date_start": "2026-08-01",
        })
        material.invalidate_recordset()
        self.assertEqual(material.dlm_supplier_price_state, "pending")
        self.assertEqual(self._search([material.id]), {material.id})

    def test_material_with_applied_price_is_excluded(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-003: Vật tư đã có giá
        NCC đang áp dụng (state='applied') phải BIẾN MẤT khỏi worklist —
        đúng ý nghĩa "chờ định giá" đã xong việc."""
        material = self.env["product.product"].create({
            "name": "Thép tấm 3mm (test VT chờ định giá 003)",
            "product_kind": "material",
        })
        seller = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id,
            "product_tmpl_id": material.product_tmpl_id.id,
            "product_id": material.id,
            "price": 15000.0,
            "date_start": "2026-08-01",
        })
        seller.action_approve()
        material.invalidate_recordset()
        self.assertEqual(material.dlm_supplier_price_state, "applied")
        self.assertEqual(self._search([material.id]), set())

    def test_obsolete_material_is_excluded_even_without_price(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-004: Vật tư Ngừng sử
        dụng bị loại khỏi worklist dù chưa có giá NCC — không còn ý nghĩa
        "cần định giá" cho vật tư đã ngừng dùng."""
        material = self.env["product.product"].create({
            "name": "Thép cũ ngừng dùng (test VT chờ định giá 004)",
            "product_kind": "material",
            "dlm_lifecycle_state": "obsolete",
        })
        self.assertEqual(self._search([material.id]), set())

    def test_trading_product_is_excluded_regardless_of_price_state(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-005: domain lọc
        product_kind='material' — SP thương mại chưa có giá NCC KHÔNG lọt
        vào (đó là việc của màn Bảng giá SP thương mại, SCR-34)."""
        trading = self.env["product.product"].create({
            "name": "Máy hàn que (test VT chờ định giá 005)",
            "product_kind": "trading",
        })
        self.assertEqual(trading.dlm_supplier_price_state, "none")
        self.assertEqual(self._search([trading.id]), set())

    def test_view_enforces_readonly_via_arch_not_acl(self):
        """TC-INT-TestMaterialsAwaitingPricingDomain-006: cơ chế "chỉ xem"
        của màn này nằm ở arch của view_dl_material_needs_price_tree
        (create="0" edit="0"), không phải ACL/ir.rule — ACL/rule của Mua
        hàng trên product.product vẫn cho ghi (ca
        TestTradingPriceListAccess.test_purchasing_can_write_trading_product
        đã canh phần đó); ca này canh đúng phần khai ở arch."""
        view = self.env.ref("dl_product.view_dl_material_needs_price_tree")
        root = etree.fromstring(view.arch_db)
        self.assertEqual(root.tag, "tree")
        self.assertEqual(root.get("create"), "0")
        self.assertEqual(root.get("edit"), "0")
