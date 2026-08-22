# -*- coding: utf-8 -*-
"""Unit test L1 (thuần, không ORM/DB) cho dl.bom.operation.line. Sheet nguồn:
DlBomOperationLine.

Chỉ test 2 constraint thuần, không đụng self.env: _check_base_qty() và
_check_outsource_partner(). Các compute (_compute_active_rule/_compute_estimate)
đụng self.env["dl.pricing.operation.rule"] nên không test ở đây."""
import unittest
from types import SimpleNamespace

from odoo.exceptions import ValidationError

from ..models.dl_bom_operation_line import DlBomOperationLine


class TestCheckBaseQty(unittest.TestCase):
    def test_negative_raises(self):
        """TC-UNIT-DlBomOperationLine-001: base_qty âm (-1.0) thì
        _check_base_qty() báo lỗi ValidationError."""
        line = SimpleNamespace(base_qty=-1.0)
        with self.assertRaises(ValidationError):
            DlBomOperationLine._check_base_qty([line])

    def test_zero_boundary_passes(self):
        """base_qty=0 (biên dưới) thì không báo lỗi."""
        line = SimpleNamespace(base_qty=0.0)
        DlBomOperationLine._check_base_qty([line])  # không raise

    def test_positive_passes(self):
        """base_qty dương (5.0) thì không báo lỗi."""
        line = SimpleNamespace(base_qty=5.0)
        DlBomOperationLine._check_base_qty([line])  # không raise


class TestCheckOutsourcePartner(unittest.TestCase):
    def test_partner_without_outsourced_flag_raises(self):
        """TC-UNIT-DlBomOperationLine-002: đã chọn nhà cung cấp gia công
        (partner_id) nhưng chưa đánh dấu is_outsourced thì
        _check_outsource_partner() báo lỗi ValidationError."""
        operation = SimpleNamespace(display_name="Cắt")
        partner = SimpleNamespace(display_name="NCC A")
        line = SimpleNamespace(partner_id=partner, is_outsourced=False, operation_id=operation)
        with self.assertRaises(ValidationError):
            DlBomOperationLine._check_outsource_partner([line])

    def test_partner_with_outsourced_flag_passes(self):
        """Có partner_id và đã đánh dấu is_outsourced=True thì không báo lỗi."""
        operation = SimpleNamespace(display_name="Cắt")
        partner = SimpleNamespace(display_name="NCC A")
        line = SimpleNamespace(partner_id=partner, is_outsourced=True, operation_id=operation)
        DlBomOperationLine._check_outsource_partner([line])  # không raise

    def test_no_partner_passes(self):
        """Không chọn nhà cung cấp gia công thì không báo lỗi dù is_outsourced
        đang False."""
        line = SimpleNamespace(partner_id=None, is_outsourced=False, operation_id=None)
        DlBomOperationLine._check_outsource_partner([line])  # không raise


if __name__ == "__main__":
    unittest.main()
