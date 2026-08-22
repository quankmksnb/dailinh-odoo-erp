# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho res.partner extension (dl_partner).
Sheet nguồn: ResPartner (dl_partner).

Chỉ test compute/constraint thuần Python (helper classification, regex validate
MST/SĐT/email), không đụng self.env. Các method create/write/name_search/
get_formview_id/_process_pending_link/_check_unique_tax_code dùng self.search
nên là L2, không test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import AccessError, ValidationError

from ..models.res_partner import ResPartner


class _PRS(list):
    """Stand-in cho recordset res.partner: hỗ trợ for rec in self và đọc
    self._DLM_AVA_PALETTE / self._fields ở cấp recordset (mượn nguyên hằng thật,
    cùng kỹ thuật _RS ở dl_sale/tests/test_dl_quotation_unit.py)."""

    _DLM_AVA_PALETTE = ResPartner._DLM_AVA_PALETTE
    # _compute_partner_type_label() đọc self._fields['partner_type'].selection
    # ở cấp recordset, mượn nguyên danh sách selection thật của field.
    _fields = {
        "partner_type": SimpleNamespace(selection=[
            ("individual", "Cá nhân"), ("company", "Doanh nghiệp"), ("dealer", "Đại lý"),
        ]),
    }
    # write() gọi self._dlm_normalize_vals(vals) ở cấp recordset trước khi soi từng
    # rec — mượn nguyên hằng + method thật, cả hai đều thuần Python (không đụng DB).
    _DLM_NORMALIZERS = ResPartner._DLM_NORMALIZERS
    _dlm_normalize_vals = ResPartner._dlm_normalize_vals


def _partner(**kw):
    base = dict(active=True, image_128=False, name="", partner_type=False,
                partner_role=False, parent_id=None, vat=False, phone=False,
                mobile=False, email=False, dlm_allow_dup_tax=False,
                commercial_partner_id=None)
    base.update(kw)
    rec = SimpleNamespace(**base)
    rec.ensure_one = lambda: rec
    # _dl_is_customer_record/_dl_is_customer_contact mượn nguyên method thật,
    # vì nhiều constraint khác gọi qua rec.<method>().
    rec._dl_is_customer_record = lambda: ResPartner._dl_is_customer_record(rec)
    rec._dl_is_customer_contact = lambda: ResPartner._dl_is_customer_contact(rec)
    rec._dl_is_dlm_partner = lambda: ResPartner._dl_is_dlm_partner(rec)
    return rec


# _dl_is_customer_record() / _dl_is_customer_contact()
class TestIsCustomerRecord(unittest.TestCase):
    def test_customer_top_level_true(self):
        """TC-UNIT-ResPartner-001: partner_role customer, không có parent (bản
        ghi gốc) thì _dl_is_customer_record trả về True."""
        p = _partner(partner_role="customer", parent_id=None)
        self.assertTrue(ResPartner._dl_is_customer_record(p))

    def test_both_role_top_level_true(self):
        """TC-UNIT-ResPartner-002: partner_role both (vừa khách hàng vừa NCC),
        không có parent thì _dl_is_customer_record trả về True."""
        p = _partner(partner_role="both", parent_id=None)
        self.assertTrue(ResPartner._dl_is_customer_record(p))

    def test_supplier_role_false(self):
        """TC-UNIT-ResPartner-003: partner_role supplier, không có parent thì
        _dl_is_customer_record trả về False."""
        p = _partner(partner_role="supplier", parent_id=None)
        self.assertFalse(ResPartner._dl_is_customer_record(p))

    def test_customer_with_parent_is_contact_not_record(self):
        """TC-UNIT-ResPartner-004: partner_role customer nhưng có parent_id (là
        contact của một công ty) thì _dl_is_customer_record trả về False, vì
        contact không tính là bản ghi khách hàng gốc."""
        p = _partner(partner_role="customer", parent_id=SimpleNamespace(id=1))
        self.assertFalse(ResPartner._dl_is_customer_record(p))


