from odoo import api, fields, models


class DlProductCategory(models.Model):
    """Nhóm sản phẩm (S05) — cho phép Trưởng KD/Admin tạo nhóm mới.

    ondelete='restrict' trên dl.product.category_id ⇒ không xóa được nhóm còn
    sản phẩm (EX-34).
    """
    _name = 'dl.product.category'
    _description = 'Nhóm sản phẩm'
    _order = 'name'
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Nhóm sản phẩm đã tồn tại.'),
    ]

    name = fields.Char(string='Tên nhóm', required=True)
    product_count = fields.Integer(string='Số sản phẩm', compute='_compute_product_count')

    def _compute_product_count(self):
        data = self.env['dl.product'].read_group(
            [('category_id', 'in', self.ids)], ['category_id'], ['category_id'])
        mapping = {d['category_id'][0]: d['category_id_count'] for d in data}
        for rec in self:
            rec.product_count = mapping.get(rec.id, 0)


class DlProduct(models.Model):
    _name = 'dl.product'
    _description = 'Sản phẩm'
    _order = 'code'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Mã sản phẩm', readonly=True, copy=False, index=True)
    name = fields.Char(string='Tên sản phẩm', required=True, tracking=True)
    category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm',
        required=True, ondelete='restrict', tracking=True)
    active = fields.Boolean(default=True)
    status_display = fields.Char(string='Trạng thái', compute='_compute_status_display')

    # ── Thuộc tính kỹ thuật (dùng để tìm sản phẩm tương tự ở S07) ─────
    dim_length = fields.Float(string='Dài (mm)')
    dim_width = fields.Float(string='Rộng (mm)')
    dim_height = fields.Float(string='Cao (mm)')
    dim_display = fields.Char(string='Kích thước', compute='_compute_dim_display')
    main_material = fields.Char(string='Vật liệu chính',
                                help='VD: Thép CT3, Inox 304, Nhôm...')
    thickness = fields.Float(string='Độ dày (mm)')
    finish = fields.Selection([
        ('powder', 'Sơn tĩnh điện'),
        ('galv', 'Mạ kẽm'),
        ('raw', 'Để nguyên'),
    ], string='Lớp hoàn thiện')
    est_weight = fields.Float(string='Khối lượng ước tính (kg)')
    tech_note = fields.Text(string='Ghi chú kỹ thuật')

    @api.depends('active')
    def _compute_status_display(self):
        for rec in self:
            rec.status_display = 'Đang sản xuất' if rec.active else 'Ngừng sản xuất'

    @api.depends('dim_length', 'dim_width', 'dim_height')
    def _compute_dim_display(self):
        for rec in self:
            if rec.dim_length or rec.dim_width or rec.dim_height:
                rec.dim_display = '%g × %g × %g mm' % (
                    rec.dim_length or 0, rec.dim_width or 0, rec.dim_height or 0)
            else:
                rec.dim_display = ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('dlm.product') or '/'
        return super().create(vals_list)
