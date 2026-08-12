# -*- coding: utf-8 -*-
"""L2 Integration test (TransactionCase, DB thật) cho res.partner mở rộng ở
dl_sale (ResPartnerQuoteStats, dl_sale/models/res_partner.py) — phân loại
khách hàng tự động (Mới/Cũ/Thân thiết) + cảnh báo gộp đơn + thống kê báo
giá. Sheet nguồn: ResPartnerQuoteStats trong Report_5_2_IntegrationTests_
L2.xlsx.

Bổ sung 2026-08-11 (Round 3 — trước đó 0% coverage, FT-14 chưa từng có test
ở bất kỳ cấp nào)."""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestResPartnerQuoteStats(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env["res.users"].create({
            "name": "Admin test RPQS", "login": "admin_rpqs_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        cls.sales_user = cls.env["res.users"].create({
            "name": "Sales test RPQS", "login": "sales_rpqs_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def _customer(self, **kw):
        # partner_type='individual' để né _check_company_tax_code (đòi MST
        # nếu partner_type='company') — _check_partner_type vẫn đòi
        # partner_type khác rỗng cho mọi KH DLM (top-level).
        base = dict(name="KH test RPQS", partner_role="customer",
                    partner_type="individual")
        base.update(kw)
        return self.env["res.partner"].create(base)

    def _quotation(self, partner, state, amount=0.0, date_order=None):
        vals = {"partner_id": partner.id, "state": state}
        if date_order:
            vals["date_order"] = date_order
        quo = self.env["dl.quotation"].create(vals)
        if amount:
            quo.line_ids = [(0, 0, {"name": "Dòng test", "qty": 1, "price_unit": amount})]
        return quo

    def test_new_customer_no_won_quotation(self):
        """TC-INT-ResPartnerQuoteStats-001"""
        partner = self._customer()
        self.assertEqual(partner.dlm_customer_group, "new")

    def test_won_below_threshold_is_existing(self):
        """TC-INT-ResPartnerQuoteStats-002"""
        partner = self._customer()
        self._quotation(partner, "accepted", amount=10_000_000.0)
        partner.invalidate_recordset()
        self.assertEqual(partner.dlm_customer_group, "existing")

    def test_threshold_boundary_and_reclassify_on_change(self):
        """TC-INT-ResPartnerQuoteStats-003"""
        partner = self._customer()
        self._quotation(partner, "ordered", amount=100.0)
        partner.invalidate_recordset()

        self.env["res.partner"].with_user(self.admin_user).set_loyal_threshold(100)
        partner.invalidate_recordset()
        self.assertEqual(partner.dlm_customer_group, "existing",
                          "Đúng bằng ngưỡng (>) chưa lên Thân thiết")

        self.env["res.partner"].with_user(self.admin_user).set_loyal_threshold(99)
        partner.invalidate_recordset()
        self.assertEqual(partner.dlm_customer_group, "loyal")

    def test_non_admin_cannot_change_threshold(self):
        """TC-INT-ResPartnerQuoteStats-004"""
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(
                self.sales_user).set_loyal_threshold(500000)

    def test_invalid_threshold_values_raise(self):
        """TC-INT-ResPartnerQuoteStats-005"""
        Partner = self.env["res.partner"].with_user(self.admin_user)
        with self.assertRaises(ValidationError):
            Partner.set_loyal_threshold(-1)
        with self.assertRaises(ValidationError):
            Partner.set_loyal_threshold("abc")

    def test_split_warning_needs_at_least_2_recent_over_threshold(self):
        """TC-INT-ResPartnerQuoteStats-006"""
        from odoo import fields
        today = fields.Date.context_today(self.env.user)
        two_customer = self._customer(name="KH test RPQS 2 dòng")
        self._quotation(two_customer, "sent", amount=15_000_000.0, date_order=today)
        self._quotation(two_customer, "sent", amount=15_000_000.0, date_order=today)
        two_customer.invalidate_recordset()
        self.assertTrue(two_customer.dlm_split_warning)

        one_customer = self._customer(name="KH test RPQS 1 dòng")
        self._quotation(one_customer, "sent", amount=30_000_000.0, date_order=today)
        one_customer.invalidate_recordset()
        self.assertFalse(
            one_customer.dlm_split_warning,
            "Chỉ 1 báo giá thì dù vượt ngưỡng vẫn không cảnh báo (cần >=2)")

    def test_win_rate_excludes_open_quotes_open_count_includes_them(self):
        """TC-INT-ResPartnerQuoteStats-007"""
        partner = self._customer(name="KH test RPQS win rate")
        self._quotation(partner, "accepted", amount=1000.0)
        self._quotation(partner, "rejected", amount=1000.0)
        self._quotation(partner, "draft", amount=1000.0)
        self._quotation(partner, "sent", amount=1000.0)
        partner.invalidate_recordset()
        self.assertAlmostEqual(partner.dlm_win_rate, 50.0)
        self.assertEqual(partner.dlm_open_quote_count, 2)
