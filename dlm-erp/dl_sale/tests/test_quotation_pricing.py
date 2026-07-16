from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "dl_quotation")
class TestQuotationPricing(TransactionCase):
    """Kiểm thử chấp nhận P0 (đặc tả §13/§17.8): TC01, TC02, TC03, TC09, TC11,
    TC12 + chặn infeasible + chiết khấu/VAT hàng thương mại."""

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

        # Vật tư thô R, có bảng giá đã duyệt + đang áp dụng, giá 100.
        cls.raw = cls.Product.create({"name": "Thép R", "product_kind": "material"})
        cls.raw_seller = cls.env["product.supplierinfo"].create({
            "partner_id": cls.supplier.id,
            "product_tmpl_id": cls.raw.product_tmpl_id.id,
            "price": 100.0,
            "date_start": "2020-01-01",
            "approval_state": "approved",
            "is_applied": True,
        })

        # Sản phẩm thương mại T, list_price 1500.
        cls.trading = cls.Product.create({
            "name": "Hàng TM", "product_kind": "trading", "list_price": 1500.0})

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

    # ------------------------------------------------------------------
    def test_tc01_trading_only(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading",
            "product_name": "Hàng TM",
            "quantity": 2,
            "resolved_product_id": self.trading.id,
        })])
        self.assertEqual(rfq.status, "confirmed")
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        self.assertTrue(quo)
        self.assertEqual(len(quo.line_ids), 1)
        line = quo.line_ids
        self.assertEqual(line.line_type, "trading")
        self.assertEqual(line.price_unit, 1500.0)          # snapshot list_price
        self.assertEqual(line.price_subtotal, 3000.0)
        self.assertEqual(line.total_cost, 0.0)             # TM không qua cost engine
        comps = quo.component_ids
        self.assertEqual(comps.mapped("component_type"), ["trading_base"])
        self.assertEqual(rfq.status, "quoted")

    def test_tc02_manufactured_missing_bom(self):
        man = self.Product.create({"name": "SP Gia công 2", "product_kind": "manufactured"})
        bom = self._make_bom(man, 1, self.raw, 3)
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured",
            "product_name": "SP Gia công 2",
            "quantity": 5,
            "resolved_product_id": man.id,
            "resolved_bom_id": bom.id,
        })])
        self.assertEqual(rfq.status, "confirmed")
        # Đưa BOM về nháp → không còn confirmed/locked → chặn QTE-002.
        bom.action_reset_draft()
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertEqual(self.Quotation.search_count(
            [("quotation_request_id", "=", rfq.id)]), 0)
        self.assertEqual(rfq.status, "confirmed")

    def test_tc03_processed_material_divides_product_qty(self):
        # BTP P: BOM product_qty=2, dùng 4 R → cost 400 cho 2 đv → 200/đv.
        processed = self.Product.create(
            {"name": "BTP P", "product_kind": "material_processed"})
        self._make_bom(processed, 2, self.raw, 4)
        # SP gia công M: BOM product_qty=1, dùng 1 P.
        man = self.Product.create({"name": "SP M", "product_kind": "manufactured"})
        bom_m = self._make_bom(man, 1, processed, 1)
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured",
            "product_name": "SP M",
            "quantity": 10,
            "resolved_product_id": man.id,
            "resolved_bom_id": bom_m.id,
        })])
        rfq.action_create_quotation()
        line = rfq.quotation_id.line_ids
        self.assertEqual(line.material_cost, 200.0)   # nếu không chia product_qty sẽ là 400
        self.assertEqual(line.total_cost, 200.0)
        self.assertEqual(line.price_subtotal, 2000.0)
        proc = line.component_ids.filtered(
            lambda c: c.component_type == "processed_material")
        self.assertEqual(proc.unit_price, 200.0)
        self.assertEqual(proc.amount, 2000.0)

    def test_tc09_snapshot_immutable(self):
        man = self.Product.create({"name": "SP 9", "product_kind": "manufactured"})
        bom = self._make_bom(man, 1, self.raw, 2)   # 2 × 100 = 200/đv
        rfq = self._make_rfq([
            (0, 0, {"product_type": "trading", "product_name": "Hàng TM",
                    "quantity": 1, "resolved_product_id": self.trading.id}),
            (0, 0, {"product_type": "manufactured", "product_name": "SP 9",
                    "quantity": 1, "resolved_product_id": man.id,
                    "resolved_bom_id": bom.id}),
        ])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        before = quo.amount_untaxed
        man_line = quo.line_ids.filtered(lambda l: l.line_type == "manufactured")
        self.assertEqual(man_line.material_cost, 200.0)

        # Đổi giá NCC và list_price sau khi tạo báo giá.
        self.raw_seller.price = 999.0
        self.trading.list_price = 9999.0
        quo.invalidate_recordset()
        self.assertEqual(quo.amount_untaxed, before)          # báo giá không đổi
        self.assertEqual(man_line.material_cost, 200.0)
        self.assertEqual(
            quo.line_ids.filtered(lambda l: l.line_type == "trading").price_unit,
            1500.0)

    def test_tc11_missing_price_rollback(self):
        man = self.Product.create({"name": "SP 11", "product_kind": "manufactured"})
        # Vật tư khác KHÔNG có bảng giá áp dụng.
        raw2 = self.Product.create({"name": "Thép R2", "product_kind": "material"})
        bom = self._make_bom(man, 1, raw2, 2)
        rfq = self._make_rfq([(0, 0, {
            "product_type": "manufactured", "product_name": "SP 11",
            "quantity": 3, "resolved_product_id": man.id, "resolved_bom_id": bom.id,
        })])
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertEqual(self.Quotation.search_count(
            [("quotation_request_id", "=", rfq.id)]), 0)
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
        # Lần 2 (RFQ đã quoted) phải bị chặn.
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
        self.assertEqual(rfq.status, "confirmed")
        with self.assertRaises(UserError):
            rfq.action_create_quotation()
        self.assertEqual(self.Quotation.search_count(
            [("quotation_request_id", "=", rfq.id)]), 0)

    def test_discount_vat_apply_to_trading(self):
        rfq = self._make_rfq([(0, 0, {
            "product_type": "trading", "product_name": "Hàng TM",
            "quantity": 2, "resolved_product_id": self.trading.id,
        })])
        rfq.action_create_quotation()
        quo = rfq.quotation_id
        quo.write({"discount_pct": 10.0, "vat_pct": 10.0})
        self.assertEqual(quo.amount_untaxed, 3000.0)
        self.assertEqual(quo.discount_amount, 300.0)
        self.assertEqual(quo.amount_before_vat, 2700.0)
        self.assertEqual(quo.vat_amount, 270.0)
        self.assertEqual(quo.amount_total, 2970.0)
