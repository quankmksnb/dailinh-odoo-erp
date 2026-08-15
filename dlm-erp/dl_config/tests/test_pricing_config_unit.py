# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.pricing.config.

Model dl.pricing.config hiện chỉ còn 2 tham số (vat_pct, rounding_to); các
màn cấu hình khác (markup, chiết khấu, công đoạn, hao hụt, ma trận phê
duyệt...) đã chuyển sang các model quy tắc V3 riêng, có sheet/test L1 riêng.

Chỉ 2 method còn thuần Python, không đụng self.env/ORM: _round_label() và
_check_quote_settings(). Các method còn lại (_can_edit, _get_singleton,
get_quote_settings, save_quote_settings) đụng self.env nên thuộc L2, không
test ở đây.
"""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.pricing_config import DlPricingConfig


def _cfg(**kw):
    base = dict(vat_pct=10.0, rounding_to=1000)
    base.update(kw)
    rec = SimpleNamespace(**base)
    return rec


class TestRoundLabel(unittest.TestCase):
    def test_zero_means_no_rounding(self):
        """TC-UNIT-DlPricingConfig-001: rounding_to=0 thì nhãn hiển thị là
        "Không làm tròn"."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 0), "Không làm tròn")

    def test_1000_known_label(self):
        """TC-UNIT-DlPricingConfig-002: rounding_to=1000 trả về nhãn có sẵn
        "Làm tròn đến 1.000đ"."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 1000), "Làm tròn đến 1.000đ")

    def test_10000_known_label(self):
        """TC-UNIT-DlPricingConfig-003: rounding_to=10000 trả về nhãn có sẵn
        "Làm tròn đến 10.000đ"."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 10000), "Làm tròn đến 10.000đ")

    def test_unknown_value_falls_back_to_str(self):
        """TC-UNIT-DlPricingConfig-004: giá trị không nằm trong 3 mốc đã đặt tên
        (0/1000/10000) thì hiển thị nguyên số, không lỗi."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, 500), "500")

    def test_none_treated_as_zero(self):
        """TC-UNIT-DlPricingConfig-005: rounding_to=None được coi như 0 (int(v or 0)),
        nên trả về nhãn "Không làm tròn" thay vì lỗi."""
        rec = _cfg()
        self.assertEqual(DlPricingConfig._round_label(rec, None), "Không làm tròn")


class TestCheckQuoteSettings(unittest.TestCase):
    def _check(self, rec):
        DlPricingConfig._check_quote_settings([rec])

    def test_happy_within_range(self):
        """TC-UNIT-DlPricingConfig-006: vat_pct và rounding_to hợp lệ, nằm trong biên
        cho phép, thì _check_quote_settings() không raise."""
        rec = _cfg(vat_pct=10.0, rounding_to=1000)
        self._check(rec)  # không raise

    def test_vat_boundary_0_allowed(self):
        """TC-UNIT-DlPricingConfig-007: biên dưới, VAT=0 hợp lệ."""
        rec = _cfg(vat_pct=0.0, rounding_to=0)
        self._check(rec)

    def test_vat_boundary_100_allowed(self):
        """TC-UNIT-DlPricingConfig-008: biên trên, VAT=100 hợp lệ."""
        rec = _cfg(vat_pct=100.0, rounding_to=0)
        self._check(rec)

    def test_vat_negative_raises(self):
        """TC-UNIT-DlPricingConfig-009: vat_pct âm (-1.0) thì báo lỗi ValidationError."""
        rec = _cfg(vat_pct=-1.0)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_vat_above_100_raises(self):
        """TC-UNIT-DlPricingConfig-010: vat_pct vượt quá 100 (100.1) thì báo lỗi
        ValidationError."""
        rec = _cfg(vat_pct=100.1)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_rounding_negative_raises(self):
        """TC-UNIT-DlPricingConfig-011: rounding_to âm (-1) thì báo lỗi
        ValidationError."""
        rec = _cfg(rounding_to=-1)
        with self.assertRaises(ValidationError):
            self._check(rec)

    def test_rounding_zero_allowed(self):
        """TC-UNIT-DlPricingConfig-012: rounding_to=0 nghĩa là không làm tròn, hợp lệ."""
        rec = _cfg(rounding_to=0)
        self._check(rec)


# get_quote_settings() đụng self.env.search/create (singleton) nên không
# thuần L1 như các test trên. Đặt cùng file cho dễ đối chiếu, chạy qua
# odoo.tests.common.TransactionCase (DB thật).
from odoo.tests.common import TransactionCase, tagged  # noqa: E402


@tagged("post_install", "-at_install", "dl_config")
class TestGetQuoteSettings(TransactionCase):
    def test_returns_singleton_values_and_can_edit_flag(self):
        """TC-UNIT-DlPricingConfig-013: admin gọi get_quote_settings() trên bản ghi
        singleton đã ghi vat_pct=10, rounding_to=1000 thì nhận đúng các giá trị này
        kèm canEdit=True."""
        admin_user = self.env["res.users"].create({
            "name": "Admin test get_quote_settings", "login": "admin_gqs_test",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("dl_base.dl_group_admin").id,
            ])],
        })
        Config = self.env["dl.pricing.config"].with_user(admin_user)
        cfg = Config._get_singleton()
        cfg.sudo().write({"vat_pct": 10.0, "rounding_to": 1000})
        result = Config.get_quote_settings()
        self.assertEqual(result, {"vat": 10.0, "rounding": 1000, "canEdit": True})


if __name__ == "__main__":
    unittest.main()
