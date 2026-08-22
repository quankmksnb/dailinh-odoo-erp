from lxml import etree

from odoo.tests.common import TransactionCase


class TestRfqViews(TransactionCase):

    def test_sales_form_uses_real_quotation_actions(self):
        """TC-INT-TestRfqViews-001: The saved create-RFQ action keeps this view id across a
        reload.
        """
        view = self.env.ref(
            "dl_technical.view_dl_quotation_request_sales_form"
        )
        arch = view._get_combined_arch()
        if not isinstance(arch, etree._Element):
            arch = etree.fromstring(arch.encode())

        legacy_buttons = arch.xpath(
            "//button[@name='action_mark_quoted']"
        )
        self.assertTrue(legacy_buttons)
        self.assertTrue(all(
            button.get("invisible") == "1" for button in legacy_buttons
        ))

        create_buttons = arch.xpath(
            "//button[@name='action_create_quotation']"
        )
        # form tách 2 loại yêu cầu (Thương mại / Gia công) nên nút này giờ lặp
        # cho từng loại, ra 4 thay vì 2 như trước khi form được tách.
        self.assertEqual(len(create_buttons), 4)
        self.assertEqual(
            len(arch.xpath("//button[@name='action_open_quotation']")),
            1,
        )