class TestIsCustomerContact(unittest.TestCase):
    def test_contact_of_customer_true(self):
        """TC-UNIT-ResPartner-005: có parent_id và commercial_partner_id.partner_role
        là customer thì _dl_is_customer_contact trả về True."""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"))
        self.assertTrue(ResPartner._dl_is_customer_contact(p))

    def test_contact_of_supplier_false(self):
        """TC-UNIT-ResPartner-006: có parent_id nhưng commercial_partner_id.partner_role
        là supplier thì _dl_is_customer_contact trả về False."""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="supplier"))
        self.assertFalse(ResPartner._dl_is_customer_contact(p))

    def test_top_level_not_a_contact(self):
        """TC-UNIT-ResPartner-007: không có parent_id (bản ghi gốc) thì
        _dl_is_customer_contact trả về False, dù commercial_partner_id có
        partner_role customer."""
        p = _partner(parent_id=None,
                     commercial_partner_id=SimpleNamespace(partner_role="customer"))
        self.assertFalse(ResPartner._dl_is_customer_contact(p))


# Compute thuần: status label / has photo / avatar letter / partner type label
class TestComputeDlmStatusLabel(unittest.TestCase):
    def test_active(self):
        """TC-UNIT-ResPartner-008: active True thì dlm_status_label phải là
        'Đang hợp tác'."""
        rec = SimpleNamespace(active=True)
        ResPartner._compute_dlm_status_label([rec])
        self.assertEqual(rec.dlm_status_label, "Đang hợp tác")

    def test_inactive(self):
        """TC-UNIT-ResPartner-009: active False thì dlm_status_label phải là
        'Ngừng hợp tác'."""
        rec = SimpleNamespace(active=False)
        ResPartner._compute_dlm_status_label([rec])
        self.assertEqual(rec.dlm_status_label, "Ngừng hợp tác")


class TestComputeDlmHasPhoto(unittest.TestCase):
    def test_has_image(self):
        """TC-UNIT-ResPartner-010: image_128 có dữ liệu thì dlm_has_photo phải
        là True."""
        rec = SimpleNamespace(image_128="base64data")
        ResPartner._compute_dlm_has_photo([rec])
        self.assertTrue(rec.dlm_has_photo)

    def test_no_image(self):
        """TC-UNIT-ResPartner-011: image_128 rỗng (False) thì dlm_has_photo phải
        là False."""
        rec = SimpleNamespace(image_128=False)
        ResPartner._compute_dlm_has_photo([rec])
        self.assertFalse(rec.dlm_has_photo)


class TestComputeDlmAvatarLetter(unittest.TestCase):
    def test_uses_first_letter_uppercased(self):
        """TC-UNIT-ResPartner-012: tên "khách hàng A" thì dlm_initial phải là
        chữ cái đầu viết hoa 'K', và dlm_avatar_bg phải là một màu nằm trong
        bảng màu _DLM_AVA_PALETTE."""
        rec = SimpleNamespace(name="khách hàng A")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec]))
        self.assertEqual(rec.dlm_initial, "K")
        self.assertIn(rec.dlm_avatar_bg, [bg for bg, fg in ResPartner._DLM_AVA_PALETTE])

    def test_empty_name_question_mark(self):
        """TC-UNIT-ResPartner-013: tên rỗng thì dlm_initial phải là dấu '?'."""
        rec = SimpleNamespace(name="")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec]))
        self.assertEqual(rec.dlm_initial, "?")

    def test_deterministic_same_name_same_color(self):
        """TC-UNIT-ResPartner-014: tính avatar 2 lần cho cùng một tên phải cho ra
        cùng một màu nền (màu suy ra tất định từ tên, không ngẫu nhiên)."""
        rec1 = SimpleNamespace(name="Công ty ABC")
        rec2 = SimpleNamespace(name="Công ty ABC")
        ResPartner._compute_dlm_avatar_letter(_PRS([rec1]))
        ResPartner._compute_dlm_avatar_letter(_PRS([rec2]))
        self.assertEqual(rec1.dlm_avatar_bg, rec2.dlm_avatar_bg)


class TestComputePartnerTypeLabel(unittest.TestCase):
    def test_maps_selection_label(self):
        """TC-UNIT-ResPartner-015: partner_type "company" thì partner_type_label
        phải map đúng sang nhãn selection 'Doanh nghiệp'."""
        rec = SimpleNamespace(partner_type="company")
        ResPartner._compute_partner_type_label(_PRS([rec]))
        self.assertEqual(rec.partner_type_label, "Doanh nghiệp")


