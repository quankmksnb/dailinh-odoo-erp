from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationPricing(TransactionCase):
    """Kiểm thử chấp nhận P0+P1 (đặc tả §13/§17.8): tính giá nền, markup, chiết
    khấu/VAT theo cấu hình, snapshot bất biến, và định tuyến phê duyệt."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env["product.product"]
        cls.Bom = cls.env["dl.bom"]
        cls.Rfq = cls.env["dl.quotation.request"]
        cls.Quotation = cls.env["dl.quotation"]

        cls.supplier = cls.env["res.partner"].create(
            {"name": "NCC Test", "partner_role": "supplier"})
        cls.customer = cls.env["res.partner"].create(
            {"name": "KH Test", "partner_role": "customer"})

        # Vật tư thô R: bảng giá đã duyệt + đang áp dụng, giá 100.
        cls.raw = cls.Product.create({"name": "Thép R", "product_kind": "material"})
        cls.raw_seller = cls.env["product.supplierinfo"].create({
            "partner_id": cls.supplier.id,
            "product_tmpl_id": cls.raw.product_tmpl_id.id,
            "price": 100.0,
            "date_start": "2020-01-01",
            "approval_state": "approved",
            "is_applied": True,
        })
        cls.trading = cls.Product.create({
            "name": "Hàng TM", "product_kind": "trading", "list_price": 1500.0})

        # --- Cấu hình báo giá đang áp dụng ---
        cls.profit_rule = cls._activate(cls.env["dl.pricing.profit.rule"].create({
            "target_markup": 20.0, "min_markup": 8.0}))
        cls.discount_rule = cls._activate(cls.env["dl.pricing.discount.rule"].create({
            "customer_group": "new", "default_rate": 5.0, "max_rate": 15.0}))

        cls.config = cls.env["dl.pricing.config"].search([], limit=1)
        if not cls.config:
            cls.config = cls.env["dl.pricing.config"].create({})
        cls.config.write({"vat_pct": 0.0, "rounding_to": 0})

    @classmethod
    def _activate(cls, rule):
        # Bỏ qua luồng phê duyệt thương mại — kích hoạt trực tiếp cho test.
        rule._activate_rule()
        return rule

    def _make_bom(self, product, qty_out, material, mat_qty, waste=0.0):
        bom = self.Bom.create({
            "product_id": product.id,
            "bom_type": "quotation",
            "product_qty": qty_out,
            "line_ids": [(0, 0, {
                "material_id": material.id,
                "quantity": mat_qty,
                "waste_rate": waste,
            })],
        })
        bom.action_confirm()
        return bom

    def _make_rfq(self, lines):
        return self.Rfq.create({
            "customer_id": self.customer.id,
            "line_ids": lines,
        })

    def _manufactured(self, name="SP GC"):
        man = self.Product.create({"name": name, "product_kind": "manufactured"})
        bom = self._make_bom(man, 1, self.raw, 2)   # 2 × 100 = 200/đv
        return man, bom

    # ------------------------------------------------------------------
    def test_tc01_trading_only(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 2, "resolved_product_id": self.trading.id,
        })])
        self.assertEqual(rfq.status, "confirmed")
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        line = quo.line_ids
        self.assertEqual(line.line_type, "trading")
        self.assertEqual(line.price_unit, 1500.0)      # snapshot list_price
        self.assertEqual(line.price_subtotal, 3000.0)
        self.assertEqual(line.total_cost, 0.0)
        self.assertEqual(line.component_ids.mapped("component_type"), ["trading_base"])
        self.assertEqual(rfq.status, "quoted")

    def test_tc02_manufactured_missing_bom(self):
        man, bom = self._manufactured("SP2")
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP2",
            "quantity": 5, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        bom.action_reset_draft()
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertFalse(self.Quotation.search([("quotation_request_id", "=", rfq.id)]))
        self.assertEqual(rfq.status, "confirmed")

    def test_tc03_processed_material_divides_product_qty(self):
        processed = self.Product.create(
            {"name": "BTP P", "product_kind": "material_processed"})
        self._make_bom(processed, 2, self.raw, 4)   # 400 cho 2 đv → 200/đv
        man = self.Product.create({"name": "SP M", "product_kind": "manufactured"})
        bom_m = self._make_bom(man, 1, processed, 1)
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP M",
            "quantity": 10, "resolved_product_id": man.id, "resolved_bom_id": bom_m.id,
        })])
        rfq.action_create_quotation()
        line = rfq.quotation_id.line_ids
        self.assertEqual(line.material_cost, 200.0)   # chia product_qty (không phải 400)
        self.assertEqual(line.total_cost, 200.0)
        self.assertEqual(line.price_unit, 240.0)      # 200 × (1 + 20%)
        self.assertEqual(line.price_subtotal, 2400.0)
        proc = line.component_ids.filtered(
            lambda c: c.component_type == "processed_material")
        self.assertEqual(proc.amount, 2000.0)

    def test_markup_and_floor(self):
        man, bom = self._manufactured("SP markup")
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP markup",
            "quantity": 1, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        line = quo.line_ids
        self.assertEqual(line.total_cost, 200.0)
        self.assertEqual(line.price_unit, 240.0)      # markup 20%
        self.assertEqual(line.floor_price, 216.0)     # min_markup 8%
        self.assertEqual(quo.target_markup, 20.0)
        markup = line.component_ids.filtered(lambda c: c.component_type == "markup")
        self.assertEqual(markup.amount, 40.0)         # (240 − 200) × 1

    def test_discount_autofill_from_rule(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 2, "resolved_product_id": self.trading.id,
        })])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        self.assertEqual(quo.discount_pct, 5.0)        # default_rate nhóm 'new'
        self.assertEqual(quo.discount_default_rate, 5.0)
        self.assertEqual(quo.discount_max_rate, 15.0)
        self.assertEqual(quo.amount_untaxed, 3000.0)
        self.assertEqual(quo.discount_amount, 150.0)   # 5% × 3000
        self.assertEqual(quo.amount_before_vat, 2850.0)

    def test_tc09_snapshot_immutable(self):
        man, bom = self._manufactured("SP9")
        rfq = self._make_rfq([
            (0, 0, {"product_type": "trading", "product_name": "Hàng TM",
                    "quantity": 1, "resolved_product_id": self.trading.id}),
            (0, 0, {"product_type": "manufactured", "product_name": "SP9",
                    "quantity": 1, "resolved_product_id": man.id,
                    "resolved_bom_id": bom.id}),
        ])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        before = quo.amount_untaxed                    # 1500 + 240 = 1740
        self.assertEqual(before, 1740.0)

        self.raw_seller.price = 999.0
        self.trading.list_price = 9999.0
        quo.invalidate_recordset()
        self.assertEqual(quo.amount_untaxed, before)
        man_line = quo.line_ids.filtered(lambda l: l.line_type == "manufactured")
        self.assertEqual(man_line.material_cost, 200.0)
        self.assertEqual(man_line.price_unit, 240.0)

    def test_tc11_missing_price_rollback(self):
        man = self.Product.create({"name": "SP11", "product_kind": "manufactured"})
        raw2 = self.Product.create({"name": "Thép R2", "product_kind": "material"})
        bom = self._make_bom(man, 1, raw2, 2)          # raw2 chưa có giá áp dụng
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP11",
            "quantity": 3, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertFalse(self.Quotation.search([("quotation_request_id", "=", rfq.id)]))
        self.assertEqual(rfq.status, "confirmed")

    @mute_logger("odoo.sql_db")
    def test_tc12_duplicate_blocked(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 1, "resolved_product_id": self.trading.id,
        })])
        rfq.action_create_quotation()
        self.assertEqual(self.Quotation.search_count(
            [("quotation_request_id", "=", rfq.id)]), 1)
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertEqual(self.Quotation.search_count(
            [("quotation_request_id", "=", rfq.id)]), 1)

    def test_infeasible_blocks_whole_rfq(self):
        rfq = self._make_rfq([
            (0, 0, {"product_type": "trading", "product_name": "Hàng TM",
                    "quantity": 1, "resolved_product_id": self.trading.id}),
            (0, 0, {"product_type": "manufactured", "product_name": "SP khó",
                    "quantity": 1, "is_infeasible": True,
                    "infeasible_reason": "Không làm được"}),
        ])
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertFalse(self.Quotation.search([("quotation_request_id", "=", rfq.id)]))

    def test_missing_profit_rule_blocks_manufactured(self):
        # Ngừng cấu hình lợi nhuận → dòng gia công không tính được markup.
        self.profit_rule.with_context(pricing_system_write=True).write(
            {"state": "expired"})
        man, bom = self._manufactured("SP no profit")
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP no profit",
            "quantity": 1, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertFalse(self.Quotation.search([("quotation_request_id", "=", rfq.id)]))

    def test_approval_required_by_value_threshold(self):
        # Ma trận: từ 1.000đ cần Trưởng KD duyệt.
        matrix = self.env["dl.pricing.approval.matrix"].create({
            "value_from": 1000.0, "approval_level": "sales_manager"})
        matrix.action_apply()

        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 2, "resolved_product_id": self.trading.id,
        })])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        self.assertTrue(quo.approval_required)
        self.assertEqual(quo.approval_state, "pending")
        self.assertTrue(quo.approval_request_id)
        self.assertTrue(quo.approval_reasons)
        self.assertEqual(quo.approval_request_id.request_type, "quote_over_threshold")
        self.assertTrue(quo.approval_request_id.trigger_reasons)
        # Chưa duyệt thì không gửi được khách.
        with self.assertRaises(UserError):
            quo.action_send()
        # Hook duyệt cập nhật trạng thái báo giá.
        quo._on_approval_approved(quo.approval_request_id)
        self.assertEqual(quo.approval_state, "approved")

    def test_no_approval_when_below_threshold(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 1, "resolved_product_id": self.trading.id,
        })])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        self.assertFalse(quo.approval_required)
        self.assertEqual(quo.approval_state, "not_required")

    def test_round_price_helper(self):
        svc = self.env["dl.quotation.pricing.service"]
        self.assertEqual(svc._round_price(123400.0, 1000), 123000.0)
        self.assertEqual(svc._round_price(123600.0, 1000), 124000.0)
        self.assertEqual(svc._round_price(123456.0, 0), 123456.0)

    # ---- Hao hụt hợp nhất: vật tư + complexity + thu hồi ----
    def test_material_waste_default_from_category(self):
        cat = self.env["product.category"].create({"name": "Nhóm thép test"})
        self._activate(self.env["dl.pricing.waste.rule"].create({
            "target_type": "category", "category_id": cat.id, "waste_rate": 7.0}))
        p = self.Product.create({
            "name": "VT theo nhóm", "product_kind": "material", "categ_id": cat.id})
        p._onchange_dlm_waste_default()
        self.assertEqual(p.dlm_waste_rate, 7.0)   # tự điền mặc định theo nhóm

    def test_waste_rate_from_material_x_complexity(self):
        self.raw.dlm_waste_rate = 8.0
        cx = self.env["dl.pricing.complexity.level"].create(
            {"name": "Cao", "factor": 1.5})
        bom = self.Bom.create({
            "product_id": self.Product.create(
                {"name": "SP cx", "product_kind": "manufactured"}).id,
            "bom_type": "quotation", "product_qty": 1,
            "line_ids": [(0, 0, {"material_id": self.raw.id, "quantity": 10.0})],
        })
        line = bom.line_ids
        line.complexity_id = cx
        line._onchange_material_waste()
        self.assertEqual(line.waste_rate, 12.0)   # 8% × 1.5

    def test_recovery_reduces_material_cost(self):
        scrap = self.Product.create(
            {"name": "Phế thép", "product_kind": "material", "list_price": 30.0})
        raw = self.Product.create({"name": "Thép thu hồi", "product_kind": "material",
                                   "dlm_has_recovery": True, "dlm_recovery_rate": 50.0,
                                   "dlm_scrap_product_id": scrap.id})
        self.env["product.supplierinfo"].create({
            "partner_id": self.supplier.id,
            "product_tmpl_id": raw.product_tmpl_id.id,
            "price": 100.0, "date_start": "2020-01-01",
            "approval_state": "approved", "is_applied": True})
        man = self.Product.create({"name": "SP thu hồi", "product_kind": "manufactured"})
        bom = self._make_bom(man, 1, raw, 10, waste=10.0)   # eff 11, hao hụt 1
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP thu hồi",
            "quantity": 1, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        rfq.action_create_quotation()
        line = rfq.quotation_id.line_ids
        # 11×100 − (1 × 50% × 30) = 1100 − 15 = 1085
        self.assertEqual(line.material_cost, 1085.0)
        rec = line.component_ids.filtered(lambda c: c.component_type == "recovery")
        self.assertEqual(rec.amount, -15.0)
