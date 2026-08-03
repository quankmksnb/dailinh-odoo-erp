from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlRfqReturnWizard(models.TransientModel):
    """KTV trả RFQ về cho Sales bổ sung — nhập lý do (bắt buộc). Đặt RFQ về
    trạng thái 'Trả lại bổ sung', ghi lý do + chatter và tạo activity nhắc Sales."""

    _name = "dl.rfq.return.wizard"
    _description = "Trả lại RFQ để bổ sung"

    request_id = fields.Many2one(
        "dl.quotation.request",
        string="Yêu cầu báo giá",
        required=True,
        readonly=True,
    )
    reason = fields.Text(string="Lý do / Cần bổ sung", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not (self.reason or "").strip():
            raise UserError(_("Vui lòng nhập lý do trả lại."))
        request = self.request_id
        request.write({
            "status": "returned",
            "return_reason": self.reason,
        })
        # Ghi chatter + nhắc người tạo RFQ (Sales) bổ sung.
        request.message_post(
            body=_("Kỹ thuật trả lại RFQ để bổ sung:<br/>%s") % self.reason)
        if request.created_by:
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Bổ sung thông tin RFQ %s") % request.name,
                note=self.reason,
                user_id=request.created_by.id,
            )
        return {"type": "ir.actions.act_window_close"}
