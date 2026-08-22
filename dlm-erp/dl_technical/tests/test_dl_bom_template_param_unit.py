# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.template.param và
dl.bom.template.line.param.map. Sheet nguồn: DlBomTemplateParam.

_check_domain(): tối thiểu không được lớn hơn tối đa.
_check_same_template() (trên DlBomTemplateLineParamMap): tham số ánh xạ phải
cùng BOM mẫu với dòng vật tư mẫu."""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_bom_template_param import (
    DlBomTemplateLineParamMap,
    DlBomTemplateParam,
)


class TestCheckDomain(unittest.TestCase):
    def test_min_greater_than_max_raises(self):
        """TC-UNIT-DlBomTemplateParam-001: value_min > value_max thì
        _check_domain() báo lỗi ValidationError."""
        rec = SimpleNamespace(value_min=10.0, value_max=5.0, code="D")
        with self.assertRaises(ValidationError):
            DlBomTemplateParam._check_domain([rec])

    def test_min_equal_max_passes(self):
        """value_min = value_max (biên bằng nhau) thì không báo lỗi."""
        rec = SimpleNamespace(value_min=5.0, value_max=5.0, code="D")
        DlBomTemplateParam._check_domain([rec])  # không raise

    def test_min_or_max_zero_not_checked(self):
        """value_min=0 (falsy, coi như chưa khai) thì bỏ qua kiểm tra dù
        value_max nhỏ hơn nếu value_min thật sự có giá trị."""
        rec = SimpleNamespace(value_min=0.0, value_max=5.0, code="D")
        DlBomTemplateParam._check_domain([rec])  # không raise


class TestCheckSameTemplate(unittest.TestCase):
    def test_different_template_raises(self):
        """TC-UNIT-DlBomTemplateParam-002: tham số và dòng vật tư mẫu thuộc
        hai BOM mẫu khác nhau thì _check_same_template() báo lỗi
        ValidationError."""
        param = SimpleNamespace(bom_template_id="tmpl_1")
        template_line = SimpleNamespace(bom_template_id="tmpl_2")
        rec = SimpleNamespace(param_id=param, template_line_id=template_line)
        with self.assertRaises(ValidationError):
            DlBomTemplateLineParamMap._check_same_template([rec])

    def test_same_template_passes(self):
        """Tham số và dòng vật tư mẫu cùng một BOM mẫu thì không báo lỗi."""
        param = SimpleNamespace(bom_template_id="tmpl_1")
        template_line = SimpleNamespace(bom_template_id="tmpl_1")
        rec = SimpleNamespace(param_id=param, template_line_id=template_line)
        DlBomTemplateLineParamMap._check_same_template([rec])  # không raise


if __name__ == "__main__":
    unittest.main()