# Constraint: loại khách hàng / MST bắt buộc / định dạng MST-SĐT-Email
class TestCheckPartnerType(unittest.TestCase):
    def test_customer_without_type_raises(self):
        """TC-UNIT-ResPartner-016: partner_role customer nhưng chưa chọn
        partner_type thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", partner_type=False)
        with self.assertRaises(ValidationError):
            ResPartner._check_partner_type([p])

    def test_customer_with_type_passes(self):
        """TC-UNIT-ResPartner-017: customer đã chọn partner_type individual thì
        không raise."""
        p = _partner(partner_role="customer", partner_type="individual")
        ResPartner._check_partner_type([p])  # không raise

    def test_supplier_exempt(self):
        """TC-UNIT-ResPartner-018: partner_role supplier không có partner_type
        thì không raise, vì constraint chỉ bắt buộc với khách hàng."""
        p = _partner(partner_role="supplier", partner_type=False)
        ResPartner._check_partner_type([p])  # không raise, không phải KH


class TestCheckCompanyTaxCode(unittest.TestCase):
    def test_company_customer_without_vat_raises(self):
        """TC-UNIT-ResPartner-019: khách hàng doanh nghiệp (company) không có
        MST (vat rỗng) thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", partner_type="company", vat="")
        with self.assertRaises(ValidationError):
            # _check_company_tax_code() đọc self._fields (không phải rec._fields) để
            # lấy nhãn hiển thị trong thông báo lỗi — self là recordset thật khi Odoo
            # gọi, nên list([p]) trần không có _fields. Bọc bằng _PRS (đã có sẵn
            # _fields ở trên, cùng kỹ thuật với _compute_partner_type_label()).
            ResPartner._check_company_tax_code(_PRS([p]))

    def test_company_customer_with_vat_passes(self):
        """TC-UNIT-ResPartner-020: khách hàng doanh nghiệp có MST hợp lệ thì
        không raise."""
        p = _partner(partner_role="customer", partner_type="company", vat="0123456789")
        ResPartner._check_company_tax_code([p])  # không raise

    def test_individual_customer_no_vat_ok(self):
        """TC-UNIT-ResPartner-021: khách hàng cá nhân (individual) không có MST
        thì không raise, vì MST không bắt buộc với cá nhân."""
        p = _partner(partner_role="customer", partner_type="individual", vat="")
        ResPartner._check_company_tax_code([p])  # cá nhân không bắt buộc


class TestCheckTaxCodeFormat(unittest.TestCase):
    def test_valid_10_digit(self):
        """TC-UNIT-ResPartner-022: MST đúng 10 chữ số thì không raise."""
        p = _partner(partner_role="customer", vat="0123456789")
        ResPartner._check_tax_code_format([p])  # không raise

    def test_valid_10_digit_with_branch_suffix(self):
        """TC-UNIT-ResPartner-023: MST 10 chữ số kèm hậu tố chi nhánh (-001) thì
        không raise."""
        p = _partner(partner_role="customer", vat="0123456789-001")
        ResPartner._check_tax_code_format([p])  # không raise

    def test_invalid_letters_raises(self):
        """TC-UNIT-ResPartner-024: MST chứa chữ cái thì báo lỗi
        ValidationError."""
        p = _partner(partner_role="customer", vat="ABC123456")
        with self.assertRaises(ValidationError):
            ResPartner._check_tax_code_format([p])

    def test_wrong_digit_count_raises(self):
        """TC-UNIT-ResPartner-025: MST sai số chữ số (không đủ 10 số) thì báo
        lỗi ValidationError."""
        p = _partner(partner_role="customer", vat="123")
        with self.assertRaises(ValidationError):
            ResPartner._check_tax_code_format([p])

    def test_empty_vat_skips(self):
        """TC-UNIT-ResPartner-026: MST rỗng (chưa nhập) thì không raise, bỏ qua
        kiểm tra định dạng."""
        p = _partner(partner_role="customer", vat="")
        ResPartner._check_tax_code_format([p])  # không raise, chưa nhập


