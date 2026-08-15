# -*- coding: utf-8 -*-
"""L2 Integration test (Chiều 3: Background Job) cho
dl.quotation._cron_expire_quotations(), cron thật duy nhất trong dl_sale
(ir.cron 'cron_dl_quotation_expire', dl_sale/data/quotation_cron.xml, chạy
hằng ngày). Không khớp job nào trong JOB-01..06 của FDS §5, xem Report 5
§1.6. Test gọi trực tiếp method, set sẵn validity_date để mô phỏng báo giá
đã quá hạn hiệu lực.
"""
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "dl_quotation")
class TestCronExpireQuotations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "KH test cron expire", "partner_role": "customer"})

    def _make_quotation(self, state, validity_date, date_order=None):
        vals = {
            "partner_id": self.customer.id,
            "state": state,
            "validity_date": validity_date,
        }
        if date_order:
            vals["date_order"] = date_order
        return self.env["dl.quotation"].create(vals)

    def test_sent_quotation_past_validity_date_expires(self):
        """TC-SCH-CRON-QUOTATION-001: báo giá đã gửi khách (sent), hạn hiệu
        lực đã qua thì tự chuyển sang 'expired'."""
        from odoo import fields
        past = fields.Date.subtract(fields.Date.today(), days=1)
        older = fields.Date.subtract(fields.Date.today(), days=5)
        # date_order phải <= validity_date (constraint _check_validity_after_order),
        # nên lùi cả 2 mốc ra quá khứ để mô phỏng báo giá đã phát hành từ trước rồi hết hạn.
        quo = self._make_quotation("sent", past, date_order=older)

        self.env["dl.quotation"]._cron_expire_quotations()

        self.assertEqual(quo.state, "expired")

    def test_sent_quotation_validity_date_today_not_expired(self):
        """TC-SCH-CRON-QUOTATION-002: hạn hiệu lực đúng bằng hôm nay (biên),
        so sánh dùng '<' không phải '<=' nên chưa hết hiệu lực."""
        from odoo import fields
        today = fields.Date.today()
        quo = self._make_quotation("sent", today)

        self.env["dl.quotation"]._cron_expire_quotations()

        self.assertEqual(quo.state, "sent", "Đúng hạn (chưa qua) thì chưa hết hiệu lực")

    def test_sent_quotation_no_validity_date_not_touched(self):
        """TC-SCH-CRON-QUOTATION-003: báo giá sent nhưng validity_date rỗng
        thì không đủ điều kiện, cron không đụng tới."""
        quo = self._make_quotation("sent", False)

        self.env["dl.quotation"]._cron_expire_quotations()

        self.assertEqual(quo.state, "sent")

    def test_draft_quotation_past_date_not_touched(self):
        """TC-SCH-CRON-QUOTATION-004: báo giá nháp (chưa gửi khách) dù hạn đã
        qua vẫn không bị đụng vì cron chỉ xử lý state='sent'."""
        from odoo import fields
        past = fields.Date.subtract(fields.Date.today(), days=5)
        older = fields.Date.subtract(fields.Date.today(), days=10)
        quo = self._make_quotation("draft", past, date_order=older)

        self.env["dl.quotation"]._cron_expire_quotations()

        self.assertEqual(quo.state, "draft")

    def test_no_stale_quotations_runs_without_error(self):
        """TC-SCH-CRON-QUOTATION-005: không có báo giá nào quá hạn thì cron
        vẫn chạy không lỗi."""
        result = self.env["dl.quotation"]._cron_expire_quotations()
        self.assertTrue(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
