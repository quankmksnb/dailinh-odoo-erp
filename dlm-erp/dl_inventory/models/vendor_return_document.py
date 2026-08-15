# -*- coding: utf-8 -*-
"""K17 — Biên bản hàng không đạt: đường ra khỏi hệ thống cho bằng chứng.

Thiết kế: docs/Thiet_ke_phan_he_kho.md §6.4.

Vì sao phải có file: nhà cung cấp KHÔNG đăng nhập ERP của Đại Linh. Ảnh chụp
hàng lỗi có nằm ngay ngắn trên phiếu trả bao nhiêu thì lúc ngồi với NCC vẫn là
con số không, nếu Mua hàng phải mở từng tấm, tải về, rồi ghép tay vào Zalo. Biên
bản này gom lý do + số lượng + LÔ + ảnh vào một tờ ký được.

Ba quyết định đã chốt, ghi lại để người sau không "sửa cho đầy đủ":

  KHÔNG CÓ GIÁ. Đây là biên bản về HÀNG, không phải yêu cầu bồi thường. Số tiền
  giảm trừ là kết quả của cuộc đàm phán, đưa lên tờ giấy trước khi đàm phán là
  tự chốt giá hộ NCC. Giá mua cũng là dữ liệu Đại Linh không có lý do gì phải
  in ra rồi đưa cho chính người bán.

  LÔ LẤY TỪ TỒN THẬT. `move.lot_ids` của phiếu trả còn trống lúc nháp (chưa giữ
  chỗ), mà nháp mới đúng là lúc cần in. Đọc thẳng lô của hàng đang nằm ở khu Chờ
  trả NCC — đó là chính số hàng biên bản đang nói tới.

  THUẦN PYTHON, KHÔNG wkhtmltopdf (quy ước dự án — xem dl_sale/models/
  quotation_document.py). Font và cách đăng ký dùng LẠI của dl_sale thay vì chép
  sang: đây đúng kiểu hằng số trùng bản mà repo đã trả giá vài lần.
"""

import base64
import io

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_datetime

# Dùng lại font đã đăng ký cho reportlab ở dl_sale (dl_inventory phụ thuộc
# dl_sale từ K6). Chép sang đây là đẻ ra bản thứ hai để lệch.
from odoo.addons.dl_sale.models.quotation_document import (
    _PDF_FONT, _PDF_FONT_BOLD)

from .stock_picking import _DLM_RETURN_CODE

# Bề rộng tối đa của một ảnh trong lưới 2 cột (khổ A4, lề 18mm).
_ANH_W_MM = 82.0
_ANH_H_MM = 62.0

# Ai được GỬI biên bản cho NCC — hẹp hơn ai được IN nó (xem
# action_dlm_email_reject_report). CEO/Admin có mặt để không ai bị kẹt khi Mua
# hàng nghỉ, đúng khuôn _DLM_DISPATCH_ROLES.
_DLM_SEND_ROLES = (
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)


