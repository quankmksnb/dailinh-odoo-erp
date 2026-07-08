from odoo import api, fields, models, _


class DlDrawing(models.Model):
    _name = 'dl.drawing'
    _description = 'Bản vẽ kỹ thuật'
    _order = 'drawing_code'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _sql_constraints = [
        ('drawing_code_uniq', 'unique(drawing_code)',
         'Mã bản vẽ đã tồn tại.'),
        ('product_version_uniq', 'unique(product_id, version)',
         'Phiên bản bản vẽ cho sản phẩm này đã tồn tại.'),
    ]

    name = fields.Char(string='Tên bản vẽ', required=True, tracking=True)
    drawing_code = fields.Char(
        string='Mã bản vẽ', required=True, tracking=True, copy=False,
        default=lambda self: _('New'),
    )
    product_id = fields.Many2one(
        'product.product', string='Sản phẩm', required=True, tracking=True,
        domain=[('product_kind', '=', 'finished')],
    )
    version = fields.Integer(string='Phiên bản', default=1, required=True)
    status = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('archived', 'Lưu trữ'),
    ], string='Trạng thái', default='draft', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', string='File đính kèm',
        help='Bản vẽ PDF, hình ảnh, file CAD',
    )
    confirmed_date = fields.Date(string='Ngày xác nhận', readonly=True)
    confirmed_by = fields.Many2one('res.users', string='Người xác nhận', readonly=True)
    note = fields.Text(string='Ghi chú')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('drawing_code', _('New')) == _('New'):
                vals['drawing_code'] = self.env['ir.sequence'].next_by_code(
                    'dl.drawing') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.write({
            'status': 'confirmed',
            'confirmed_date': fields.Date.today(),
            'confirmed_by': self.env.uid,
        })

    def action_archive(self):
        self.write({'status': 'archived'})

    def action_reset_draft(self):
        self.write({
            'status': 'draft',
            'confirmed_date': False,
            'confirmed_by': False,
        })
