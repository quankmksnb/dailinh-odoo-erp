# -*- coding: utf-8 -*-
"""L2 Integration test (Chiều 3, Background Job) cho
dl.quotation.request.line._cron_cleanup_rfq_provisional_records(), cron thật
duy nhất trong dl_technical liên quan RFQ (ir.cron
'cron_cleanup_rfq_provisional_records', dl_technical/data/
rfq_provisional_data.xml, chạy hằng ngày). Không khớp JOB-01..06 nào trong
FDS §5, xem Report 5 §1.6. Gọi trực tiếp method, set sẵn write_date để mô
phỏng "đã bị bỏ dở quá N ngày" (mặc định 7, qua ir.config_parameter
dl_technical.rfq_provisional_cleanup_days).
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_technical")
class TestCronCleanupRfqProvisional(TransactionCase):

    def _age(self, model_name, record_id, days_old):
        old_date = fields.Datetime.subtract(fields.Datetime.now(), days=days_old)
        table = self.env[model_name]._table
        self.env.cr.execute(
            f"UPDATE {table} SET write_date = %s WHERE id = %s",
            (old_date, record_id),
        )
        self.env[model_name].browse(record_id).invalidate_recordset(["write_date"])

    def test_orphan_provisional_bom_older_than_threshold_is_cleaned(self):
        """TC-SCH-CRON-RFQPROV-001: BOM tạm (is_rfq_provisional=True) không còn được dòng
        RFQ nào tham chiếu, bỏ dở quá 7 ngày thì bị dọn.
        """
        product = self.env["product.product"].create({
            "name": "SP tạm RFQ mồ côi (test cron)",
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
        })
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "quotation",
            "is_rfq_provisional": True,
        })
        self._age("dl.bom", bom.id, days_old=8)
        bom_id = bom.id

        self.env["dl.quotation.request.line"]._cron_cleanup_rfq_provisional_records()

        self.assertFalse(
            self.env["dl.bom"].browse(bom_id).exists(),
            "BOM tạm mồ côi bỏ dở quá 7 ngày phải bị dọn")

    def test_recent_provisional_bom_within_threshold_kept(self):
        """TC-SCH-CRON-RFQPROV-002: BOM tạm mới được sửa 2 ngày trước, chưa qua ngưỡng 7
        ngày, thì không bị dọn (biên dưới).
        """
        product = self.env["product.product"].create({
            "name": "SP tạm RFQ mới (test cron)",
            "product_kind": "manufactured",
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
        })
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "quotation",
            "is_rfq_provisional": True,
        })
        self._age("dl.bom", bom.id, days_old=2)
        bom_id = bom.id

        self.env["dl.quotation.request.line"]._cron_cleanup_rfq_provisional_records()

        self.assertTrue(
            self.env["dl.bom"].browse(bom_id).exists(),
            "BOM tạm chưa quá ngưỡng ngày thì chưa bị dọn")

    def test_non_provisional_bom_never_touched(self):
        """TC-SCH-CRON-RFQPROV-003: BOM không phải tạm RFQ (is_rfq_provisional=False), dù
        cũ đến đâu, cũng không nằm trong phạm vi cron này.
        """
        product = self.env["product.product"].create({
            "name": "SP chuẩn (test cron, không phải tạm)",
            "product_kind": "manufactured",
        })
        bom = self.env["dl.bom"].create({
            "product_id": product.id,
            "bom_type": "template",
        })
        self._age("dl.bom", bom.id, days_old=100)
        bom_id = bom.id

        self.env["dl.quotation.request.line"]._cron_cleanup_rfq_provisional_records()

        self.assertTrue(self.env["dl.bom"].browse(bom_id).exists())

    def test_no_provisional_records_runs_without_error(self):
        """TC-SCH-CRON-RFQPROV-004: không có bản ghi tạm nào thì cron vẫn chạy không lỗi.
        """
        result = self.env[
            "dl.quotation.request.line"]._cron_cleanup_rfq_provisional_records()
        self.assertTrue(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
