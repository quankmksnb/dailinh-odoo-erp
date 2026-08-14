# -*- coding: utf-8 -*-
"""K21 — Tờ giấy gửi nhà cung cấp.

Vì sao phải có file: **NCC không đăng nhập ERP của Đại Linh.** Đơn mua nằm ngay
ngắn trong hệ thống bao nhiêu thì lúc gọi cho Thắng Hảo vẫn là con số không.

MỘT mẫu, hai biến thể theo trạng thái:

  nháp / đã gửi  →  **YÊU CẦU BÁO GIÁ**, cột đơn giá ĐỂ TRỐNG cho NCC điền
  đã chốt        →  **ĐƠN ĐẶT HÀNG**, có giá đã chốt

🔴 **Tờ này CÓ giá — cố ý ngược với biên bản hàng không đạt của K17** (tờ đó cố ý
KHÔNG có giá). Không mâu thuẫn: đây là giá ta trả cho NCC, do chính họ báo; còn
kia là biên bản về hàng lỗi, in tiền lên đó là tự chốt mức giảm trừ hộ NCC.
Ghi ở cả hai chỗ để người sau không "sửa cho nhất quán".

🔴 **KHÔNG in tên khách hàng cuối.** NCC không có lý do gì phải biết Đại Linh
đang làm cho ai — đó là đường ngắn nhất để họ bán thẳng cho khách của mình.

Thuần Python bằng reportlab, dùng LẠI font tiếng Việt đã đăng ký ở ``dl_sale``
— KHÔNG wkhtmltopdf (quy ước dự án, xem ``dl_inventory/models/
vendor_return_document.py``).
"""

import base64
import io

from odoo import _, models
from odoo.exceptions import UserError

from odoo.addons.dl_sale.models.quotation_document import (
    _PDF_FONT, _PDF_FONT_BOLD)


class DlPurchaseOrderDocument(models.Model):
    _inherit = "dl.purchase.order"

    def action_dlm_print(self):
        """Xuất PDF gửi NCC và lưu thành đính kèm + ghi chatter.

        Lưu lại chứ không chỉ tải về: ba tháng sau còn trả lời được "hôm đó gửi
        NCC đúng cái gì" — cùng lý do biên bản hàng loại của K17 được lưu.
        """
        self.ensure_one()
        self._dlm_check_buyer()
        if not self.line_ids:
            raise UserError(_("Đơn %s chưa có dòng nào để in.") % self.name)
        is_order = self.state == "confirmed"
        pdf = self._dlm_build_pdf(is_order=is_order)
        filename = "%s_%s.pdf" % (
            "DonDatHang" if is_order else "YeuCauBaoGia",
            self.name.replace("/", "_"))
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(pdf),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/pdf",
        })
        self.message_post(
            body=_("Đã xuất %s gửi nhà cung cấp.") % (
                _("Đơn đặt hàng") if is_order else _("Yêu cầu báo giá")),
            attachment_ids=[attachment.id])
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    def _dlm_build_pdf(self, is_order):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

        self.ensure_one()
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

        header = [_("STT"), _("Mặt hàng"), _("ĐVT"), _("Số lượng"),
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
            12 * mm, 70 * mm, 18 * mm, 22 * mm, 26 * mm, 26 * mm])
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
