# -*- coding: utf-8 -*-
"""Dialog "Xuất / Gửi đơn" trên đơn mua: Tải về PDF hoặc mở trình soạn thư đã đính sẵn.

Gộp ba nút cũ ([In yêu cầu báo giá] / [In đơn đặt hàng] / [Gửi mail cho NCC]) về
một cửa (cùng khuôn dialog "Xuất / Gửi báo giá" của dl_sale). Chứng từ tự đổi
giọng theo trạng thái đơn — logic dựng PDF và soạn thư vẫn nằm ở dl.purchase.order,
wizard chỉ là lớp vỏ mỏng gọi lại."""

from odoo import api, fields, models


class DlPurchaseOrderExportWizard(models.TransientModel):
    _name = "dl.purchase.order.export.wizard"
    _description = "Xuất / Gửi đơn mua cho nhà cung cấp"

    order_id = fields.Many2one(
        "dl.purchase.order", string="Đơn mua", required=True, readonly=True)
    partner_email = fields.Char(
        related="order_id.partner_id.email", string="Email nhà cung cấp",
        readonly=True)
    doc_label = fields.Char(
        string="Chứng từ", compute="_compute_doc_label",
        help="Chưa chốt là Yêu cầu báo giá (không giá), đã chốt là Đơn đặt hàng.")

    @api.depends("order_id.state")
    def _compute_doc_label(self):
        for wiz in self:
            wiz.doc_label = wiz.order_id._dlm_document_label()

    def action_download(self):
        """Tải PDF — gọi lại logic in sẵn trên đơn (đính kèm + chatter)."""
        self.ensure_one()
        return self.order_id.action_dlm_print()

    def action_email(self):
        """Mở trình soạn thư đã đính sẵn PDF; guard người mua nằm ở đơn."""
        self.ensure_one()
        return self.order_id.action_dlm_email()
