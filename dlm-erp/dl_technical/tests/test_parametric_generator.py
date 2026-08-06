"""Đợt 4 — bộ sinh định mức tham số (thiết kế Thiet_ke_xu_ly_dong_RFQ_ky_thuat
§7.4a–d).

Kiểm: chữ ký tham số chuẩn hoá, cổng chất lượng mẫu (chưa duyệt / thiếu tham
số / ngoài miền), và ánh xạ tuyến tính `target = factor × tham số + offset`
sinh ra một BOM báo giá (instance) — KHÔNG bao giờ là phiên bản hiện hành.

File này từng chỉ tồn tại ở máy local (chưa push) nên bị mất khi pull nhánh;
khôi phục lại vì `tests/__init__.py` vẫn import và feature vẫn chạy.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical")
class TestParametricGenerator(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bom = cls.env["dl.bom"]
        cls.finished_root = cls.env.ref("dl_product.categ_root_finished")
        cls.categ = cls.env["product.category"].create({
            "name": "Bàn thép khung hộp (test §7.4)",
            "parent_id": cls.finished_root.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Bàn thép 1200x800 (test)",
            "categ_id": cls.categ.id,
            "product_kind": "manufactured",
        })
        cls.material = cls.env["product.product"].create({
            "name": "Thép hộp 40x40 (test §7.4)",
            "product_kind": "material",
        })

    def _make_template(self, status="confirmed"):
        template = self.env["dl.bom.template"].create({
            "name": "Mẫu Bàn thép (test)",
            "product_category_id": self.categ.id,
            "line_ids": [(0, 0, {
                "material_id": self.material.id,
                "quantity": 1.0,
            })],
        })
        if status in ("confirmed", "locked"):
            template.action_confirm()
        if status == "locked":
            template.action_lock()
        return template

    # ------------------------------------------------------------------
    # Chữ ký tham số — nền của đường A (khớp cấu hình cũ) và catalog
    # ------------------------------------------------------------------
    def test_param_signature_normalized(self):
        sig = self.Bom._dlm_param_signature({"D": 1400, "R": 830})
        self.assertEqual(sig, "D=1400|R=830", "Khoá sắp alphabet, số nguyên bỏ '.0'")
        # Không phụ thuộc thứ tự khai báo + làm tròn 1 chữ số thập phân.
        self.assertEqual(
            self.Bom._dlm_param_signature({"R": 830.0, "D": 1400.04}),
            "D=1400|R=830")

    # ------------------------------------------------------------------
    # Cổng chất lượng mẫu
    # ------------------------------------------------------------------
    def test_generate_requires_confirmed_template(self):
        template = self._make_template(status="draft")
        template.param_ids = [(0, 0, {
            "code": "L", "name": "Chiều dài", "required": True})]
        with self.assertRaises(UserError):
            template.generate_instance(self.product, {"L": 1000})

    def test_generate_requires_params(self):
        template = self._make_template()   # confirmed nhưng CHƯA khai tham số
        with self.assertRaises(UserError):
            template.generate_instance(self.product, {"L": 1000})

    def test_missing_required_param_raises(self):
        template = self._make_template()
        template.param_ids = [(0, 0, {
            "code": "L", "name": "Chiều dài", "required": True})]
        with self.assertRaises(UserError):
            template.generate_instance(self.product, {})

    def test_param_out_of_range_raises(self):
        template = self._make_template()
        template.param_ids = [(0, 0, {
            "code": "L", "name": "Chiều dài", "required": True,
            "value_min": 100, "value_max": 2000})]
        with self.assertRaises(UserError):
            template.generate_instance(self.product, {"L": 5000})

    # ------------------------------------------------------------------
    # Ánh xạ tuyến tính → instance
    # ------------------------------------------------------------------
    def test_generate_instance_applies_linear_map(self):
        template = self._make_template()
        param = self.env["dl.bom.template.param"].create({
            "bom_template_id": template.id,
            "code": "N", "name": "Số nan", "required": True})
        self.env["dl.bom.template.line.param.map"].create({
            "template_line_id": template.line_ids[0].id,
            "param_id": param.id,
            "target_field": "quantity",
            "factor": 2.0, "offset": 1.0,
        })

        instance = template.generate_instance(self.product, {"N": 3})

        self.assertEqual(instance.bom_type, "quotation")
        self.assertEqual(instance.status, "draft")
        self.assertTrue(instance.is_rfq_provisional)
        self.assertFalse(instance.is_current, "Instance không bao giờ là hiện hành")
        self.assertEqual(instance.source_template_id, template)
        self.assertEqual(instance.param_signature, "N=3")
        self.assertEqual(
            instance.line_ids[0].quantity, 7.0,
            "quantity = factor×N + offset = 2×3 + 1")