class TestCheckPhoneFormat(unittest.TestCase):
    def test_valid_leading_zero(self):
        """TC-UNIT-ResPartner-027: SĐT hợp lệ dạng bắt đầu bằng số 0 thì không
        raise."""
        p = _partner(partner_role="customer", phone="0912345678")
        ResPartner._check_phone_format([p])  # không raise

    def test_valid_plus84(self):
        """TC-UNIT-ResPartner-028: SĐT hợp lệ dạng bắt đầu bằng +84 thì không
        raise."""
        p = _partner(partner_role="customer", phone="+84912345678")
        ResPartner._check_phone_format([p])  # không raise

    def test_valid_with_separators_cleaned(self):
        """TC-UNIT-ResPartner-029: SĐT có dấu chấm phân cách (091.234.5678) vẫn
        không raise, vì dấu chấm bị lọc bỏ trước khi kiểm tra định dạng."""
        p = _partner(partner_role="customer", phone="091.234.5678")
        ResPartner._check_phone_format([p])  # không raise, dấu . bị lọc trước

    def test_invalid_prefix_raises(self):
        """TC-UNIT-ResPartner-030: SĐT sai đầu số (bắt đầu bằng 1 thay vì 0/+84)
        thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", phone="1912345678")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])

    def test_too_short_raises(self):
        """TC-UNIT-ResPartner-031: SĐT quá ngắn thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", phone="0912345")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])

    def test_mobile_field_also_checked(self):
        """TC-UNIT-ResPartner-032: phone rỗng nhưng mobile sai định dạng thì vẫn
        báo lỗi ValidationError, vì constraint kiểm tra cả field mobile."""
        p = _partner(partner_role="customer", phone=False, mobile="abc")
        with self.assertRaises(ValidationError):
            ResPartner._check_phone_format([p])


class TestCheckEmailFormat(unittest.TestCase):
    def test_valid_email(self):
        """TC-UNIT-ResPartner-033: email đúng định dạng thì không raise."""
        p = _partner(partner_role="customer", email="test@example.com")
        ResPartner._check_email_format([p])  # không raise

    def test_invalid_email_raises(self):
        """TC-UNIT-ResPartner-034: email sai định dạng thì báo lỗi
        ValidationError."""
        p = _partner(partner_role="customer", email="not-an-email")
        with self.assertRaises(ValidationError):
            ResPartner._check_email_format([p])

    def test_no_email_skips(self):
        """TC-UNIT-ResPartner-035: không nhập email thì không raise."""
        p = _partner(partner_role="customer", email=False)
        ResPartner._check_email_format([p])  # không raise


class TestCheckContactPhoneFormat(unittest.TestCase):
    def test_contact_invalid_phone_raises(self):
        """TC-UNIT-ResPartner-036: contact của khách hàng có SĐT sai định dạng
        thì báo lỗi ValidationError, contact cũng bị kiểm tra như bản ghi
        khách hàng gốc."""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"),
                     phone="123")
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_phone_format([p])

    def test_non_contact_exempt(self):
        """TC-UNIT-ResPartner-037: bản ghi không phải contact (không có
        parent_id) có SĐT sai định dạng thì không raise, vì constraint này chỉ
        áp dụng cho contact."""
        p = _partner(parent_id=None, phone="123")
        ResPartner._check_contact_phone_format([p])  # không raise, không phải contact


class TestCheckContactEmailFormat(unittest.TestCase):
    def test_contact_invalid_email_raises(self):
        """TC-UNIT-ResPartner-038: contact của khách hàng có email sai định
        dạng thì báo lỗi ValidationError."""
        p = _partner(parent_id=SimpleNamespace(id=1),
                     commercial_partner_id=SimpleNamespace(partner_role="customer"),
                     email="bad-email")
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_email_format([p])


# _check_unique_tax_code() / write() (khoá vô hiệu hoá KH)
class _TaxCodeRS(list):
    def __init__(self, records, search_result):
        super().__init__(records)
        self._search_result = search_result

    def with_context(self, **kw):
        return self

    def search(self, domain, limit=None):
        return self._search_result


