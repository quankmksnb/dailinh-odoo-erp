from odoo import fields, models, _
from odoo.exceptions import UserError


class DlQuotationRevisionWizard(models.TransientModel):
    """Dialog "Khách yêu cầu điều chỉnh" — chọn LOẠI điều chỉnh + ghi nội dung.
    Loại chọn ở đây quyết định dải hướng dẫn hiện sau đó trên form Báo giá:
      - Giá/chiết khấu, Giao hàng/điều khoản → Sales tự "Sửa & gửi lại".
      - Vật liệu/kỹ thuật → chuyển Kỹ thuật sửa BOM rồi báo giá lại."""

    _name = "dl.quotation.revision.wizard"
    _description = "Khách yêu cầu điều chỉnh báo giá"

    quotation_id = fields.Many2one(
        "dl.quotation",
        string="Báo giá",
        required=True,
        readonly=True,
    )
    adjust_type = fields.Selection(
        selection=lambda self: self.env["dl.quotation"]._fields[
            "revision_request_type"].selection,
        string="Loại điều chỉnh",
        required=True,
        default="commercial",
    )
    note = fields.Text(
        string="Khách muốn điều chỉnh gì?",
        required=True,
        help="Ghi rõ nội dung khách yêu cầu để xử lý và truy vết.")

    def action_confirm(self):
        """Nút Xác nhận — chuyển yêu cầu sang model chính rồi đóng dialog."""
        self.ensure_one()
        if not (self.note or "").strip():
            raise UserError(_("Vui lòng ghi rõ khách muốn điều chỉnh gì."))
        self.quotation_id._apply_revision_request(self.adjust_type, self.note)
        return {"type": "ir.actions.act_window_close"}
