# -*- coding: utf-8 -*-
"""L2 Integration test (TransactionCase, DB thật) cho
res.company._dlm_enforce_vnd() (dl_base/models/res_company.py) — ép mọi
công ty dùng VNĐ, chạy lại ở mỗi lần -u dl_base. Sheet nguồn: ResCompany
trong Report_5_1_UnitTests_L1.xlsx.

Bổ sung 2026-08-11 (Round 2/3 — trước đó 0% coverage). Nhánh except UserError
(công ty đã có bút toán kế toán, account module chặn đổi tiền tệ) không tái
hiện được bằng dữ liệu thật trong môi trường test này (module `account`
KHÔNG cài — xác nhận qua `"account.move" in env` == False) nên patch thẳng
Company.write để mô phỏng đúng lỗi mà account module ném ra thật sự — vẫn
verify đúng logic try/except của _dlm_enforce_vnd(), không phải verify lại
constraint của account (không thuộc code dl_base)."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_base")
class TestResCompanyEnforceVnd(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vnd = cls.env.ref("base.VND")
        cls.usd = cls.env.ref("base.USD")

    def test_company_on_other_currency_switches_to_vnd(self):
        """TC-UNIT-ResCompany-001"""
        self.usd.sudo().active = True
        company = self.env["res.company"].create({
            "name": "Công ty test VND 001", "currency_id": self.usd.id,
        })
        self.env["res.company"]._dlm_enforce_vnd()
        self.assertEqual(company.currency_id, self.vnd)
        self.assertTrue(self.vnd.active)

    def test_company_with_blocked_write_keeps_currency_and_does_not_raise(self):
        """TC-UNIT-ResCompany-002"""
        self.usd.sudo().active = True
        company = self.env["res.company"].create({
            "name": "Công ty test VND 002 (đã có bút toán)", "currency_id": self.usd.id,
        })
        Company = type(company)
        real_write = Company.write

        def _blocked_write(self, vals):
            if "currency_id" in vals and company.id in self.ids:
                raise UserError("Không thể đổi tiền tệ: đã có bút toán kế toán.")
            return real_write(self, vals)

        with patch.object(Company, "write", _blocked_write):
            self.env["res.company"]._dlm_enforce_vnd()  # không raise ra ngoài
        self.assertEqual(
            company.currency_id, self.usd,
            "Ghi bị chặn -> tiền tệ công ty phải GIỮ NGUYÊN, không âm thầm đổi",
        )
