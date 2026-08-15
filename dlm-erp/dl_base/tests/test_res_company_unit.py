# -*- coding: utf-8 -*-
"""L2 Integration test (TransactionCase, DB thật) cho res.company._dlm_enforce_vnd()
(dl_base/models/res_company.py), ép mọi công ty dùng VNĐ và chạy lại ở mỗi lần -u dl_base.
Sheet nguồn: ResCompany trong Report_5_1_UnitTests_L1.xlsx.

Nhánh except UserError (công ty đã có bút toán kế toán, module account chặn đổi tiền tệ)
không tái hiện được bằng dữ liệu thật trong môi trường test này vì module account không
được cài (xác nhận qua "account.move" in env là False). Vì vậy test patch thẳng
Company.write để mô phỏng đúng lỗi mà module account ném ra thật sự, chỉ nhằm verify
logic try/except của _dlm_enforce_vnd(), không verify lại constraint của module account."""
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
        """TC-UNIT-ResCompany-001: công ty đang dùng USD, gọi _dlm_enforce_vnd()
        thì phải đổi currency_id về VNĐ và kích hoạt currency VNĐ."""
        self.usd.sudo().active = True
        company = self.env["res.company"].create({
            "name": "Công ty test VND 001", "currency_id": self.usd.id,
        })
        self.env["res.company"]._dlm_enforce_vnd()
        self.assertEqual(company.currency_id, self.vnd)
        self.assertTrue(self.vnd.active)

    def test_company_with_blocked_write_keeps_currency_and_does_not_raise(self):
        """TC-UNIT-ResCompany-002: khi write currency_id bị chặn (mô phỏng lỗi
        module account ném ra vì công ty đã có bút toán), _dlm_enforce_vnd() phải
        nuốt UserError, không raise ra ngoài, và tiền tệ công ty giữ nguyên USD."""
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
            "Ghi bị chặn thì tiền tệ công ty phải giữ nguyên, không được âm thầm đổi",
        )
