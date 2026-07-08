from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class DlBom(models.Model):
    _name = 'dl.bom'
    _description = 'Bill of Materials'
    _order = 'name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _sql_constraints = [
        ('product_version_type_uniq',
         'unique(product_id, version, bom_type)',
         'BOM thành phẩm trùng phiên bản.'),
        ('semi_version_type_uniq',
         'unique(semi_product_id, version, bom_type)',
         'BOM bán thành phẩm trùng phiên bản.'),
    ]

    name = fields.Char(
        string='Mã BOM', required=True, tracking=True, copy=False,
        default=lambda self: _('New'),
    )
    version = fields.Integer(string='Phiên bản', default=1, required=True, tracking=True)
    bom_type = fields.Selection([
        ('template', 'BOM / Công thức chuẩn'),
    ], string='Loại BOM', required=True, default='template', tracking=True,
        help='Theo TDS: mọi dl.bom (dù gắn product_id, semi_product_id hay '
             'category_id) đều là công thức chuẩn tái sử dụng — không có bản '
             'sao riêng theo từng báo giá. dl.quotation.line.bom_id trỏ thẳng '
             'vào bản ghi này.')

    # XOR: chỉ 1 trong 3 có giá trị. ondelete='restrict' (thay vì mặc định
    # 'set null') vì nếu Postgres tự null hoá lúc xoá sản phẩm, dòng dl.bom sẽ
    # còn lại KHÔNG có owner nào — vi phạm ràng buộc XOR (_check_owner_xor)
    # mà không đi qua được validation Python. Phải xoá/lưu trữ BOM trước.
    product_id = fields.Many2one(
        'product.product', string='Thành phẩm', tracking=True,
        domain=[('product_kind', '=', 'finished'), ('active', '=', True)],
        ondelete='restrict',
    )
    semi_product_id = fields.Many2one(
        'dl.semi.product', string='Bán thành phẩm', tracking=True,
        ondelete='restrict',
    )
    category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm (BOM mẫu)', tracking=True,
        ondelete='restrict',
    )

    owner_name = fields.Char(
        string='Sản phẩm / Nhóm', compute='_compute_owner_name', store=True,
    )

    product_qty = fields.Float(
        string='Số lượng đầu ra', default=1.0, required=True,
        digits='Product Unit of Measure',
    )
    status = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('locked', 'Đã khóa'),
        ('archived', 'Lưu trữ'),
    ], string='Trạng thái', default='draft', tracking=True, copy=False)

    line_ids = fields.One2many('dl.bom.line', 'bom_id', string='Dòng BOM', copy=True)
    line_count = fields.Integer(compute='_compute_line_count')

    total_material_cost = fields.Float(
        string='Tổng chi phí vật tư', compute='_compute_total_material_cost',
        store=True, digits='Product Price',
    )

    note = fields.Text(string='Ghi chú kỹ thuật')
    change_note = fields.Text(string='Ghi chú thay đổi', tracking=True)

    confirmed_by = fields.Many2one('res.users', string='Người xác nhận', readonly=True)
    confirmed_date = fields.Datetime(string='Ngày xác nhận', readonly=True)

    has_expired_price = fields.Boolean(
        compute='_compute_has_expired_price', store=False,
    )

    @api.depends('product_id', 'semi_product_id', 'category_id')
    def _compute_owner_name(self):
        for rec in self:
            if rec.product_id:
                rec.owner_name = rec.product_id.name
            elif rec.semi_product_id:
                rec.owner_name = rec.semi_product_id.name
            elif rec.category_id:
                rec.owner_name = rec.category_id.name
            else:
                rec.owner_name = ''

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('line_ids.subtotal')
    def _compute_total_material_cost(self):
        for rec in self:
            rec.total_material_cost = sum(rec.line_ids.mapped('subtotal'))

    def _compute_has_expired_price(self):
        today = fields.Date.today()
        for rec in self:
            rec.has_expired_price = any(
                line.material_id and line.material_id.price_status == 'expired'
                for line in rec.line_ids
                if line.component_type == 'raw_material'
            )

    @api.constrains('product_id', 'semi_product_id', 'category_id')
    def _check_owner_xor(self):
        for rec in self:
            owners = bool(rec.product_id) + bool(rec.semi_product_id) + bool(rec.category_id)
            if owners != 1:
                raise ValidationError(_(
                    'BOM phải liên kết chính xác 1 trong: Thành phẩm, '
                    'Bán thành phẩm, hoặc Nhóm sản phẩm (khung mẫu cấp nhóm).'))

    @api.constrains('product_qty')
    def _check_product_qty(self):
        for rec in self:
            if rec.product_qty <= 0:
                raise ValidationError(_('Số lượng đầu ra phải lớn hơn 0.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dl.bom') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.status != 'draft':
                raise UserError(_('Chỉ BOM nháp mới có thể xác nhận.'))
            if not rec.line_ids:
                raise UserError(_(
                    'BOM cần có ít nhất 1 dòng vật tư trước khi xác nhận.'))
            rec.write({
                'status': 'confirmed',
                'confirmed_by': self.env.uid,
                'confirmed_date': fields.Datetime.now(),
            })
            rec.message_post(body=_(
                'BOM đã được xác nhận bởi %s.') % self.env.user.name)

    def action_lock(self):
        for rec in self:
            if rec.status != 'confirmed':
                raise UserError(_('Chỉ BOM đã xác nhận mới có thể khóa.'))
            rec.write({'status': 'locked'})

    def action_archive_bom(self):
        for rec in self:
            if rec.status == 'locked':
                raise UserError(_(
                    'BOM đã khóa không thể lưu trữ trực tiếp. '
                    'Hãy tạo phiên bản mới thay vì lưu trữ.'))
            rec.write({'status': 'archived'})

    def action_reset_draft(self):
        for rec in self:
            if rec.status not in ('confirmed',):
                raise UserError(_('Chỉ BOM đã xác nhận mới có thể đưa về nháp.'))
            rec.write({
                'status': 'draft',
                'confirmed_by': False,
                'confirmed_date': False,
            })

    def action_create_new_version(self):
        self.ensure_one()
        if self.status not in ('confirmed', 'locked'):
            raise UserError(_(
                'Chỉ có thể tạo phiên bản mới từ BOM đã xác nhận hoặc đã khóa.'))
        max_version = max(
            self.search([
                ('product_id', '=', self.product_id.id if self.product_id else False),
                ('semi_product_id', '=', self.semi_product_id.id if self.semi_product_id else False),
                ('category_id', '=', self.category_id.id if self.category_id else False),
                ('bom_type', '=', self.bom_type),
            ]).mapped('version') or [0]
        )
        new_bom = self.copy({
            'version': max_version + 1,
            'status': 'draft',
            'confirmed_by': False,
            'confirmed_date': False,
            'change_note': _('Tạo từ %s V%s') % (self.name, self.version),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.bom',
            'res_id': new_bom.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_copy_as_product_bom(self):
        """Sao chép khung mẫu cấp nhóm (category_id) thành BOM cụ thể cho 1
        thành phẩm — dùng khi KTV tạo sản phẩm mới thuộc nhóm đã có BOM mẫu."""
        self.ensure_one()
        if not self.category_id:
            raise UserError(_(
                'Chỉ BOM mẫu cấp nhóm (category_id) mới có thể sao chép thành BOM sản phẩm.'))
        new_bom = self.copy({
            'status': 'draft',
            'version': 1,
            'category_id': False,
            'confirmed_by': False,
            'confirmed_date': False,
            'change_note': _('Sao chép từ khung mẫu %s') % self.name,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.bom',
            'res_id': new_bom.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def write(self, vals):
        for rec in self:
            if rec.status == 'locked' and not self.env.context.get('force_locked_write'):
                allowed = {'message_main_attachment_id', 'message_follower_ids'}
                if set(vals.keys()) - allowed:
                    raise UserError(_(
                        'BOM đã khóa không thể sửa trực tiếp. '
                        'Hãy tạo phiên bản mới.'))
        return super().write(vals)