class StockPickingRejectReport(models.Model):
    _inherit = "stock.picking"

    # ------------------------------------------------------------------
    # Ngữ cảnh dữ liệu — một nguồn sự thật cho cả bảng lẫn phần ảnh.
    # ------------------------------------------------------------------
    def _dlm_reject_report_rows(self):
        """Mỗi dòng hàng trả = một mục của biên bản.

        Trả về dict thuần (không phải recordset) để phần dựng PDF không phải
        biết gì về model — và để test kiểm được rằng KHÔNG có khoá giá nào lọt
        vào đây.
        """
        self.ensure_one()
        reasons = dict(
            self.env["stock.move"]._fields["dlm_reject_reason"].selection)
        rows = []
        for idx, move in enumerate(self.move_ids, start=1):
            rows.append({
                "stt": idx,
                "product": move.product_id.display_name or "",
                "lots": ", ".join(self._dlm_reject_report_lots(move)),
                "qty": ("%g" % (move.product_uom_qty or 0.0)),
                "uom": move.product_uom.name or "",
                "reason": reasons.get(move.dlm_reject_reason, _("Chưa ghi")),
                "note": move.dlm_reject_note or "",
                "images": move.dlm_evidence_ids.filtered(
                    lambda a: (a.mimetype or "").startswith("image/")),
                "files": move.dlm_evidence_ids.filtered(
                    lambda a: not (a.mimetype or "").startswith("image/")),
            })
        return rows

    def _dlm_reject_report_lots(self, move):
        """Số lô của hàng trên dòng — ưu tiên lô đã giữ chỗ, sau đó lô đang nằm
        ở khu Chờ trả NCC.

        Lô là mắt xích mạnh nhất của cả biên bản: "lô LO/2026/00761 của quý
        công ty có 8 cây gỉ" tra ngược được tới đúng chuyến giao, còn "8 cây
        thép gỉ" thì không.
        """
        self.ensure_one()
        if move.lot_ids:
            return move.lot_ids.mapped("name")
        quants = self.env["stock.quant"].search([
            ("location_id", "child_of", self.location_id.id),
            ("product_id", "=", move.product_id.id),
            ("quantity", ">", 0),
        ])
        return [name for name in quants.mapped("lot_id.name") if name]

    # ------------------------------------------------------------------
    # Dựng PDF
    # ------------------------------------------------------------------
    def _dlm_build_reject_report(self):
        self.ensure_one()
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                TableStyle)
        except ImportError:
            raise UserError(_(
                "Thiếu thư viện 'reportlab' để tạo biên bản PDF. Cài bằng: "
                "pip install reportlab"))

        self.env["dl.quotation"]._register_pdf_font()
        company = self.company_id or self.env.company
        partner = self.partner_id
        rows = self._dlm_reject_report_rows()

        base = ParagraphStyle(
            "dl_base", fontName=_PDF_FONT, fontSize=10, leading=14)
        small = ParagraphStyle("dl_small", parent=base, fontSize=8, leading=10)
        bold = ParagraphStyle("dl_bold", parent=base, fontName=_PDF_FONT_BOLD)
        center = ParagraphStyle("dl_center", parent=base, alignment=TA_CENTER)
        right = ParagraphStyle("dl_right", parent=base, alignment=TA_RIGHT)
        title = ParagraphStyle(
            "dl_title", parent=bold, fontSize=18, alignment=TA_CENTER,
            spaceBefore=6, spaceAfter=2)

        def th(text, align=TA_CENTER):
            return Paragraph(text, ParagraphStyle(
                "dl_th", parent=bold, alignment=align, textColor=colors.white))

        story = []

        # --- Đầu trang: công ty lập biên bản ---
        story.append(Paragraph(company.name or "", ParagraphStyle(
            "dl_co", parent=bold, fontSize=14)))
        addr = ", ".join(filter(None, [company.street, company.city]))
        for text in filter(None, [
            ("Địa chỉ: " + addr) if addr else "",
            ("Mã số thuế: " + company.vat) if company.vat else "",
            " | ".join(filter(None, [
                ("ĐT: " + company.phone) if company.phone else "",
                ("Email: " + company.email) if company.email else ""])),
        ]):
            story.append(Paragraph(text, base))

        story.append(Paragraph("BIÊN BẢN HÀNG KHÔNG ĐẠT", title))
        story.append(Paragraph("Số: %s" % (self.name or ""), center))
        story.append(Spacer(1, 6 * mm))

        # --- Hai bên + chứng từ gốc ---
        ben = [Paragraph("<b>Kính gửi:</b> %s" % (partner.name or ""), base)]
        for text in filter(None, [
            ("Mã số thuế: " + partner.vat) if partner.vat else "",
            ("Địa chỉ: " + ", ".join(filter(None, [
                partner.street, partner.city]))) if partner.street else "",
            ("Điện thoại: " + partner.phone) if partner.phone else "",
        ]):
            ben.append(Paragraph(text, base))
        meta = [Paragraph("Ngày lập: %s" % format_datetime(
            self.env, self.scheduled_date), right)] if self.scheduled_date else []
        if self.dlm_origin_picking_id:
            meta.append(Paragraph("Phiếu nhận gốc: %s" % (
                self.dlm_origin_picking_id.name or ""), right))
        # `meta or ""`: ô rỗng phải là chuỗi, danh sách rỗng làm reportlab nổ.
        head = Table([[ben, meta or ""]], colWidths=[110 * mm, 64 * mm])
        head.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            "Qua kiểm tra chất lượng lô hàng quý công ty đã giao, chúng tôi ghi "
            "nhận các mặt hàng sau <b>không đạt yêu cầu</b>:", base))
        story.append(Spacer(1, 2 * mm))

        # --- Bảng hàng không đạt (KHÔNG có cột giá — xem docstring) ---
        data = [[th("Số thứ tự"), th("Mặt hàng", TA_CENTER), th("Số lô"),
                 th("Số lượng"), th("Đơn vị tính"), th("Lý do"), th("Ghi chú", TA_CENTER)]]
        for row in rows:
            data.append([
                Paragraph(str(row["stt"]), center),
                Paragraph(row["product"], base),
                Paragraph(row["lots"], small),
                Paragraph(row["qty"], center),
                Paragraph(row["uom"], center),
                Paragraph(row["reason"], base),
                Paragraph(row["note"], small),
            ])
        # Tổng PHẢI = 174mm (A4 210 trừ hai lề 18mm) — vượt là bảng tràn lề.
        # Bốn cột giữa rộng hơn bản đầu vì nhãn viết đầy đủ ("Số thứ tự",
        # "Đơn vị tính") dài hơn hẳn chữ viết tắt cũ; phần bù lấy từ Mặt hàng /
        # Lý do / Ghi chú vốn đã tự xuống dòng.
        table = Table(data, repeatRows=1, colWidths=[
            14 * mm, 40 * mm, 24 * mm, 17 * mm, 20 * mm, 29 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b0b0b0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            # Đệm mặc định của reportlab là 6pt mỗi bên — với cột hẹp nhất
            # ("Số thứ tự", 14mm) thì 12pt đệm còn rộng hơn cả chữ, nên nhãn bị
            # bẻ giữa từ.
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

        # --- Ảnh bằng chứng, gom theo từng mặt hàng ---
        story += self._dlm_reject_report_evidence(rows, base, bold, small)

        # --- Chữ ký ---
        # KeepTogether: không có nó thì hai ô ký trôi sang một trang trắng của
        # riêng chúng — tờ biên bản mà trang cuối chỉ có chỗ ký thì nhìn như in
        # lỗi, và người ta ngại đưa cho đối tác.
        ket = [Spacer(1, 10 * mm), Paragraph(
            "Biên bản được lập thành 02 bản, mỗi bên giữ 01 bản có giá trị "
            "như nhau.", base), Spacer(1, 6 * mm)]
        sign = Table([[
            [Paragraph("ĐẠI DIỆN NHÀ CUNG CẤP", ParagraphStyle(
                "s1", parent=bold, alignment=TA_CENTER)),
             Paragraph("<i>(Ký, ghi rõ họ tên)</i>", center)],
            [Paragraph("ĐẠI DIỆN %s" % (company.name or "").upper(),
                       ParagraphStyle("s2", parent=bold, alignment=TA_CENTER)),
             Paragraph("<i>(Ký, ghi rõ họ tên)</i>", center)],
        ]], colWidths=[87 * mm, 87 * mm])
        sign.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        ket.append(sign)
        story.append(KeepTogether(ket))

        buf = io.BytesIO()
        SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=15 * mm, bottomMargin=15 * mm,
            title="Bien ban hang khong dat %s" % (self.name or ""),
        ).build(story)
        return buf.getvalue()

    def _dlm_reject_report_evidence(self, rows, base, bold, small):
        """Phần ảnh — thứ khiến tờ giấy này khác một cái email kể lể.

        Lưới 2 cột theo từng mặt hàng, `KeepTogether` để tiêu đề mặt hàng không
        bị tách khỏi ảnh của nó khi sang trang. Ảnh hỏng thì BỎ QUA tấm đó chứ
        không cho nổ cả biên bản: mất một tấm còn in được, mất cả tờ thì Mua
        hàng ra gặp NCC tay không.
        """
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import (
            Image, KeepTogether, Paragraph, Spacer, Table, TableStyle)

        story = []
        co_anh = any(row["images"] for row in rows)
        if not co_anh:
            return story

        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("<b>ẢNH BẰNG CHỨNG</b>", base))
        story.append(Paragraph(
            "Ảnh do thủ kho chụp tại thời điểm mở hàng, trước khi hàng rời khu "
            "chờ kiểm.", small))

        for row in rows:
            if not row["images"]:
                continue
            khoi = [Spacer(1, 3 * mm),
                    Paragraph("%s — %s %s" % (
                        row["product"], row["qty"], row["uom"]), bold)]
            o = []
            for att in row["images"]:
                anh = self._dlm_reject_report_image(
                    att, ImageReader, Image, mm)
                if anh is not None:
                    o.append([anh, Paragraph(att.name or "", small)])
            if not o:
                continue
            # Xếp 2 ảnh/hàng; ô lẻ cuối cùng để trống cho lưới không vỡ.
            luoi = [o[i:i + 2] for i in range(0, len(o), 2)]
            if len(luoi[-1]) == 1:
                luoi[-1].append("")
            tbl = Table(luoi, colWidths=[87 * mm, 87 * mm])
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            khoi.append(tbl)
            story.append(KeepTogether(khoi))

        # File không phải ảnh (PDF chứng thư, video…) chỉ nêu TÊN: nhúng được
        # thì cũng không xem được trên giấy, nhưng phải nói ra là có tồn tại.
        khac = [name for row in rows for name in row["files"].mapped("name")]
        if khac:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(
                "<b>Tài liệu đính kèm khác:</b> %s" % ", ".join(khac), small))
        return story

    def _dlm_reject_report_image(self, attachment, ImageReader, Image, mm):
        """Một tấm ảnh đã co về khung, giữ đúng tỉ lệ. None nếu đọc không được."""
        try:
            raw = base64.b64decode(attachment.datas or b"")
            if not raw:
                return None
            reader = ImageReader(io.BytesIO(raw))
            w, h = reader.getSize()
            if not w or not h:
                return None
            ty_le = min(_ANH_W_MM * mm / w, _ANH_H_MM * mm / h)
            return Image(io.BytesIO(raw), width=w * ty_le, height=h * ty_le)
        except Exception:  # noqa: BLE001 — một tấm ảnh hỏng không được giết cả biên bản
            return None

    # ------------------------------------------------------------------
    # Nút trên form: dựng file, lưu dấu vết, tải về
    # ------------------------------------------------------------------
    def action_dlm_print_reject_report(self):
        """Tạo biên bản, đính vào phiếu + chatter, rồi tải về.

        Lưu lại chứ không dựng-rồi-quên: bản đưa cho NCC là chứng từ đối ngoại,
        ba tháng sau phải trả lời được "hôm đó mình đưa họ đúng cái gì".
        """
        self.ensure_one()
        attachment = self._dlm_create_reject_report_attachment()
        # sudo: message_post nổ UserError khi người dùng chưa khai email — cùng
        # lý do đã ghi ở _dlm_create_vendor_return. Dấu vết không được phép làm
        # hỏng việc in.
        self.sudo().message_post(
            body=_("Đã lập biên bản hàng không đạt để gửi nhà cung cấp."),
            attachment_ids=[attachment.id])
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_dlm_email_reject_report(self):
        """Mở trình soạn thư đã đính sẵn biên bản, gửi thẳng nhà cung cấp.

        🔴 Nút IN cố ý KHÔNG khoá theo vai trò (thủ kho cần in kẹp vào hàng lúc
        xe NCC tới lấy), nhưng nút GỬI thì có: thư này mở đầu một cuộc đàm phán
        giảm trừ, và quan hệ với NCC là của Mua hàng. Thủ kho nhận hàng theo đơn
        nhưng không nói chuyện với NCC — cùng lằn kiểm soát chéo mà
        ``dl.purchase.order._dlm_check_buyer`` đang giữ.

        Lá chắn nằm ở ĐÂY chứ không chỉ ở ``groups=`` của view: view chỉ giấu
        nút, còn RPC/import/test vẫn gọi thẳng được.

        Dùng trình soạn thư (không gửi thẳng): người nhận là NCC, và Mua hàng có
        quyền GHI ``stock.picking`` (ACL 1,1,1,0) nên composer không bị chặn.
        Cùng khuôn ``dl.purchase.order.action_dlm_email``.
        """
        self.ensure_one()
        if not self.env.su and not any(
                self.env.user.has_group(role) for role in _DLM_SEND_ROLES):
            raise UserError(_(
                "Gửi biên bản cho nhà cung cấp là việc của Mua hàng — thư này "
                "mở đầu cuộc đàm phán giảm trừ. Bạn vẫn in được bản giấy bằng "
                "nút [Biên bản gửi nhà cung cấp]."))
        if not self.partner_id:
            raise UserError(_(
                "Phiếu %s chưa gắn nhà cung cấp nên không biết gửi cho ai.")
                % self.name)
        if not self.partner_id.email:
            raise UserError(_(
                "Nhà cung cấp %s chưa có email — bổ sung email trên hồ sơ nhà "
                "cung cấp, hoặc in bản giấy rồi gửi bằng kênh của bạn."
            ) % self.partner_id.display_name)

        attachment = self._dlm_create_reject_report_attachment()
        template = self.env.ref(
            "dl_inventory.mail_template_dl_reject_report",
            raise_if_not_found=False)
        subject = body = ""
        if template:
            rendered = template._generate_template(
                self.ids, {"subject", "body_html"})[self.id]
            subject = rendered.get("subject") or ""
            body = rendered.get("body_html") or ""

        return {
            "type": "ir.actions.act_window",
            "name": _("Gửi biên bản cho nhà cung cấp"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_model": "stock.picking",
                "default_res_ids": self.ids,
                "default_composition_mode": "comment",
                "default_subject": subject,
                "default_body": body,
                "default_partner_ids": [(6, 0, self.partner_id.ids)],
                "default_attachment_ids": [(6, 0, attachment.ids)],
                "force_email": True,
            },
        }

    def _dlm_create_reject_report_attachment(self):
        """Dựng biên bản rồi đính vào phiếu.

        Lưu lại chứ không dựng-rồi-quên: bản đưa cho NCC là chứng từ đối ngoại,
        ba tháng sau phải trả lời được "hôm đó mình đưa họ đúng cái gì".
        """
        self.ensure_one()
        if self.picking_type_id.sequence_code != _DLM_RETURN_CODE:
            raise UserError(_(
                "Biên bản hàng không đạt chỉ lập từ phiếu Trả hàng nhà cung cấp."))
        if not self.move_ids:
            raise UserError(_("Phiếu chưa có dòng hàng nào để lập biên bản."))

        content = self._dlm_build_reject_report()
        return self.env["ir.attachment"].create({
            "name": "Bien_ban_hang_khong_dat_%s.pdf" % (
                self.name or "moi").replace("/", "_"),
            "datas": base64.b64encode(content),
            "res_model": "stock.picking",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })
