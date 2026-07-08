from odoo import api, fields, models, _


class DlSemiProduct(models.Model):
    """Bán thành phẩm — model độc lập của S08 (không có màn quản lý riêng ở
    module khác, không cần dựa vào product.product)."""
    _name = 'dl.semi.product'
    _description = 'Bán thành phẩm'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'semi_code'
    _sql_constraints = [
        ('semi_code_uniq', 'unique(semi_code)',
         'Mã bán thành phẩm đã tồn tại.'),
    ]

    name = fields.Char(string='Tên bán thành phẩm', required=True, tracking=True)
    semi_code = fields.Char(
        string='Mã bán thành phẩm', required=True, tracking=True, copy=False,
        default=lambda self: _('New'),
    )
    category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm', tracking=True,
    )
    uom_id = fields.Many2one('uom.uom', string='Đơn vị tính', required=True)
    dimension_spec = fields.Char(string='Kích thước (DxRxC, mm)')
    material_spec = fields.Char(string='Vật liệu chính')
    technical_note = fields.Text(string='Ghi chú kỹ thuật')
    active = fields.Boolean(default=True)

    bom_ids = fields.One2many('dl.bom', 'semi_product_id', string='BOM liên quan')
    bom_count = fields.Integer(compute='_compute_bom_count', string='Số BOM')

    @api.depends('bom_ids')
    def _compute_bom_count(self):
        for rec in self:
            rec.bom_count = len(rec.bom_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('semi_code', _('New')) == _('New'):
                vals['semi_code'] = self.env['ir.sequence'].next_by_code(
                    'dl.semi.product') or _('New')
        return super().create(vals_list)

    def action_view_boms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOM — %s') % self.name,
            'res_model': 'dl.bom',
            'view_mode': 'tree,form',
            'domain': [('semi_product_id', '=', self.id)],
            'context': {'default_semi_product_id': self.id},
        }
