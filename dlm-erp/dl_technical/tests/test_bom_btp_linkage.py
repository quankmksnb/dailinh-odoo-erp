"""Test chấp nhận LKT-01..16 — Thiet_ke_lien_ket_ky_thuat_BOM_vat_tu_BTP_ban_ve
§15.

Bao phủ liên kết khối Kỹ thuật: giá vốn BTP dùng chung một helper (LK-02), tự
cập nhật khi BOM con đổi (LK-16), chặn định mức vòng lặp (LK-01), wizard tạo
BTP (P3), vệ sinh dữ liệu tạm (LK-07), storable (LK-14), siết mẫu (LK-03),
guard danh mục (LK-11/13), chính sách & neo bản vẽ (LK-05/06/15), banner cấu
phần chưa định giá (LK-09/10).
"""

import base64

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical")
class TestBomBtpLinkage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bom = cls.env["dl.bom"]
        cls.Product = cls.env["product.product"]
        cls.material_root = cls.env.ref("dl_product.categ_root_material")
        cls.finished_root = cls.env.ref("dl_product.categ_root_finished")
        cls.btp_categ = cls.env["product.category"].create({
            "name": "Bán thành phẩm (test LKT)",
            "parent_id": cls.material_root.id,
        })
        cls.finished_categ = cls.env["product.category"].create({
            "name": "Bàn thép (test LKT)",
            "parent_id": cls.finished_root.id,
        })
        cls.supplier = cls.env["res.partner"].create({
            "name": "NCC test LKT", "partner_role": "supplier"})
        # Vật tư thô "trung tính" cho các dòng không quan tâm giá.
        cls.raw_plain = cls.env["product.product"].create({
            "name": "Thép hộp trơn (LKT)", "product_kind": "material"})

    # ------------------------------------------------------------------ helpers
    def _mk_product(self, kind, name, categ=None):
        vals = {"name": name, "product_kind": kind}
        if categ is not None:
            vals["categ_id"] = categ.id
        return self.env["product.product"].create(vals)

    def _apply_price(self, product, price):
        """Tạo một bảng giá NCC ĐÃ DUYỆT & ĐANG ÁP DỤNG cho vật tư (để BOM con
        có total_material_cost khác 0)."""
        return self.env["product.supplierinfo"].create({
            "partner_id": self.supplier.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "price": price,
            "date_start": fields.Date.today(),
            "approval_state": "approved",
            "is_applied": True,
        })

    def _mk_bom(self, product, bom_type="template", material=None, confirm=False):
        bom = self.Bom.create({
            "product_id": product.id,
            "bom_type": bom_type,
            "line_ids": [(0, 0, {
                "material_id": (material or self.raw_plain).id,
                "quantity": 1.0,
            })],
        })
        if confirm:
            bom.action_confirm()
        return bom

    def _mk_attachment(self, name):
        return self.env["ir.attachment"].create({
            "name": name,
            "datas": base64.b64encode(b"%PDF-1.4 test drawing").decode(),
        })

    # ================================================================ LKT-01/02
    def test_lkt01_standard_child_bom_prefers_template(self):
        """BTP có cả BOM template (is_current) lẫn BOM báo giá version cao hơn →
        _standard_child_bom trả TEMPLATE; snapshot dòng cha lấy giá vốn template."""
        btp = self._mk_product("material_processed", "BTP khung LKT01", self.btp_categ)
        mat_std = self._mk_product("material", "Thép chuẩn LKT01")
        mat_quote = self._mk_product("material", "Thép báo giá LKT01")
        self._apply_price(mat_std, 100.0)
        self._apply_price(mat_quote, 999.0)

        template = self._mk_bom(btp, "template", material=mat_std, confirm=True)
        quotation = self._mk_bom(btp, "quotation", material=mat_quote, confirm=True)

        self.assertTrue(template.is_current)
        self.assertFalse(quotation.is_current)
        self.assertEqual(self.Bom._standard_child_bom(btp), template)

        parent = self._mk_bom(
            self._mk_product("manufactured", "Bàn LKT01", self.finished_categ),
            "template", material=btp)
        line = parent.line_ids
        self.assertEqual(
            line.price_snapshot, 100.0,
            "Giá vốn BTP phải lấy từ BOM chuẩn (100), không phải BOM báo giá (999)")

    def test_lkt02_fallback_to_quotation_when_no_template(self):
        """BTP chỉ có BOM báo giá (chưa có template) → fallback trả báo giá."""
        btp = self._mk_product("material_processed", "BTP chỉ báo giá LKT02", self.btp_categ)
        quotation = self._mk_bom(btp, "quotation", confirm=True)
        self.assertEqual(self.Bom._standard_child_bom(btp), quotation)

    # =================================================================== LKT-03
    def test_lkt03_parent_snapshot_follows_child_cost(self):
        """Đổi tổng chi phí BOM con của BTP → snapshot BOM cha tự cập nhật (P10)."""
        btp = self._mk_product("material_processed", "BTP LKT03", self.btp_categ)
        mat = self._mk_product("material", "Thép LKT03")
        self._apply_price(mat, 100.0)
        template = self._mk_bom(btp, "template", material=mat, confirm=True)
        self.assertEqual(template.total_material_cost, 100.0)

        parent = self._mk_bom(
            self._mk_product("manufactured", "Bàn LKT03", self.finished_categ),
            "template", material=btp)
        self.assertEqual(parent.line_ids.price_snapshot, 100.0)

        # Thêm 1 dòng vào BOM con confirmed → tổng chi phí 100 → 200.
        template.write({"line_ids": [(0, 0, {
            "material_id": mat.id, "quantity": 1.0})]})
        self.assertEqual(template.total_material_cost, 200.0)

        parent.line_ids.invalidate_recordset(["price_snapshot"])
        self.assertEqual(
            parent.line_ids.price_snapshot, 200.0,
            "Snapshot BOM cha phải lan theo tổng chi phí BOM con (LK-16)")

    # =================================================================== LKT-04
    def test_lkt04_cycle_blocked(self):
        """Dòng BOM trỏ BTP mà BTP (gián tiếp) dùng lại SP cha → ValidationError."""
        btp_a = self._mk_product("material_processed", "BTP A LKT04", self.btp_categ)
        btp_b = self._mk_product("material_processed", "BTP B LKT04", self.btp_categ)
        # B làm từ A.
        self._mk_bom(btp_b, "template", material=btp_a, confirm=True)
        # A làm từ B → A dùng B, B dùng A ⇒ vòng lặp.
        with self.assertRaises(ValidationError):
            self._mk_bom(btp_a, "template", material=btp_b)

    # ================================================================ LKT-05/06
    def test_lkt05_wizard_blocks_exact_duplicate_name(self):
        existing = self._mk_product(
            "material_processed", "Khung hàn LKT05", self.btp_categ)
        self.assertFalse(existing.is_rfq_provisional)
        parent = self._mk_bom(
            self._mk_product("manufactured", "Bàn LKT05", self.finished_categ),
            "template")
        wizard = self.env["dl.bom.create.btp.wizard"].create({
            "bom_id": parent.id,
            "name": "Khung hàn LKT05",
            "category_id": self.btp_categ.id,
        })
        with self.assertRaises(UserError):
            wizard.action_create()

    def test_lkt06_wizard_creates_btp_tree(self):
        parent = self._mk_bom(
            self._mk_product("manufactured", "Bàn LKT06", self.finished_categ),
            "template")
        self.assertEqual(parent.status, "draft")
        wizard = self.env["dl.bom.create.btp.wizard"].create({
            "bom_id": parent.id,
            "name": "Khung hàn mới LKT06",
            "category_id": self.btp_categ.id,
            "quantity": 2.0,
            "init_mode": "empty",
        })
        action = wizard.action_create()

        self.assertEqual(action["res_model"], "dl.bom")
        child = self.Bom.browse(action["res_id"])
        self.assertEqual(child.bom_type, "template")
        self.assertEqual(child.status, "draft")
        prod = child.product_id
        self.assertEqual(prod.product_kind, "material_processed")
        self.assertEqual(prod.dlm_lifecycle_state, "draft")
        self.assertEqual(prod.categ_id, self.btp_categ)

        new_line = parent.line_ids.filtered(lambda l: l.material_id == prod)
        self.assertEqual(len(new_line), 1)
        self.assertEqual(new_line.quantity, 2.0)

    # ================================================================ LKT-07/08
    def test_lkt08_cleanup_handles_material_and_btp(self):
        """Vệ sinh dữ liệu tạm mở rộng cho CẢ vật tư thô lẫn BTP (LK-07): dọn
        bản mồ côi, giữ bản còn được bản ghi khác trỏ tới."""
        # Vật tư thô tạm KHÔNG được dùng → phải bị dọn.
        orphan_mat = self.Product.create({
            "name": "Vật tư tạm mồ côi LKT08",
            "product_kind": "material",
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
        })
        # BTP tạm ĐƯỢC một BOM trỏ tới (material_id) → phải GIỮ.
        used_btp = self.Product.create({
            "name": "BTP tạm được dùng LKT08",
            "product_kind": "material_processed",
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
        })
        self.Bom.create({
            "product_id": self._mk_product(
                "manufactured", "Bàn dùng BTP LKT08", self.finished_categ).id,
            "bom_type": "template",
            "line_ids": [(0, 0, {"material_id": used_btp.id, "quantity": 1.0})],
        })

        orphan_id, used_id = orphan_mat.id, used_btp.id
        (orphan_mat | used_btp)._cleanup_unused_rfq_provisional()

        self.assertFalse(
            self.Product.browse(orphan_id).exists(),
            "Vật tư thô tạm mồ côi phải bị dọn (LK-07 mở rộng cho material)")
        self.assertTrue(
            self.Product.browse(used_id).exists(),
            "BTP tạm còn được BOM khác trỏ tới thì phải giữ")

    # =================================================================== LKT-09
    def test_lkt09_created_products_are_storable(self):
        for kind in ("manufactured", "material", "material_processed", "trading"):
            product = self.Product.create({
                "name": "Storable %s LKT09" % kind, "product_kind": kind})
            self.assertEqual(
                product.detailed_type, "product",
                "SP kind=%s tạo qua app phải storable (mở đường Kho)" % kind)

    # =================================================================== LKT-10
    def test_lkt10_copy_from_draft_template_blocked(self):
        prod = self._mk_product("manufactured", "Bàn LKT10", self.finished_categ)
        bom = self._mk_bom(prod, "template")   # đích, còn Nháp
        draft_template = self.env["dl.bom.template"].create({
            "name": "Mẫu Nháp LKT10",
            "product_category_id": self.finished_categ.id,
            "line_ids": [(0, 0, {"material_id": self.raw_plain.id, "quantity": 1.0})],
        })
        self.assertEqual(draft_template.status, "draft")
        wizard = self.env["dl.bom.from.template.wizard"].create({
            "bom_id": bom.id,
            "template_id": draft_template.id,
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()

    # =================================================================== LKT-11
    def test_lkt11_archive_category_with_active_product_blocked(self):
        categ = self.env["product.category"].create({
            "name": "Nhóm còn SP active LKT11",
            "parent_id": self.material_root.id,
        })
        product = self._mk_product("material", "Vật tư active LKT11", categ)
        product.dlm_lifecycle_state = "active"
        with self.assertRaises(ValidationError):
            categ.active = False

    # =================================================================== LKT-12
    def test_lkt12_tech_can_create_material_branch_only(self):
        tech_user = self.env["res.users"].create({
            "name": "KTV LKT12",
            "login": "ktv_lkt12",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("dl_base.dl_group_tech").id,
            ])],
        })
        Category = self.env["product.category"].with_user(tech_user)
        # Nhánh Vật tư — được tạo.
        mat_cat = Category.create({
            "name": "KTV nhóm vật tư LKT12", "parent_id": self.material_root.id})
        self.assertTrue(mat_cat.exists())
        self.assertEqual(mat_cat.dl_branch, "material")
        # Nhánh Thành phẩm — record rule chặn.
        with self.assertRaises(AccessError):
            Category.create({
                "name": "KTV nhóm TP LKT12", "parent_id": self.finished_root.id})

    # =================================================================== LKT-13
    def test_lkt13_depth_warning_soft(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "dl_product.category_max_depth", "1")
        c1 = self.env["product.category"].create({"name": "c1 LKT13"})
        c2 = self.env["product.category"].create({
            "name": "c2 LKT13", "parent_id": c1.id})

        deep = self.env["product.category"].new({"parent_id": c2.id})
        res = deep._onchange_dlm_depth_warning()
        self.assertTrue(res and res.get("warning"), "Nhóm quá sâu phải cảnh báo")

        shallow = self.env["product.category"].new({"parent_id": c1.id})
        self.assertFalse(
            shallow._onchange_dlm_depth_warning(),
            "Nhóm trong ngưỡng không cảnh báo")

    # =================================================================== LKT-14
    def test_lkt14_drawing_version_notifies_unlocked_bom(self):
        product = self._mk_product("material_processed", "BTP có bản vẽ LKT14", self.btp_categ)
        draft_bom = self._mk_bom(product, "template")           # còn Nháp
        locked_bom = self._mk_bom(product, "template", confirm=True)
        locked_bom.action_lock()

        Drawing = self.env["dl.drawing"]
        d1 = Drawing.create({
            "name": "BV LKT14 v1", "product_id": product.id, "version": 1,
            "attachment_id": self._mk_attachment("bv1.pdf").id})
        d1.action_confirm()
        d2 = Drawing.create({
            "name": "BV LKT14 v2", "product_id": product.id, "version": 2,
            "attachment_id": self._mk_attachment("bv2.pdf").id})
        d2.action_confirm()

        Activity = self.env["mail.activity"]
        self.assertTrue(
            Activity.search_count([
                ("res_model", "=", "dl.bom"), ("res_id", "=", draft_bom.id)]),
            "BOM chưa khóa phải được nhắc rà theo bản vẽ mới (LK-15)")
        self.assertFalse(
            Activity.search_count([
                ("res_model", "=", "dl.bom"), ("res_id", "=", locked_bom.id)]),
            "BOM đã khóa không bị đụng (ranh giới snapshot)")

    def test_lkt13b_drawing_domain_blocks_raw_material(self):
        """LKT-13(§) — gắn bản vẽ cho vật tư thô bị chặn cứng (LK-05)."""
        with self.assertRaises(ValidationError):
            self.env["dl.drawing"].create({
                "name": "BV sai loại", "product_id": self.raw_plain.id})

    # =================================================================== LKT-15
    def test_lkt15_drawing_policy_block_then_warn(self):
        Param = self.env["ir.config_parameter"].sudo()
        product = self._mk_product("manufactured", "Bàn cần bản vẽ LKT15", self.finished_categ)
        bom = self._mk_bom(product, "template")

        Param.set_param("dl_technical.require_drawing_for_finished", "block")
        with self.assertRaises(UserError):
            bom.action_confirm()

        Param.set_param("dl_technical.require_drawing_for_finished", "warn")
        bom.action_confirm()
        self.assertEqual(bom.status, "confirmed")

    # =================================================================== LKT-16
    def test_lkt16_unpriced_components_flag(self):
        """BOM có vật tư chưa giá / BTP chưa BOM chuẩn → cờ + tên đúng."""
        product = self._mk_product("manufactured", "Bàn LKT16", self.finished_categ)
        unpriced_mat = self._mk_product("material", "Vật tư chưa giá LKT16")
        btp_no_bom = self._mk_product("material_processed", "BTP chưa BOM LKT16", self.btp_categ)
        bom = self.Bom.create({
            "product_id": product.id,
            "bom_type": "template",
            "line_ids": [
                (0, 0, {"material_id": unpriced_mat.id, "quantity": 1.0}),
                (0, 0, {"material_id": btp_no_bom.id, "quantity": 1.0}),
            ],
        })
        self.assertTrue(bom.dlm_has_unpriced_component)
        names = bom.dlm_unpriced_component_names or ""
        self.assertIn("Vật tư chưa giá LKT16", names)
        self.assertIn("BTP chưa BOM LKT16", names)
