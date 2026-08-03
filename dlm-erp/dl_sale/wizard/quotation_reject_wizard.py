from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlQuotationRejectWizard(models.TransientModel):
    """Sales ghi nhận khách từ chối báo giá — BẮT BUỘC chọn lý do (đặc tả
    "Trường hợp 4"). Lý do "Khác" phải kèm mô tả để truy vết nguyên nhân mất
    đơn. Việc chuyển trạng thái + hủy yêu cầu phê duyệt treo do model chính lo
    (dl.quotation._apply_reject)."""

    _name = "dl.quotation.reject.wizard"
    _description = "Từ chối báo giá — nhập lý do"

    quotation_id = fields.Many2one(
        "dl.quotation",
        string="Báo giá",
        required=True,
        readonly=True,
    )
    reason = fields.Selection(
        selection=lambda self: self.env["dl.quotation"]._fields[
            "reject_reason"].selection,
        string="Lý do từ chối",
        required=True,
    )
    note = fields.Text(
        string="Chi tiết",
        help="Nêu rõ nguyên nhân (bắt buộc khi chọn 'Lý do khác').")

    def action_confirm(self):
        self.ensure_one()
        if self.reason == "other" and not (self.note or "").strip():
            raise UserError(_(
                "Vui lòng nhập chi tiết khi chọn 'Lý do khác'."))
        self.quotation_id._apply_reject(self.reason, self.note)
        return {"type": "ir.actions.act_window_close"}
