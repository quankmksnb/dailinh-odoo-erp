from odoo import fields, models, _
from odoo.exceptions import ValidationError


class DlPricingApprovalRejectWizard(models.TransientModel):
    """Người duyệt từ chối yêu cầu phê duyệt — BẮT BUỘC nhập lý do, mở dạng
    dialog khi bấm "Từ chối" thay vì để ô lý do thường trực trên form (gợi ý
    là sẽ từ chối trong khi phần lớn thao tác là Phê duyệt). Việc chuyển trạng
    thái + kiểm quyền do model chính lo (request.action_reject)."""

    _name = "dl.pricing.approval.reject.wizard"
    _description = "Từ chối yêu cầu phê duyệt — nhập lý do"

    request_id = fields.Many2one(
        "dl.pricing.approval.request", string="Yêu cầu phê duyệt",
        required=True, readonly=True, ondelete="cascade")
    reject_comment = fields.Text(string="Lý do từ chối", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not (self.reject_comment or "").strip():
            raise ValidationError(_("Bắt buộc nhập lý do khi từ chối."))
        # Ghi lý do lên yêu cầu rồi để action_reject kiểm quyền + chuyển trạng
        # thái (giữ nguyên guard _check_can_resolve / bắt buộc reject_comment).
        self.request_id.write({"reject_comment": self.reject_comment})
        return self.request_id.action_reject()
