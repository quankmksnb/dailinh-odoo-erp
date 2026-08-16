# -*- coding: utf-8 -*-
"""L2 Integration test (cắt ngang, Security) cho GB-06 (PRD §5.1): "Dữ liệu
chi phí nội bộ chỉ CEO, Trưởng phòng KD, Kế toán, Admin được xem. NV Kinh
doanh và Kỹ thuật viên không được xem." Che ở tầng field-level theo vai trò
(UC-082, UC-003).

Không gắn với một endpoint/controller cụ thể (khác các test RBAC record-rule
như LKT-12 trong test_bom_btp_linkage.py). Test này kiểm field-level
`groups=` trên dl.bom.line (price_snapshot, recovery_value, subtotal) và
dl.bom (total_operation_cost_est), dùng cơ chế Odoo lõi tại
BaseModel.fields_get()/check_field_access_rights() (odoo/models.py).
"""
from odoo.tests.common import TransactionCase, tagged

COST_LINE_FIELDS = ("price_snapshot", "recovery_value", "subtotal")


@tagged("post_install", "-at_install", "dl_security")
class TestCostFieldVisibilitySecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.material = cls.env["product.product"].create({
            "name": "Vật tư GB06 (test)", "product_kind": "material",
        })
        cls.finished = cls.env["product.product"].create({
            "name": "SP GB06 (test)", "product_kind": "manufactured",
        })
        cls.bom = cls.env["dl.bom"].create({
            "product_id": cls.finished.id,
            "bom_type": "template",
            "version": 1,
            "line_ids": [(0, 0, {
                "material_id": cls.material.id,
                "quantity": 2.0,
            })],
        })
        cls.line = cls.bom.line_ids[0]

    def _user(self, group_xmlid, login):
        return self.env["res.users"].create({
            "name": login,
            "login": login,
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref(group_xmlid).id,
            ])],
        })

    # dl.bom.line: price_snapshot / recovery_value / subtotal
    def test_sales_staff_cannot_see_bom_line_cost_fields(self):
        """TC-SEC-GB06-001: NV kinh doanh gọi fields_get() trên 3 field chi phí dòng BOM,
        kỳ vọng không field nào được trả về (bị che hoàn toàn).
        """
        sales = self._user("dl_base.dl_group_ba", "sales_gb06")
        visible = self.line.with_user(sales).fields_get(list(COST_LINE_FIELDS))
        self.assertEqual(visible, {}, "NV Kinh doanh không được thấy field chi phí (GB-06)")

    def test_technician_cannot_see_bom_line_cost_fields(self):
        """TC-SEC-GB06-002: Kỹ thuật viên cũng bị che 3 field chi phí dòng BOM, tương tự NV
        kinh doanh.
        """
        tech = self._user("dl_base.dl_group_tech", "ktv_gb06")
        visible = self.line.with_user(tech).fields_get(list(COST_LINE_FIELDS))
        self.assertEqual(visible, {}, "Kỹ thuật viên không được thấy field chi phí (GB-06)")

    def test_sales_manager_can_see_bom_line_cost_fields(self):
        """TC-SEC-GB06-003: Trưởng phòng kinh doanh được phép xem đủ cả 3 field chi phí
        dòng BOM.
        """
        mgr = self._user("dl_base.dl_group_sales_manager", "tpkd_gb06")
        visible = self.line.with_user(mgr).fields_get(list(COST_LINE_FIELDS))
        self.assertEqual(set(visible.keys()), set(COST_LINE_FIELDS))

    def test_accountant_can_see_bom_line_cost_fields(self):
        """TC-SEC-GB06-004: Kế toán được phép xem đủ cả 3 field chi phí dòng BOM.
        """
        acc = self._user("dl_base.dl_group_accountant", "ketoan_gb06")
        visible = self.line.with_user(acc).fields_get(list(COST_LINE_FIELDS))
        self.assertEqual(set(visible.keys()), set(COST_LINE_FIELDS))

    def test_ceo_can_see_bom_line_cost_fields(self):
        """TC-SEC-GB06-005: CEO được phép xem đủ cả 3 field chi phí dòng BOM.
        """
        ceo = self._user("dl_base.dl_group_ceo", "ceo_gb06")
        visible = self.line.with_user(ceo).fields_get(list(COST_LINE_FIELDS))
        self.assertEqual(set(visible.keys()), set(COST_LINE_FIELDS))

    # dl.bom: total_operation_cost_est (ước tính chi phí công đoạn/đơn vị)
    def test_technician_cannot_see_bom_operation_cost_est(self):
        """TC-SEC-GB06-006: Kỹ thuật viên gọi fields_get() trên total_operation_cost_est
        của BOM, kỳ vọng field bị che hoàn toàn.
        """
        tech = self._user("dl_base.dl_group_tech", "ktv_gb06_op")
        visible = self.bom.with_user(tech).fields_get(["total_operation_cost_est"])
        self.assertEqual(visible, {}, "Kỹ thuật viên không được thấy ước tính chi phí công đoạn (GB-06)")

    def test_ceo_can_see_bom_operation_cost_est(self):
        """TC-SEC-GB06-007: CEO được phép xem total_operation_cost_est của BOM.
        """
        ceo = self._user("dl_base.dl_group_ceo", "ceo_gb06_op")
        visible = self.bom.with_user(ceo).fields_get(["total_operation_cost_est"])
        self.assertEqual(set(visible.keys()), {"total_operation_cost_est"})


if __name__ == "__main__":
    import unittest
    unittest.main()
