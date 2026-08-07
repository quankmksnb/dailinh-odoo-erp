# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho res.partner extension (dl_partner).
Sheet nguồn: ResPartner (dl_partner).

Chỉ test compute/constraint thuần Python (helper classification + regex
validate MST/SĐT/email) — không đụng self.env. create/write/name_search/
get_formview_id/_process_pending_link/_check_unique_tax_code (dùng
self.search) là L2, không test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.res_partner import ResPartner


class _PRS(list):
    """Stand-in cho recordset res.partner — hỗ trợ for rec in self + đọc
    self._DLM_AVA_PALETTE / self._fields ở cấp recordset (mượn nguyên hằng
    thật, giống kỹ thuật _RS ở dl_sale/tests/test_dl_quotation_unit.py)."""

    _DLM_AVA_PALETTE = ResPartner._DLM_AVA_PALETTE
    # _compute_partner_type_label() đọc self._fields['partner_type'].selection
    # ở cấp recordset — mượn nguyên danh sách selection thật của field.
    _fields = {
        "partner_type": SimpleNamespace(selection=[
            ("individual", "Cá nhân"), ("company", "Doanh nghiệp"), ("dealer", "Đại lý"),
        ]),
    }


def _partner(**kw):
    base = dict(active=True, image_128=False, name="", partner_type=False,
                partner_role=False, parent_id=None, vat=False, phone=False,
                mobile=False, email=False, dlm_allow_dup_tax=False,
                commercial_partner_id=None)
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec.ensure_one = lambda: rec
    # _dl_is_customer_record/_dl_is_customer_contact mượn nguyên method thật —
    # được nhiều constraint khác gọi qua rec.<method>().
    rec._dl_is_customer_record = lambda: ResPartner._dl_is_customer_record(rec)
    rec._dl_is_customer_contact = lambda: ResPartner._dl_is_customer_contact(rec)
    return rec


# =============================================================================
# _dl_is_customer_record() / _dl_is_customer_contact()
# =============================================================================
class TestIsCustomerRecord(unittest.TestCase):
    def test_customer_top_level_true(self):
        """TC-UNIT-ResPartner-001"""
        p = _partner(partner_role="customer", parent_id=None)
        self.assertTrue(ResPartner._dl_is_customer_record(p))

    def test_both_role_top_level_true(self):
        """TC-UNIT-ResPartner-002"""
        p = _partner(partner_role="both", parent_id=None)
        self.assertTrue(ResPartner._dl_is_customer_record(p))

    def test_supplier_role_false(self):
        """TC-UNIT-ResPartner-003"""
        p = _partner(partner_role="supplier", parent_id=None)
        self.assertFalse(ResPartner._dl_is_customer_record(p))

    def test_customer_with_parent_is_contact_not_record(self):
        """TC-UNIT-ResPartner-004"""
        p = _partner(partner_role="customer", parent_id=SimpleNamespace(id=1))
        self.assertFalse(ResPartner._dl_is_customer_record(p))


class TestIsCustomerContact(unittest.TestCase):
    def test_contact_of_customer_true(self):
        """TC-UNIT-ResPartner-005"""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"))
        self.assertTrue(ResPartner._dl_is_customer_contact(p))

    def test_contact_of_supplier_false(self):
        """TC-UNIT-ResPartner-006"""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="supplier"))
        self.assertFalse(ResPartner._dl_is_customer_contact(p))

    def test_top_level_not_a_contact(self):
        """TC-UNIT-ResPartner-007"""
        p = _partner(parent_id=None,
                     commercial_partner_id=SimpleNamespace(partner_role="customer"))
        self.assertFalse(ResPartner._dl_is_customer_contact(p))


