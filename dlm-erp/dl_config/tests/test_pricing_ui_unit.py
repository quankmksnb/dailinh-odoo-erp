# -*- coding: utf-8 -*-
"""Unit test L2 (TransactionCase, dùng DB thật) cho dl.pricing.ui — cầu nối
dữ liệu cho màn OWL "Cấu hình Báo giá". Sheet nguồn: DlPricingUi trong
Report_5_1_UnitTests_L1.xlsx (đặt ở đây, không phải test-DB-free, vì
get_health()/get_bootstrap() đụng self.env.search/self.env.company thật).

Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage)."""
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_config")
class TestPricingUi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Ui = cls.env["dl.pricing.ui"]
        # Không active profit rule nào tồn tại theo mặc định trong DB test —
        # nhưng để chắc chắn (không lệ thuộc data demo/seed khác), hết hiệu
        # lực mọi profit rule đang active trước khi test.
        cls.env["dl.pricing.profit.rule"].sudo().search([
            ("state", "=", "active")]).sudo().write({"state": "expired"})

    def test_no_active_profit_rule_returns_block_item(self):
        """TC-UNIT-DlPricingUi-001"""
        items = self.Ui.get_health()
        block_texts = [i["text"] for i in items if i["level"] == "block"]
        self.assertTrue(
            any("lợi nhuận" in t for t in block_texts),
            "Phải cảnh báo thiếu chính sách lợi nhuận khi không có rule active",
        )

    def test_operation_used_on_confirmed_bom_without_price_returns_block_item(self):
        """TC-UNIT-DlPricingUi-002"""
        # Có 1 profit rule active để cô lập đúng nhánh đang test (tránh lẫn
        # với cảnh báo ở TC-001).
        self.env["dl.pricing.profit.rule"].create({
            "target_markup": 20.0, "min_markup": 5.0, "state": "active",
        })
        operation = self.env["dl.pricing.operation"].create({
            "name": "Công đoạn chưa có giá (test)", "code": "TESTNOPRICE",
        })
        material = self.env["product.product"].create({
            "name": "Vật tư test DlPricingUi", "product_kind": "material",
        })
        product = self.env["product.product"].create({
            "name": "SP test DlPricingUi", "product_kind": "manufactured",
        })
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "quotation",
            "product_qty": 1.0,
            "line_ids": [(0, 0, {"material_id": material.id, "quantity": 1.0})],
            "operation_line_ids": [(0, 0, {"operation_id": operation.id})],
        })
        bom.action_confirm()
        items = self.Ui.get_health()
        block_texts = [i["text"] for i in items if i["level"] == "block"]
        self.assertTrue(
            any(operation.display_name in t for t in block_texts),
            "Phải nêu đúng tên công đoạn chưa có đơn giá trong cảnh báo",
        )

    def test_get_bootstrap_perms_differ_by_role(self):
        """TC-UNIT-DlPricingUi-003"""
        tech_user = self.env["res.users"].create({
            "name": "KTV test DlPricingUi", "login": "ktv_pricingui_test",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("dl_base.dl_group_tech").id,
            ])],
        })
        ceo_user = self.env["res.users"].create({
            "name": "CEO test DlPricingUi", "login": "ceo_pricingui_test",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("dl_base.dl_group_ceo").id,
            ])],
        })
        tech_perms = self.Ui.with_user(tech_user).get_bootstrap()["perms"]
        ceo_perms = self.Ui.with_user(ceo_user).get_bootstrap()["perms"]
        self.assertTrue(tech_perms["waste"])
        self.assertFalse(tech_perms["profit"])
        self.assertFalse(tech_perms["discount"])
        self.assertTrue(ceo_perms["profit"])
        self.assertTrue(ceo_perms["discount"])
        self.assertTrue(ceo_perms["self_approve"])
