# -*- coding: utf-8 -*-
"""Dialog "Xuất / Gửi báo giá": chọn Word hay PDF rồi Tải về hoặc Gửi email.

File do model chính dựng (python-docx / reportlab). Gửi email KHÔNG tự bắn ra
ngoài — chỉ mở sẵn trình soạn thư đã đính file để người dùng đọc lại rồi tự
bấm Gửi."""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlQuotationExportWizard(models.TransientModel):
    _name = "dl.quotation.export.wizard"
    _description = "Xuất / Gửi báo giá (Word/PDF)"

    quotation_id = fields.Many2one(
        "dl.quotation", string="Báo giá", required=True, readonly=True)
    doc_format = fields.Selection(
        [("pdf", "PDF"), ("docx", "Word (.docx)")],
        string="Định dạng", default="pdf", required=True)
    partner_email = fields.Char(
        related="quotation_id.partner_id.email", string="Email khách",
        readonly=True)

    def action_download(self):
        """Tải file báo giá theo định dạng đã chọn."""
        self.ensure_one()
        attachment = self.quotation_id._create_quotation_attachment(self.doc_format)
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_email(self):
        """Mở trình soạn thư đã đính sẵn file báo giá + tiêu đề/nội dung từ mẫu
        thư. Người dùng đọc lại rồi mới bấm Gửi."""
        self.ensure_one()
        quotation = self.quotation_id
        if not quotation.partner_id.email:
            raise UserError(_(
                "Khách hàng chưa có email — cập nhật email trên hồ sơ khách, "
                "hoặc dùng nút Tải về rồi gửi thủ công."))

        attachment = quotation._create_quotation_attachment(self.doc_format)

        # Lấy tiêu đề/nội dung thư từ mẫu; file đính kèm là bản vừa dựng ở trên.
        template = self.env.ref(
            "dl_sale.mail_template_dl_quotation", raise_if_not_found=False)
        subject = body = ""
        if template:
            rendered = template._generate_template(
                quotation.ids, {"subject", "body_html"})[quotation.id]
            subject = rendered.get("subject") or ""
            body = rendered.get("body_html") or ""

        ctx = {
            "default_model": "dl.quotation",
            "default_res_ids": quotation.ids,
            "default_composition_mode": "comment",
            "default_subject": subject,
            "default_body": body,
            "default_partner_ids": [(6, 0, quotation.partner_id.ids)],
            "default_attachment_ids": [(6, 0, attachment.ids)],
            "force_email": True,
        }
        return {
            "type": "ir.actions.act_window",
            "name": _("Gửi báo giá qua email"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": ctx,
        }
