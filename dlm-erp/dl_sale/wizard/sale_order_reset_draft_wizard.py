from odoo import fields, models, _
from odoo.exceptions import ValidationError


class DlSaleOrderResetDraftWizard(models.TransientModel):
    _name = 'dl.sale.order.reset.draft.wizard'
    _description = 'Lý do đưa đơn bán hàng về nháp'

    order_id = fields.Many2one(
        'dl.sale.order', string='Đơn bán hàng', required=True, readonly=True)
    reason = fields.Text(
        string='Lý do đưa về nháp', required=True,
        help='Nêu rõ nội dung cần sửa và nguyên nhân xác nhận nhầm.')

    def action_confirm(self):
        self.ensure_one()
        if not (self.reason or '').strip():
            raise ValidationError(_('Vui lòng nhập lý do đưa đơn về nháp.'))
        self.order_id._reset_to_draft_with_reason(self.reason)
        return {'type': 'ir.actions.act_window_close'}
