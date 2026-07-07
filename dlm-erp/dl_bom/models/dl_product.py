from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DlProduct(models.Model):
    _name = 'dl.product'
    _description = 'Thành phẩm'
    _order = 'default_code'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _sql_constraints = [
        ('default_code_uniq', 'unique(default_code)',
         'Mã sản phẩm đã tồn tại, vui lòng chọn mã khác.'),
    ]

    name = fields.Char(string='Tên sản phẩm', required=True, tracking=True)
    default_code = fields.Char(
        string='Mã sản phẩm', required=True, tracking=True, copy=False,
        default=lambda self: _('New'),
    )
    category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm',
        required=True, tracking=True,
    )
    uom_id = fields.Many2one(
        'uom.uom', string='Đơn vị tính', required=True,
    )
    supply_type = fields.Selection([
        ('manufactured', 'Gia công theo yêu cầu'),
        ('trading', 'Hàng có sẵn / nhập về'),
    ], string='Loại cung ứng', required=True, default='manufactured', tracking=True)
    purchase_cost = fields.Float(
        string='Giá vốn nhập', digits='Product Price',
        help='Chỉ áp dụng khi loại cung ứng = Hàng có sẵn',
    )
    dimension_spec = fields.Char(string='Kích thước (DxRxC, mm)')
    material_spec = fields.Char(string='Vật liệu chính')
    finish_spec = fields.Selection([
        ('powder_coating', 'Sơn tĩnh điện'),
        ('galvanized', 'Mạ kẽm'),
        ('raw', 'Để nguyên'),
        ('other', 'Khác'),
    ], string='Lớp hoàn thiện')
    weight_estimate = fields.Float(string='Khối lượng ước tính (kg)')
    technical_note = fields.Text(string='Ghi chú kỹ thuật')

    state = fields.Selection([
        ('active', 'Đang sản xuất'),
        ('discontinued', 'Ngừng'),
    ], string='Trạng thái', default='active', tracking=True)
    active = fields.Boolean(default=True)

    bom_ids = fields.One2many('dl.bom', 'product_id', string='BOM liên quan')
    bom_count = fields.Integer(compute='_compute_bom_count', string='Số BOM')

    @api.depends('bom_ids')
    def _compute_bom_count(self):
        for rec in self:
            rec.bom_count = len(rec.bom_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('default_code', _('New')) == _('New'):
                vals['default_code'] = self.env['ir.sequence'].next_by_code(
                    'dl.product') or _('New')
        return super().create(vals_list)

    def action_discontinue(self):
        self.write({'state': 'discontinued'})

    def action_activate(self):
        self.write({'state': 'active'})

    def action_view_boms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOM — %s') % self.name,
            'res_model': 'dl.bom',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }


class DlProductCategory(models.Model):
    _name = 'dl.product.category'
    _description = 'Nhóm sản phẩm'
    _order = 'name'

    name = fields.Char(string='Tên nhóm', required=True)
    template_bom_id = fields.Many2one(
        'dl.bom', string='BOM mẫu mặc định',
        domain=[('bom_type', '=', 'template')],
        help='BOM mẫu mặc định gợi ý khi tạo sản phẩm mới trong nhóm',
    )
    active = fields.Boolean(default=True)
    product_ids = fields.One2many('dl.product', 'category_id', string='Sản phẩm')
    product_count = fields.Integer(compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)