# =============================================================================
# Compute thuần: status label / has photo / avatar letter / partner type label
# =============================================================================
class TestComputeDlmStatusLabel(unittest.TestCase):
    def test_active(self):
        """TC-UNIT-ResPartner-008"""
        rec = SimpleNamespace(active=True)
        ResPartner._compute_dlm_status_label([rec])
        self.assertEqual(rec.dlm_status_label, "Đang hợp tác")

    def test_inactive(self):
        """TC-UNIT-ResPartner-009"""
        rec = SimpleNamespace(active=False)
        ResPartner._compute_dlm_status_label([rec])
        self.assertEqual(rec.dlm_status_label, "Ngừng hợp tác")


class TestComputeDlmHasPhoto(unittest.TestCase):
    def test_has_image(self):
        """TC-UNIT-ResPartner-010"""
        rec = SimpleNamespace(image_128="base64data")
        ResPartner._compute_dlm_has_photo([rec])
        self.assertTrue(rec.dlm_has_photo)

    def test_no_image(self):
        """TC-UNIT-ResPartner-011"""
        rec = SimpleNamespace(image_128=False)
        ResPartner._compute_dlm_has_photo([rec])
        self.assertFalse(rec.dlm_has_photo)


class TestComputeDlmAvatarLetter(unittest.TestCase):
    def test_uses_first_letter_uppercased(self):
        """TC-UNIT-ResPartner-012"""
        rec = SimpleNamespace(name="khách hàng A")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec]))
        self.assertEqual(rec.dlm_initial, "K")
        self.assertIn(rec.dlm_avatar_bg, [bg for bg, fg in ResPartner._DLM_AVA_PALETTE])

    def test_empty_name_question_mark(self):
        """TC-UNIT-ResPartner-013"""
        rec = SimpleNamespace(name="")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec]))
        self.assertEqual(rec.dlm_initial, "?")

    def test_deterministic_same_name_same_color(self):
        """TC-UNIT-ResPartner-014"""
        rec1 = SimpleNamespace(name="Công ty ABC")
        rec2 = SimpleNamespace(name="Công ty ABC")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec1]))
        ResPartner._compute_dlm_avatar_letter(_PRS([rec2]))
        self.assertEqual(rec1.dlm_avatar_bg, rec2.dlm_avatar_bg)


class TestComputePartnerTypeLabel(unittest.TestCase):
    def test_maps_selection_label(self):
        """TC-UNIT-ResPartner-015"""
        rec = SimpleNamespace(partner_type="company")
        ResPartner._compute_partner_type_label(_PRS([rec]))
        self.assertEqual(rec.partner_type_label, "Doanh nghiệp")


# =============================================================================
# Constraint: loại khách hàng / MST bắt buộc / định dạng MST-SĐT-Email
# =============================================================================
class TestCheckPartnerType(unittest.TestCase):
    def test_customer_without_type_raises(self):
        """TC-UNIT-ResPartner-016"""
        p = _partner(partner_role="customer", partner_type=False)
        with self.assertRaises(ValidationError):
            ResPartner._check_partner_type([p])

    def test_customer_with_type_passes(self):
        """TC-UNIT-ResPartner-017"""
        p = _partner(partner_role="customer", partner_type="individual")
        ResPartner._check_partner_type([p])  # không raise

    def test_supplier_exempt(self):
        """TC-UNIT-ResPartner-018"""
        p = _partner(partner_role="supplier", partner_type=False)
        ResPartner._check_partner_type([p])  # không raise, không phải KH


class TestCheckCompanyTaxCode(unittest.TestCase):
    def test_company_customer_without_vat_raises(self):
        """TC-UNIT-ResPartner-019"""
        p = _partner(partner_role="customer", partner_type="company", vat="")
        with self.assertRaises(ValidationError):
            ResPartner._check_company_tax_code([p])

    def test_company_customer_with_vat_passes(self):
        """TC-UNIT-ResPartner-020"""
        p = _partner(partner_role="customer", partner_type="company", vat="0123456789")
        ResPartner._check_company_tax_code([p])  # không raise

    def test_individual_customer_no_vat_ok(self):
        """TC-UNIT-ResPartner-021"""
        p = _partner(partner_role="customer", partner_type="individual", vat="")
        ResPartner._check_company_tax_code([p])  # cá nhân không bắt buộc


