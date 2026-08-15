# -*- coding: utf-8 -*-
"""L2 Integration test (Chiều 3, Background Job) cho
product.product._cron_obsolete_orphan_drafts(), cron thật duy nhất tìm thấy
trong dl_product (ir.cron 'cron_obsolete_orphan_drafts', dl_product/data/
dl_product_data.xml, chạy hằng ngày). Không khớp JOB-01..06 nào trong FDS §5,
xem Report 5 §1.6. Test gọi trực tiếp method thay vì qua ir.cron trigger thật,
và set sẵn create_date để mô phỏng "đã quá hạn N ngày" theo đúng kỹ thuật
Testing Guide §Background Job Testing.
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_product")
class TestCronObsoleteOrphanDrafts(TransactionCase):

    def _make_draft(self, name, kind="manufactured", days_old=40):
        product = self.env["product.product"].create({
            "name": name,
            "product_kind": kind,
            "dlm_lifecycle_state": "draft",
        })
        old_date = fields.Datetime.subtract(fields.Datetime.now(), days=days_old)
        # create_date là field readonly qua ORM nên ghi thẳng qua SQL để mô phỏng
        # "đã tạo từ N ngày trước", đúng kỹ thuật time-manipulation của Testing Guide.
        self.env.cr.execute(
            "UPDATE product_product SET create_date = %s WHERE id = %s",
            (old_date, product.id),
        )
        product.invalidate_recordset(["create_date"])
        return product

    def test_orphan_draft_older_than_threshold_becomes_obsolete(self):
        """TC-SCH-CRON-PRODUCT-001: nháp mồ côi quá hạn (mặc định 30 ngày, tạo 40 ngày
        trước, không đơn nào dùng) thì tự chuyển sang 'obsolete'."""
        product = self._make_draft("SP nháp mồ côi quá hạn (test)", days_old=40)

        self.env["product.product"]._cron_obsolete_orphan_drafts()

        self.assertEqual(product.dlm_lifecycle_state, "obsolete")

    def test_orphan_draft_within_threshold_not_touched(self):
        """TC-SCH-CRON-PRODUCT-002: nháp mồ côi mới tạo 5 ngày, chưa qua ngưỡng 30 ngày,
        nên không bị đụng."""
        product = self._make_draft("SP nháp mồ côi mới (test)", days_old=5)

        self.env["product.product"]._cron_obsolete_orphan_drafts()

        self.assertEqual(product.dlm_lifecycle_state, "draft")

    def test_draft_used_by_sale_order_line_not_touched(self):
        """TC-SCH-CRON-PRODUCT-003: nháp quá hạn nhưng đã có dòng đơn bán chưa huỷ
        tham chiếu nên không phải mồ côi, không bị đụng."""
        product = self._make_draft("SP nháp có đơn dùng (test)", days_old=40)
        customer = self.env["res.partner"].create({
            "name": "KH test cron orphan", "partner_role": "customer"})
        order = self.env["dl.sale.order"].create({
            "partner_id": customer.id,
            "line_ids": [(0, 0, {
                "name": product.display_name, "product_id": product.id,
                "qty": 1.0, "price_unit": 100.0,
            })],
        })
        self.assertTrue(order.line_ids)

        self.env["product.product"]._cron_obsolete_orphan_drafts()

        self.assertEqual(
            product.dlm_lifecycle_state, "draft",
            "SP còn Nháp nhưng đã có đơn bán tham chiếu thì không phải mồ côi")

    def test_no_orphan_drafts_runs_without_error(self):
        """TC-SCH-CRON-PRODUCT-004: không có SP nháp mồ côi nào thì cron chạy không lỗi,
        không đụng dữ liệu khác."""
        result = self.env["product.product"]._cron_obsolete_orphan_drafts()
        self.assertTrue(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