class TestCheckUniqueTaxCode(unittest.TestCase):
    def test_duplicate_tax_code_raises(self):
        """TC-UNIT-ResPartner-039: search ra một bản ghi khác đã dùng cùng MST,
        dlm_allow_dup_tax False thì báo lỗi ValidationError."""
        dup = SimpleNamespace(name="Công ty A", dlm_code="KH0001")
        dup._dlm_display_code = lambda: dup.dlm_code
        rec = _partner(id=1, partner_role="customer", partner_type="company",
                        vat="0123456789", dlm_allow_dup_tax=False)
        rs = _TaxCodeRS([rec], dup)
        with self.assertRaises(ValidationError):
            ResPartner._check_unique_tax_code(rs)

    def test_allow_dup_tax_bypasses_check(self):
        """TC-UNIT-ResPartner-040: có bản ghi trùng MST nhưng dlm_allow_dup_tax
        True thì không raise, cờ này cho phép bỏ qua kiểm tra trùng."""
        dup = SimpleNamespace(name="Công ty A", dlm_code="KH0001")
        rec = _partner(id=1, partner_role="customer", partner_type="company",
                        vat="0123456789", dlm_allow_dup_tax=True)
        rs = _TaxCodeRS([rec], dup)
        ResPartner._check_unique_tax_code(rs)  # không raise

    def test_no_vat_skips_check(self):
        """Không có MST thì bỏ qua kiểm tra trùng MST, không raise."""
        rec = _partner(partner_role="customer", partner_type="company",
                        vat=False, dlm_allow_dup_tax=False)
        rs = _TaxCodeRS([rec], SimpleNamespace())
        ResPartner._check_unique_tax_code(rs)  # không raise


