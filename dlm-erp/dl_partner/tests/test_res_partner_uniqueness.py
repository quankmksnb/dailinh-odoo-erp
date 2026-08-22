# -*- coding: utf-8 -*-
"""L2 (TransactionCase, chạm DB thật) cho hai constraint chặn trùng của
res.partner (dl_partner/models/res_partner.py). Sheet nguồn:
TestResPartnerUniqueness.

- _check_contact_unique_name(): chặn hai người liên hệ trùng tên trong cùng
  một khách hàng.
- _check_unique_contact_channel(): chặn hai khách hàng cấp cao dùng chung
  SĐT/Email, trừ khi tích dlm_allow_dup_contact.
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_partner")
class TestResPartnerUniqueness(TransactionCase):

    def test_duplicate_contact_name_in_same_customer_blocked(self):
        """TC-INT-TestResPartnerUniqueness-001: khách hàng đã có 1 người liên
        hệ tên 'Nguyễn Văn A'; tạo thêm người liên hệ thứ 2 cùng parent_id,
        cùng tên (dlm_name_key trùng) -> ValidationError chứa tên khách hàng
        và 'đã có người liên hệ tên'."""
        customer = self.env["res.partner"].create({
            "name": "Khách hàng test trùng NLH (test uniq 001)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111101",
        })
        self.env["res.partner"].create({
            "parent_id": customer.id,
            "type": "contact",
            "name": "Nguyễn Văn A",
            "phone": "0922222201",
        })

        with self.assertRaises(ValidationError) as err:
            self.env["res.partner"].create({
                "parent_id": customer.id,
                "type": "contact",
                "name": "Nguyễn Văn A",
                "phone": "0933333301",
            })

        message = str(err.exception)
        self.assertIn(customer.name, message)
        self.assertIn("đã có người liên hệ tên", message)

    def test_same_name_different_customer_not_blocked(self):
        """Đối chứng: hai người liên hệ trùng tên nhưng thuộc HAI khách hàng
        khác nhau thì không bị chặn (constraint chỉ so trong cùng parent_id)."""
        customer_a = self.env["res.partner"].create({
            "name": "Khách hàng A (test uniq 001b)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111102",
        })
        customer_b = self.env["res.partner"].create({
            "name": "Khách hàng B (test uniq 001b)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111103",
        })
        self.env["res.partner"].create({
            "parent_id": customer_a.id,
            "type": "contact",
            "name": "Trần Văn B",
            "phone": "0922222202",
        })

        contact_b = self.env["res.partner"].create({
            "parent_id": customer_b.id,
            "type": "contact",
            "name": "Trần Văn B",
            "phone": "0922222203",
        })

        self.assertEqual(contact_b.name, "Trần Văn B")

    def test_duplicate_phone_between_customers_blocked(self):
        """TC-INT-TestResPartnerUniqueness-002: đã có khách hàng dùng số
        '0912345678'; tạo khách hàng thứ 2 cùng SĐT, dlm_allow_dup_contact=False
        -> ValidationError."""
        self.env["res.partner"].create({
            "name": "Khách hàng dùng SĐT gốc (test uniq 002)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0912345678",
        })

        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Khách hàng dùng SĐT trùng (test uniq 002)",
                "partner_role": "customer",
                "partner_type": "individual",
                "phone": "0912345678",
                "dlm_allow_dup_contact": False,
            })

    def test_duplicate_email_between_customers_blocked(self):
        """Constraint cũng chặn trùng Email giữa hai khách hàng, không chỉ SĐT."""
        self.env["res.partner"].create({
            "name": "Khách hàng dùng email gốc (test uniq 002b)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111104",
            "email": "trung.email@test-dlm.example",
        })

        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({
                "name": "Khách hàng dùng email trùng (test uniq 002b)",
                "partner_role": "customer",
                "partner_type": "individual",
                "phone": "0911111105",
                "email": "trung.email@test-dlm.example",
            })

    def test_allow_dup_contact_bypasses_check(self):
        """Ca đối chứng: tích dlm_allow_dup_contact=True thì không raise dù
        trùng SĐT với khách hàng đã có."""
        self.env["res.partner"].create({
            "name": "Khách hàng dùng SĐT gốc (test uniq 002c)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111106",
        })

        dup = self.env["res.partner"].create({
            "name": "Khách hàng cho phép trùng SĐT (test uniq 002c)",
            "partner_role": "customer",
            "partner_type": "individual",
            "phone": "0911111106",
            "dlm_allow_dup_contact": True,
        })

        self.assertEqual(dup.phone, "0911111106")
