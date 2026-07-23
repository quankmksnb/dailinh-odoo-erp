from markupsafe import escape

from odoo import api, fields, models, _
from odoo.tools import html2plaintext


class DlRfqHistoryWizard(models.TransientModel):
    """Modal "Lịch sử RFQ" — mở từ nút "Lịch sử" trên list RFQ (cả màn Quản lý
    RFQ của Sales lẫn RFQ cần xử lý của Kỹ thuật): timeline CHỈ ĐỌC từ lúc RFQ
    được tạo: đổi trạng thái, đổi field theo dõi, ghi chú/trao đổi. Nguồn dữ
    liệu: chatter sẵn có (mail.message + mail.tracking.value) — không thêm
    model log nào mới."""

    _name = "dl.rfq.history.wizard"
    _description = "Lịch sử RFQ"

    request_id = fields.Many2one(
        "dl.quotation.request", string="RFQ", required=True, readonly=True)
    history_html = fields.Html(
        string="Lịch sử", compute="_compute_history_html", sanitize=False)

    # ── helpers ──────────────────────────────────────────────────────────

    def _tv_display(self, tv, prefix):
        """Giá trị hiển thị của 1 mail.tracking.value theo kiểu field gốc
        (selection/m2o đã được mail lưu sẵn label vào *_value_char)."""
        ttype = tv.field_id.ttype
        if ttype in ("integer", "boolean"):
            return str(tv[f"{prefix}_value_integer"] or 0)
        if ttype in ("float", "monetary"):
            return str(tv[f"{prefix}_value_float"] or 0.0)
        if ttype in ("date", "datetime"):
            val = tv[f"{prefix}_value_datetime"]
            if not val:
                return ""
            local = fields.Datetime.context_timestamp(self, val)
            fmt = "%d/%m/%Y" if ttype == "date" else "%d/%m/%Y %H:%M"
            return local.strftime(fmt)
        if ttype == "text":
            return tv[f"{prefix}_value_text"] or ""
        return tv[f"{prefix}_value_char"] or ""

    def _fmt_when(self, dt):
        if not dt:
            return ""
        return fields.Datetime.context_timestamp(self, dt).strftime("%d/%m/%Y %H:%M")

    @api.depends("request_id")
    def _compute_history_html(self):
        Message = self.env["mail.message"]
        for rec in self:
            req = rec.request_id
            if not req:
                rec.history_html = ""
                continue

            entries = []  # [(when, who, [dòng nội dung html-safe])]

            # Mốc đầu tiên: RFQ được tạo.
            who = (req.created_by or req.create_uid).name or ""
            entries.append((
                req.create_date, who,
                ["<b>%s</b>" % escape(_("RFQ được tạo — trạng thái: Mới"))],
            ))

            # Chatter: tracking (đổi trạng thái/field) + ghi chú/trao đổi.
            msgs = Message.search(
                [("model", "=", "dl.quotation.request"), ("res_id", "=", req.id)],
                order="date asc, id asc")
            for msg in msgs:
                lines = []
                # sudo: mail.tracking.value giới hạn quyền đọc theo field —
                # user xem được RFQ thì cho xem lịch sử của chính nó.
                for tv in msg.sudo().tracking_value_ids:
                    desc = tv.field_id.field_description or tv.field_id.name
                    old = rec._tv_display(tv, "old") or _("(trống)")
                    new = rec._tv_display(tv, "new") or _("(trống)")
                    lines.append(
                        "%s: <span class='text-muted'>%s</span> → <b>%s</b>"
                        % (escape(desc), escape(old), escape(new)))
                body = html2plaintext(msg.body or "").strip()
                if body:
                    lines.append(escape(body))
                if lines:
                    entries.append((
                        msg.date, (msg.author_id.name or ""), lines))

            # Render timeline (mới nhất ở DƯỚI — đọc từ trên xuống theo thời gian).
            parts = ["<div class='dl-rfq-history'>"]
            for when, author, lines in entries:
                parts.append(
                    "<div style='border-left:3px solid #d0d5dd;"
                    "padding:2px 0 10px 12px;margin-left:4px;'>"
                    "<div class='text-muted' style='font-size:12px;'>%s%s</div>%s"
                    "</div>"
                    % (
                        escape(rec._fmt_when(when)),
                        " — <b>%s</b>" % escape(author) if author else "",
                        "".join("<div>%s</div>" % l for l in lines),
                    ))
            parts.append("</div>")
            rec.history_html = "".join(parts)