class TestCheckTaxCodeFormat(unittest.TestCase):
    def test_valid_10_digit(self):
        """TC-UNIT-ResPartner-022"""
        p = _partner(partner_role="customer", vat="0123456789")
        ResPartner._check_tax_code_format([p])  # không raise

    def test_valid_10_digit_with_branch_suffix(self):
        """TC-UNIT-ResPartner-023"""
        p = _partner(partner_role="customer", vat="0123456789-001")
        ResPartner._check_tax_code_format([p])  # không raise

    def test_invalid_letters_raises(self):
        """TC-UNIT-ResPartner-024"""
        p = _partner(partner_role="customer", vat="ABC123456")
        with self.assertRaises(ValidationError):
            ResPartner._check_tax_code_format([p])

    def test_wrong_digit_count_raises(self):
        """TC-UNIT-ResPartner-025"""
        p = _partner(partner_role="customer", vat="123")
        with self.assertRaises(ValidationError):
            ResPartner._check_tax_code_format([p])

    def test_empty_vat_skips(self):
        """TC-UNIT-ResPartner-026"""
        p = _partner(partner_role="customer", vat="")
        ResPartner._check_tax_code_format([p])  # không raise, chưa nhập


class TestCheckPhoneFormat(unittest.TestCase):
    def test_valid_leading_zero(self):
        """TC-UNIT-ResPartner-027"""
        p = _partner(partner_role="customer", phone="0912345678")
        ResPartner._check_phone_format([p])  # không raise

    def test_valid_plus84(self):
        """TC-UNIT-ResPartner-028"""
        p = _partner(partner_role="customer", phone="+84912345678")
        ResPartner._check_phone_format([p])  # không raise

    def test_valid_with_separators_cleaned(self):
        """TC-UNIT-ResPartner-029"""
        p = _partner(partner_role="customer", phone="091.234.5678")
        ResPartner._check_phone_format([p])  # không raise, dấu . bị lọc trước

    def test_invalid_prefix_raises(self):
        """TC-UNIT-ResPartner-030"""
        p = _partner(partner_role="customer", phone="1912345678")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])

    def test_too_short_raises(self):
        """TC-UNIT-ResPartner-031"""
        p = _partner(partner_role="customer", phone="0912345")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])

    def test_mobile_field_also_checked(self):
        """TC-UNIT-ResPartner-032"""
        p = _partner(partner_role="customer", phone=False, mobile="abc")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])


class TestCheckEmailFormat(unittest.TestCase):
    def test_valid_email(self):
        """TC-UNIT-ResPartner-033"""
        p = _partner(partner_role="customer", email="test@example.com")
        ResPartner._check_email_format([p])  # không raise

    def test_invalid_email_raises(self):
        """TC-UNIT-ResPartner-034"""
        p = _partner(partner_role="customer", email="not-an-email")
        with self.assertRaises(ValidationError):
            ResPartner._check_email_format([p])

    def test_no_email_skips(self):
        """TC-UNIT-ResPartner-035"""
        p = _partner(partner_role="customer", email=False)
        ResPartner._check_email_format([p])  # không raise


class TestCheckContactPhoneFormat(unittest.TestCase):
    def test_contact_invalid_phone_raises(self):
        """TC-UNIT-ResPartner-036"""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"),
                     phone="123")
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_phone_format([p])

    def test_non_contact_exempt(self):
        """TC-UNIT-ResPartner-037"""
        p = _partner(parent_id=None, phone="123")
        ResPartner._check_contact_phone_format([p])  # không raise, không phải contact


class TestCheckContactEmailFormat(unittest.TestCase):
    def test_contact_invalid_email_raises(self):
        """TC-UNIT-ResPartner-038"""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"),
                     email="bad-email")
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_email_format([p])


if __name__ == "__main__":
    unittest.main()
