from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError

# Field-level RBAC (BR/AC-6, AC-7): Odoo's per-field `groups=` kwarg only hides a
# field in views, it does not block write()/RPC — so we enforce it explicitly here.
_TECH_ONLY_FIELDS = {'material_code', 'name', 'uom_id', 'categ_id'}
_ACCOUNTANT_ONLY_FIELDS = {'active'}


class DlMaterial(models.Model):
    _name = 'dl.material'
    _description = 'Vật tư'
    _order = 'material_code'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'product.product': 'product_id'}
    _sql_constraints = [
        ('material_code_uniq', 'unique(material_code)', 'Mã vật tư đã tồn tại, vui lòng chọn mã khác.'),
    ]

    product_id = fields.Many2one('product.product', string='Sản phẩm', required=True,
                                  ondelete='cascade', auto_join=True)
    material_code = fields.Char(string='Mã vật tư', required=True, tracking=True)
    # name/uom_id/categ_id/active đều delegate qua product_id (product.product/product.template)
    # theo TDS 4.0 — không còn field code/unit/category/status/technical_spec riêng trên dl_material.

    price_ids = fields.One2many('dl.material.price', 'material_id', string='Lịch sử giá')
    # compute_sudo=True: hàm tính này phải đọc price_ids bất kể quyền của người xem
    # Material hiện tại — nếu không, Kỹ thuật/BA/Trưởng phòng KD (không có quyền xem
    # dl.material.price) sẽ bị AccessError ngay khi mở danh sách/form Vật tư.
    active_price_id = fields.Many2one('dl.material.price', string='Giá đang hiệu lực',
                                       compute='_compute_price_info', store=False,
                                       compute_sudo=True)
    has_active_price = fields.Boolean(string='Đã có giá hiệu lực',
                                       compute='_compute_price_info', store=False,
                                       compute_sudo=True,
                                       search='_search_has_active_price')
    price_status = fields.Selection([
        ('none', 'Chưa có giá'),
        ('ok', 'Bình thường'),
        ('warning', 'Sắp hết hạn'),
        ('expired', 'Quá hạn'),
    ], string='Tình trạng giá', compute='_compute_price_info', store=False,
       compute_sudo=True, search='_search_price_status')

    # `default=` bên cạnh `compute=` là cần thiết: cơ chế onchange() của Odoo khi
    # tạo bản ghi mới lấy giá trị khởi tạo qua default_get(), field chỉ có compute
    # (không có default) sẽ bị gán tạm False trước khi compute chạy và giá trị đó
    # không bao giờ được tính lại trên form "New" chưa lưu.
    is_technician = fields.Boolean(
        compute='_compute_is_technician', compute_sudo=True,
        default=lambda self: self.env.user.has_group('dl_base.dl_group_tech'))

    def _compute_is_technician(self):
        is_tech = self.env.user.has_group('dl_base.dl_group_tech')
        for rec in self:
            rec.is_technician = is_tech

    @api.depends('price_ids.valid_from', 'price_ids.valid_to')
    def _compute_price_info(self):
        today = fields.Date.context_today(self)
        warning_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'dlm_material.expiry_warning_days', 15))
        for material in self:
            candidates = material.price_ids.filtered(
                lambda p: p.valid_from <= today
                and (not p.valid_to or p.valid_to >= today)
            )
            current = candidates.sorted('valid_from', reverse=True)[:1]
            material.active_price_id = current
            material.has_active_price = bool(current)
            if not current:
                material.price_status = 'expired' if material.price_ids else 'none'
            elif current.valid_to and (current.valid_to - today).days <= warning_days:
                material.price_status = 'warning'
            else:
                material.price_status = 'ok'

    def _search_has_active_price(self, operator, value):
        want = value if operator == '=' else not value
        materials = self.search([]).filtered(lambda m: m.has_active_price == want)
        return [('id', 'in', materials.ids)]

    def _search_price_status(self, operator, value):
        values = value if isinstance(value, (list, tuple)) else [value]
        materials = self.search([]).filtered(lambda m: m.price_status in values)
        if operator not in ('in', '='):
            materials = self.search([]) - materials
        return [('id', 'in', materials.ids)]

    def write(self, vals):
        if not self.env.su:
            user = self.env.user
            if _TECH_ONLY_FIELDS & vals.keys() and not user.has_group('dl_base.dl_group_tech'):
                raise AccessError(_('Chỉ Kỹ thuật được sửa thông tin/thông số Vật tư.'))
            if _ACCOUNTANT_ONLY_FIELDS & vals.keys() and not user.has_group('dl_base.dl_group_accountant'):
                raise AccessError(_('Chỉ Kế toán nội bộ được Kích hoạt/Ngừng dùng vật tư.'))
        return super().write(vals)

    def action_activate(self):
        self.write({'active': True})

    def action_discontinue(self):
        self.write({'active': False})

    def action_new_price(self):
        self.ensure_one()
        current = self.active_price_id
        suggested_from = fields.Date.context_today(self)
        if current:
            suggested_from = current.valid_to or fields.Date.context_today(self)
            if current.valid_to:
                suggested_from = current.valid_to + relativedelta(days=1)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cập nhật giá mới'),
            'res_model': 'dl.material.price',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_material_id': self.id,
                'default_uom_id': self.uom_id.id,
                'default_supplier_id': current.supplier_id.id if current else False,
                'default_valid_from': suggested_from,
            },
        }
