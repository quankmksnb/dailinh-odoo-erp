from odoo import api, fields, models, _
from odoo.exceptions import UserError
from markupsafe import Markup


class DlRfqReturnWizard(models.TransientModel):
    """KTV trả RFQ về cho Sales bổ sung — chọn dòng cần bổ sung + lý do.

    Wizard tự nạp các dòng gia công; dòng đã đánh dấu "Chờ bổ sung" (qua
    resolve wizard) được tick sẵn kèm ghi chú. KTV có thể tick thêm dòng,
    sửa ghi chú, hoặc chỉ nhập ghi chú chung."""

    _name = "dl.rfq.return.wizard"
    _description = "Trả lại RFQ để bổ sung"

    request_id = fields.Many2one(
        "dl.quotation.request",
        string="Yêu cầu báo giá",
        required=True,
        readonly=True,
    )
    reason = fields.Text(string="Ghi chú chung")
    line_ids = fields.One2many(
        "dl.rfq.return.wizard.line", "wizard_id",
        string="Dòng sản phẩm")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = res.get("request_id") or self._context.get("default_request_id")
        if "line_ids" in fields_list and request_id:
            request = self.env["dl.quotation.request"].browse(request_id)
            lines_vals = []
            for line in request.line_ids.filtered(
                    lambda l: l.product_type == "manufactured"):
                lines_vals.append((0, 0, {
                    "rfq_line_id": line.id,
                    "selected": bool(line.supplement_note),
                    "note": line.supplement_note or "",
                }))
            res["line_ids"] = lines_vals
        return res

    def action_confirm(self):
        self.ensure_one()
        selected = self.line_ids.filtered("selected")
        if not selected and not (self.reason or "").strip():
            raise UserError(_(
                "Vui lòng chọn ít nhất 1 dòng cần bổ sung hoặc nhập ghi chú chung."))

        for wiz_line in selected:
            wiz_line.rfq_line_id.supplement_note = wiz_line.note or ""
        for wiz_line in self.line_ids.filtered(lambda l: not l.selected):
            wiz_line.rfq_line_id.supplement_note = False

        body = Markup("")
        if (self.reason or "").strip():
            body += Markup("<p><b>Ghi chú chung:</b> %s</p>") % self.reason.strip()
        if selected:
            body += Markup("<p><b>Dòng cần bổ sung:</b></p><ul>")
            for wiz_line in selected:
                note = wiz_line.note or _("(không có ghi chú)")
                body += Markup("<li><b>%s</b>: %s</li>") % (
                    wiz_line.product_name, note)
            body += Markup("</ul>")

        parts = []
        if (self.reason or "").strip():
            parts.append(self.reason.strip())
        for wiz_line in selected:
            parts.append("• %s: %s" % (
                wiz_line.product_name,
                wiz_line.note or _("(không có ghi chú)")))
        compiled = "\n".join(parts)

        request = self.request_id
        request.write({
            "status": "returned",
            "return_reason": compiled,
        })
        request.message_post(
            body=Markup("<p>Kỹ thuật trả lại RFQ để bổ sung:</p>") + body)
        if request.created_by:
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Bổ sung thông tin RFQ %s") % request.name,
                note=compiled,
                user_id=request.created_by.id,
            )
        return {"type": "ir.actions.act_window_close"}


class DlRfqReturnWizardLine(models.TransientModel):
    _name = "dl.rfq.return.wizard.line"
    _description = "Dòng trả lại RFQ"

    wizard_id = fields.Many2one(
        "dl.rfq.return.wizard", required=True, ondelete="cascade")
    rfq_line_id = fields.Many2one(
        "dl.quotation.request.line", string="Dòng RFQ",
        required=True, readonly=True)
    product_name = fields.Char(
        related="rfq_line_id.product_name", string="Sản phẩm", readonly=True)
    technical_status = fields.Selection(
        related="rfq_line_id.technical_status", string="Trạng thái", readonly=True)
    selected = fields.Boolean(string="Cần bổ sung", default=False)
    note = fields.Text(string="Nội dung cần bổ sung")
