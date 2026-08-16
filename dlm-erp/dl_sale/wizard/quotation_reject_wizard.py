from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlQuotationRejectWizard(models.TransientModel):
    """Dialog "Từ chối báo giá" — BẮT BUỘC chọn lý do; lý do "Khác" phải ghi
    thêm mô tả để còn biết vì sao mất đơn. Việc đổi trạng thái + huỷ yêu cầu
    duyệt treo do dl.quotation._apply_reject lo."""

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
        """Nút Xác nhận — chuyển lý do sang model chính rồi đóng dialog."""
        self.ensure_one()
        if self.reason == "other" and not (self.note or "").strip():
            raise UserError(_(
                "Vui lòng nhập chi tiết khi chọn 'Lý do khác'."))
        self.quotation_id._apply_reject(self.reason, self.note)
        return {"type": "ir.actions.act_window_close"}
