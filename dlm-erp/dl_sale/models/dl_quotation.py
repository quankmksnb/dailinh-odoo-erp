from odoo import models, fields, api


class DlQuotation(models.Model):
    _name = 'dl.quotation'
    _description = 'Báo giá'
    _order = 'date_order desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Số báo giá', required=True, copy=False,
                       readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Khách hàng', required=True,
                                 domain=[('partner_role', '=', 'customer')],
                                 tracking=True)
    date_order = fields.Date(string='Ngày báo giá', required=True,
                             default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('sent', 'Đã gửi'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái', default='draft', tracking=True)
    note = fields.Text(string='Ghi chú')
    line_ids = fields.One2many('dl.quotation.line', 'quotation_id', string='Chi tiết')
    amount_total = fields.Float(string='Tổng tiền', compute='_compute_amount', store=True)
    currency_id = fields.Many2one('res.currency', string='Tiền tệ',
                                  default=lambda self: self.env.company.currency_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dl.quotation') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.price_subtotal')
    def _compute_amount(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('price_subtotal'))

    def action_send(self):
        self.state = 'sent'

    def action_approve(self):
        self.state = 'approved'

    def action_reject(self):
        self.state = 'rejected'

    def action_reset_draft(self):
        self.state = 'draft'


class DlQuotationLine(models.Model):
    _name = 'dl.quotation.line'
    _description = 'Chi tiết báo giá'

    quotation_id = fields.Many2one('dl.quotation', string='Báo giá', ondelete='cascade')
    name = fields.Char(string='Mô tả', required=True)
    qty = fields.Float(string='SL', default=1.0)
    price_unit = fields.Float(string='Đơn giá')
    price_subtotal = fields.Float(string='Thành tiền', compute='_compute_subtotal', store=True)

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