class TestCheckPartnerName(unittest.TestCase):
    def test_dlm_partner_empty_name_raises(self):
        """TC-UNIT-ResPartner-043: đối tác cấp cao (KH/NCC) không nhập Tên
        thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", parent_id=None, name="")
        p._dl_partner_kind_label = lambda: ResPartner._dl_partner_kind_label(p)
        with self.assertRaises(ValidationError):
            ResPartner._check_partner_name([p])

    def test_dlm_partner_whitespace_only_name_raises(self):
        """Tên chỉ có khoảng trắng (chưa strip) cũng bị coi là rỗng, vẫn báo
        lỗi ValidationError."""
        p = _partner(partner_role="supplier", parent_id=None, name="   ")
        p._dl_partner_kind_label = lambda: ResPartner._dl_partner_kind_label(p)
        with self.assertRaises(ValidationError):
            ResPartner._check_partner_name([p])

    def test_non_dlm_partner_exempt(self):
        """Bản ghi không có partner_role (không phải đối tác DLM) thì không
        raise dù Tên rỗng."""
        p = _partner(partner_role=False, parent_id=None, name="")
        ResPartner._check_partner_name([p])  # không raise, không phải đối tác DLM

    def test_dlm_partner_with_name_passes(self):
        """Đối tác cấp cao đã có Tên thì không raise."""
        p = _partner(partner_role="customer", parent_id=None, name="Công ty ABC")
        p._dl_partner_kind_label = lambda: ResPartner._dl_partner_kind_label(p)
        ResPartner._check_partner_name([p])  # không raise


class TestCheckCustomerAddress(unittest.TestCase):
    def test_company_missing_street_and_city_raises(self):
        """TC-UNIT-ResPartner-044: khách hàng loại Doanh nghiệp thiếu cả
        Đường và Tỉnh/TP thì báo lỗi ValidationError."""
        p = _partner(partner_role="customer", partner_type="company",
                      street="", city="")
        with self.assertRaises(ValidationError):
            ResPartner._check_customer_address(_PRS([p]))

    def test_dealer_missing_street_only_raises(self):
        """Khách Đại lý có Tỉnh/TP nhưng thiếu Đường thì vẫn báo lỗi
        ValidationError."""
        p = _partner(partner_role="customer", partner_type="dealer",
                      street="", city="Hà Nội")
        with self.assertRaises(ValidationError):
            ResPartner._check_customer_address(_PRS([p]))

    def test_company_with_full_address_passes(self):
        """Khách Doanh nghiệp đã có đủ Đường và Tỉnh/TP thì không raise."""
        p = _partner(partner_role="customer", partner_type="company",
                      street="123 Lê Lợi", city="Hà Nội")
        ResPartner._check_customer_address(_PRS([p]))  # không raise

    def test_individual_exempt(self):
        """Khách hàng Cá nhân không bắt buộc địa chỉ, không raise dù thiếu
        Đường và Tỉnh/TP."""
        p = _partner(partner_role="customer", partner_type="individual",
                      street="", city="")
        ResPartner._check_customer_address([p])  # không raise, cá nhân miễn địa chỉ

    def test_contact_row_exempt(self):
        """Dòng người liên hệ (có parent_id) không phải bản ghi khách hàng
        gốc nên không raise, dù thiếu địa chỉ."""
        p = _partner(partner_role="customer", partner_type="company",
                      parent_id=SimpleNamespace(id=1), street="", city="")
        ResPartner._check_customer_address([p])  # không raise, không phải KH gốc


class TestCheckContactName(unittest.TestCase):
    def test_person_contact_empty_name_raises(self):
        """TC-UNIT-ResPartner-045: dòng người liên hệ (type contact) của
        khách hàng chưa nhập Họ tên thì báo lỗi ValidationError."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="contact",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      name="")
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_name([p])

    def test_person_contact_name_too_short_raises(self):
        """Họ tên người liên hệ ngắn hơn _MIN_NAME_LEN (1 ký tự) thì báo lỗi
        ValidationError."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="contact",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      name="A")
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_name([p])

    def test_address_row_type_exempt(self):
        """Dòng dạng địa chỉ (type khác 'contact') không tính là người liên
        hệ, không raise dù tên rỗng."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="delivery",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      name="")
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        ResPartner._check_contact_name([p])  # không raise, không phải dòng người liên hệ

    def test_person_contact_with_valid_name_passes(self):
        """Người liên hệ đã có Họ tên đủ dài thì không raise."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="contact",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      name="Nguyễn Văn A")
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        ResPartner._check_contact_name([p])  # không raise


class TestCheckContactChannel(unittest.TestCase):
    def test_person_contact_no_channel_raises(self):
        """TC-UNIT-ResPartner-046: dòng người liên hệ không có Điện thoại,
        Di động hay Email nào thì báo lỗi ValidationError."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="contact",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      phone=False, mobile=False, email=False)
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        with self.assertRaises(ValidationError):
            ResPartner._check_contact_channel([p])

    def test_person_contact_with_email_only_passes(self):
        """Người liên hệ chỉ có Email (không có Điện thoại/Di động) vẫn coi
        là đủ kênh liên lạc, không raise."""
        p = _partner(parent_id=SimpleNamespace(id=1), type="contact",
                      commercial_partner_id=SimpleNamespace(partner_role="customer"),
                      phone=False, mobile=False, email="a@example.com")
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        ResPartner._check_contact_channel([p])  # không raise

    def test_non_contact_exempt(self):
        """Bản ghi không phải dòng người liên hệ (không có parent_id) thì
        không raise dù không có kênh liên lạc nào."""
        p = _partner(parent_id=None, phone=False, mobile=False, email=False)
        p._dl_is_customer_person_contact = lambda: ResPartner._dl_is_customer_person_contact(p)
        ResPartner._check_contact_channel([p])  # không raise, không phải người liên hệ


class TestWriteDeactivateGuard(unittest.TestCase):
    def test_unauthorized_role_cannot_deactivate_customer(self):
        """TC-UNIT-ResPartner-041: user không phải superuser và không có quyền
        cần thiết cố ghi active=False cho một khách hàng thì bị chặn bằng
        AccessError."""
        rec = _partner(partner_role="customer")
        rs = _PRS([rec])
        rs.env = SimpleNamespace(
            su=False,
            user=SimpleNamespace(has_group=lambda g: False))
        # _dlm_check_archive_right() đọc self.env.user ở CẤP TỪNG rec (không phải
        # rs) — gán riêng cho rec, cùng bộ role giả không thuộc nhóm nào được phép.
        rec.env = rs.env
        rec._dlm_check_archive_right = lambda: ResPartner._dlm_check_archive_right(rec)
        with self.assertRaises(AccessError):
            ResPartner.write(rs, {"active": False})


if __name__ == "__main__":
    unittest.main()
