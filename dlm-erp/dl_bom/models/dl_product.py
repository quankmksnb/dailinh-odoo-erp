from odoo import api, fields, models, _


class DlProductCategory(models.Model):
    """A2 — dl.product.category: nhóm sản phẩm DLM (khác product.category chuẩn Odoo)."""
    _name = 'dl.product.category'
    _description = 'Nhóm sản phẩm (DLM)'
    _order = 'name'

    name = fields.Char(string='Tên nhóm', required=True)
    template_bom_id = fields.Many2one(
        'dl.bom', string='BOM mẫu mặc định',
        help='Khung BOM trừu tượng cấp nhóm (dl.bom với category_id=nhóm này), '
             'gợi ý khi tạo sản phẩm mới trong nhóm. Không bắt buộc — nhóm chỉ '
             'chứa hàng trading thì không cần BOM mẫu.',
    )
    active = fields.Boolean(default=True)
    product_ids = fields.One2many(
        'product.product', 'product_category_id', string='Sản phẩm',
        domain=[('product_kind', '=', 'finished')],
    )
    product_count = fields.Integer(compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)


class ProductProduct(models.Model):
    """A3 — dl.product: KHÔNG tạo bảng riêng, mở rộng trực tiếp product.product
    (Thành phẩm gia công/trading) theo đúng TDS — record nằm trong bảng product_product."""
    _inherit = 'product.product'

    product_kind = fields.Selection([
        ('finished', 'Thành phẩm'),
        ('semi', 'Bán thành phẩm'),
    ], string='Loại sản phẩm DLM', default='finished',
        help='finished = A3 (thành phẩm), semi = A3b (đặt qua dl.semi.product, '
             'không tự chọn tay ở đây).')
    supply_type = fields.Selection([
        ('manufactured', 'Gia công theo yêu cầu'),
        ('trading', 'Hàng có sẵn / nhập về'),
    ], string='Loại cung ứng', default='manufactured')
    product_category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm (DLM)',
    )
    dimension_spec = fields.Char(string='Kích thước (DxRxC, mm)')
    purchase_cost = fields.Float(
        string='Giá vốn nhập', digits='Product Price',
        help='Chỉ áp dụng khi supply_type=trading — thay thế chi phí tính từ BOM.',
    )
    default_supplier_id = fields.Many2one(
        'res.partner', string='NCC mặc định (hàng trading)',
    )
    technical_note = fields.Text(string='Ghi chú kỹ thuật')

    bom_ids = fields.One2many('dl.bom', 'product_id', string='BOM liên quan')
    bom_count = fields.Integer(compute='_compute_bom_count', string='Số BOM')

    @api.depends('bom_ids')
    def _compute_bom_count(self):
        for rec in self:
            rec.bom_count = len(rec.bom_ids)

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
