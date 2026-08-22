# -*- coding: utf-8 -*-
"""Dialog "Xuất / Gửi biên bản" trên phiếu Trả hàng NCC: Tải về PDF hoặc mở trình soạn thư đã đính sẵn.

Gộp hai nút cũ [Biên bản gửi nhà cung cấp] + [Gửi biên bản qua email] về một cửa
(cùng khuôn dialog "Xuất / Gửi báo giá" của dl_sale). Logic dựng PDF và soạn thư
vẫn nằm ở stock.picking — wizard chỉ là lớp vỏ mỏng gọi lại, không chép logic."""

from odoo import fields, models


class DlVendorReturnExportWizard(models.TransientModel):
    _name = "dl.vendor.return.export.wizard"
    _description = "Xuất / Gửi biên bản hàng không đạt"

    picking_id = fields.Many2one(
        "stock.picking", string="Phiếu trả", required=True, readonly=True)
    partner_email = fields.Char(
        related="picking_id.partner_id.email", string="Email nhà cung cấp",
        readonly=True)

    def action_download(self):
        """Tải biên bản PDF — gọi lại logic in sẵn trên phiếu (đính kèm + chatter)."""
        self.ensure_one()
        return self.picking_id.action_dlm_print_reject_report()

    def action_email(self):
        """Mở trình soạn thư đã đính sẵn biên bản; guard vai trò nằm ở phiếu."""
        self.ensure_one()
        return self.picking_id.action_dlm_email_reject_report()
