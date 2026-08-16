# -*- coding: utf-8 -*-
"""PDF gửi NCC: nháp/đã gửi = YÊU CẦU BÁO GIÁ (trống giá), đã chốt = ĐƠN ĐẶT HÀNG (có giá)."""

import base64
import io

from odoo import _, models
from odoo.exceptions import UserError

from odoo.addons.dl_sale.models.quotation_document import (
    _PDF_FONT, _PDF_FONT_BOLD)


class DlPurchaseOrderDocument(models.Model):
    _inherit = "dl.purchase.order"

    def action_dlm_print(self):
        """Nút [In] trên đơn mua — xuất PDF gửi NCC, lưu thành đính kèm và tải về."""
        self.ensure_one()
        attachment = self._dlm_create_document_attachment()
        self.message_post(
            body=_("Đã xuất %s gửi nhà cung cấp.") % self._dlm_document_label(),
            attachment_ids=[attachment.id])
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_dlm_email(self):
        """Nút [Gửi mail NCC] — mở trình soạn thư đã đính sẵn PDF + tiêu đề/nội dung từ mẫu."""
        self.ensure_one()
        if not self.partner_id.email:
            raise UserError(_(
                "Nhà cung cấp %s chưa có email — bổ sung email trên hồ sơ nhà "
                "cung cấp, hoặc dùng nút In rồi gửi bằng kênh của bạn."
            ) % self.partner_id.display_name)

        attachment = self._dlm_create_document_attachment()
        template = self.env.ref(
            "dl_purchase.mail_template_dl_purchase_order",
            raise_if_not_found=False)
        subject = body = ""
        if template:
            rendered = template._generate_template(
                self.ids, {"subject", "body_html"})[self.id]
            subject = rendered.get("subject") or ""
            body = rendered.get("body_html") or ""

        return {
            "type": "ir.actions.act_window",
            "name": _("Gửi %s cho nhà cung cấp") % self._dlm_document_label(),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_composition_mode": "comment",
                "default_subject": subject,
                "default_body": body,
                "default_partner_ids": [(6, 0, self.partner_id.ids)],
                "default_attachment_ids": [(6, 0, attachment.ids)],
                "force_email": True,
            },
        }

    def _dlm_document_label(self):
        """Tên tờ giấy theo trạng thái (Đơn đặt hàng / Yêu cầu báo giá) — một nguồn cho mọi chỗ."""
        self.ensure_one()
        return (_("Đơn đặt hàng") if self.state == "confirmed"
                else _("Yêu cầu báo giá"))

    def _dlm_create_document_attachment(self):
        """Dựng PDF rồi lưu thành đính kèm của đơn (để sau còn tra đã gửi NCC cái gì)."""
        self.ensure_one()
        self._dlm_check_buyer()
        if not self.line_ids:
            raise UserError(_("Đơn %s chưa có dòng nào để in.") % self.name)
        is_order = self.state == "confirmed"
        pdf = self._dlm_build_pdf(is_order=is_order)
        filename = "%s_%s.pdf" % (
            "DonDatHang" if is_order else "YeuCauBaoGia",
            self.name.replace("/", "_"))
        return self.env["ir.attachment"].sudo().create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(pdf),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/pdf",
        })

    # ------------------------------------------------------------------
    def _dlm_build_pdf(self, is_order):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

        self.ensure_one()
        # Mượn tên font của `dl_sale` thì phải mượn cả bước đăng ký nó, không thì reportlab nổ.
        self.env["dl.quotation"]._register_pdf_font()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=16 * mm, bottomMargin=16 * mm,
            title=self.name)
        tieu_de = ParagraphStyle(
            "dl_title", fontName=_PDF_FONT_BOLD, fontSize=15, leading=19,
            alignment=1, spaceAfter=4)
        thuong = ParagraphStyle(
            "dl_body", fontName=_PDF_FONT, fontSize=10, leading=14)
        nho = ParagraphStyle(
            "dl_small", fontName=_PDF_FONT, fontSize=8.5, leading=12,
            textColor=colors.HexColor("#666666"))

        story = [
            Paragraph(
                _("ĐƠN ĐẶT HÀNG") if is_order else _("YÊU CẦU BÁO GIÁ"),
                tieu_de),
            Paragraph(_("Số: %s") % self.name, thuong),
            Spacer(1, 6),
            Paragraph(_("Nhà cung cấp: <b>%s</b>")
                      % self.partner_id.display_name, thuong),
            Paragraph(_("Ngày lập: %s") % (
                self.date_order.strftime("%d/%m/%Y")
                if self.date_order else "—"), thuong),
        ]
        if self.date_expected:
            story.append(Paragraph(
                _("Ngày hàng về mong muốn: %s")
                % self.date_expected.strftime("%d/%m/%Y"), thuong))
        story.append(Spacer(1, 10))

        header = [_("Số thứ tự"), _("Mặt hàng"), _("Đơn vị tính"),
                  _("Số lượng"),
                  _("Đơn giá"), _("Thành tiền")]
        rows = [header]
        for index, line in enumerate(self.line_ids, start=1):
            rows.append([
                str(index),
                line.product_id.display_name,
                line.uom_id.name or "",
                _num(line.qty),
                _money(line.price_unit) if is_order else "",
                _money(line.price_subtotal) if is_order else "",
            ])
        if is_order:
            rows.append(["", _("TỔNG CỘNG"), "", "", "",
                         _money(self.amount_total)])

        table = Table(rows, colWidths=[
            18 * mm, 60 * mm, 24 * mm, 22 * mm, 25 * mm, 25 * mm])
        style = [
            ("FONTNAME", (0, 0), (-1, -1), _PDF_FONT),
            ("FONTNAME", (0, 0), (-1, 0), _PDF_FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if is_order:
            style.append(("FONTNAME", (0, -1), (-1, -1), _PDF_FONT_BOLD))
        table.setStyle(TableStyle(style))
        story.append(table)

        if not is_order:
            story.append(Spacer(1, 8))
            story.append(Paragraph(_(
                "Kính đề nghị Quý công ty báo giá cho các mặt hàng trên (đã "
                "gồm VAT), kèm thời gian giao hàng dự kiến."), thuong))
        if self.note:
            story.append(Spacer(1, 8))
            story.append(Paragraph(_("Ghi chú: %s") % self.note, thuong))

        story.append(Spacer(1, 16))
        story.append(Table(
            [[Paragraph(_("<b>ĐẠI DIỆN BÊN MUA</b>"), thuong),
              Paragraph(_("<b>ĐẠI DIỆN NHÀ CUNG CẤP</b>"), thuong)],
             [Paragraph(_("(ký, ghi rõ họ tên)"), nho),
              Paragraph(_("(ký, ghi rõ họ tên)"), nho)]],
            colWidths=[87 * mm, 87 * mm]))

        doc.build(story)
        return buffer.getvalue()


def _num(value):
    text = "%.3f" % (value or 0.0)
    text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") if text else "0"


def _money(value):
    return "{:,.0f}".format(value or 0.0).replace(",", ".")
