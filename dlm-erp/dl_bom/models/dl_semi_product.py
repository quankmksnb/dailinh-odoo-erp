from odoo import api, fields, models, _


class DlSemiProduct(models.Model):
    """A3b — dl.semi.product: bảng dl_semi_product MỚI + product_product qua
    _inherits — name/uom_id/type đọc-ghi thẳng qua product_id (đúng TDS)."""
    _name = 'dl.semi.product'
    _description = 'Bán thành phẩm'
    _inherits = {'product.product': 'product_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'semi_code'
    _sql_constraints = [
        ('semi_code_uniq', 'unique(semi_code)',
         'Mã bán thành phẩm đã tồn tại.'),
    ]

    product_id = fields.Many2one(
        'product.product', string='Sản phẩm (BTP)', required=True,
        ondelete='cascade', auto_join=True,
    )
    semi_code = fields.Char(
        string='Mã bán thành phẩm', required=True, tracking=True, copy=False,
        default=lambda self: _('New'),
    )
    dimension_spec = fields.Char(string='Kích thước (DxRxC, mm)')
    material_spec = fields.Char(string='Vật liệu chính')
    technical_note = fields.Text(string='Ghi chú kỹ thuật')

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
            # product_kind là field delegate qua product_id (product.product) —
            # ép 'semi' để phân biệt với Thành phẩm (A3, product_kind='finished').
            vals['product_kind'] = 'semi'
            vals.setdefault('type', 'consu')
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
