from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DlBomLine(models.Model):
    _name = 'dl.bom.line'
    _description = 'Dòng BOM'
    _order = 'sequence, id'

    bom_id = fields.Many2one(
        'dl.bom', string='BOM', required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Thứ tự', default=10)

    component_type = fields.Selection([
        ('raw_material', 'Vật tư thô'),
        ('semi_finished', 'Bán thành phẩm'),
    ], string='Loại thành phần', required=True, default='raw_material')

    material_id = fields.Many2one(
        'dl.material', string='Vật tư',
        domain=[('status', '=', 'active')],
    )
    semi_finished_id = fields.Many2one(
        'dl.semi.product', string='Bán thành phẩm',
        domain=[('state', '=', 'active')],
    )

    component_name = fields.Char(
        string='Tên thành phần', compute='_compute_component_name', store=True,
    )
    component_uom = fields.Char(
        string='ĐVT', compute='_compute_component_name', store=True,
    )

    # Input parametric
    input_length_mm = fields.Float(string='Chiều dài (mm)', digits=(12, 3))
    input_width_mm = fields.Float(string='Chiều rộng (mm)', digits=(12, 3))
    input_thickness_mm = fields.Float(string='Độ dày (mm)', digits=(12, 3))

    quantity = fields.Float(
        string='Số lượng định mức', required=True, default=1.0,
        digits='Product Unit of Measure',
    )
    waste_rate = fields.Float(
        string='Tỷ lệ hao hụt (%)', default=0.0, digits=(5, 2),
    )
    effective_qty = fields.Float(
        string='SL thực tế', compute='_compute_effective_qty',
        store=True, digits='Product Unit of Measure',
    )

    price_snapshot = fields.Float(
        string='Đơn giá snapshot', digits='Product Price', default=0.0,
        groups='dl_base.dl_group_ceo,dl_base.dl_group_admin,'
               'dl_base.dl_group_accountant,dl_base.dl_group_sales_manager',
    )
    subtotal = fields.Float(
        string='Thành tiền', compute='_compute_subtotal',
        store=True, digits='Product Price',
        groups='dl_base.dl_group_ceo,dl_base.dl_group_admin,'
               'dl_base.dl_group_accountant,dl_base.dl_group_sales_manager',
    )

    is_override = fields.Boolean(string='Ghi đè SL', default=False)
    override_reason = fields.Char(string='Lý do ghi đè')

    uom_id = fields.Many2one('uom.uom', string='Đơn vị tính')
    note = fields.Char(string='Ghi chú')

    material_status = fields.Selection(
        related='material_id.status', string='Trạng thái VT', readonly=True,
    )
    material_price_status = fields.Selection(
        related='material_id.price_status', string='Tình trạng giá', readonly=True,
    )

    @api.depends('component_type', 'material_id', 'semi_finished_id')
    def _compute_component_name(self):
        for line in self:
            if line.component_type == 'raw_material' and line.material_id:
                line.component_name = line.material_id.name
                line.component_uom = line.material_id.unit or ''
            elif line.component_type == 'semi_finished' and line.semi_finished_id:
                line.component_name = line.semi_finished_id.name
                line.component_uom = line.semi_finished_id.uom_id.name if line.semi_finished_id.uom_id else ''
            else:
                line.component_name = ''
                line.component_uom = ''

    @api.depends('quantity', 'waste_rate')
    def _compute_effective_qty(self):
        for line in self:
            line.effective_qty = line.quantity * (1 + line.waste_rate / 100.0)

    @api.depends('effective_qty', 'price_snapshot')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.effective_qty * line.price_snapshot

    @api.onchange('material_id')
    def _onchange_material_id(self):
        if self.material_id:
            self.component_type = 'raw_material'
            self.uom_id = False
            if self.material_id.active_price_id:
                self.price_snapshot = self.material_id.active_price_id.unit_price

    @api.onchange('semi_finished_id')
    def _onchange_semi_finished_id(self):
        if self.semi_finished_id:
            self.component_type = 'semi_finished'
            self.uom_id = self.semi_finished_id.uom_id
            # Chi phí bán thành phẩm lấy từ BOM con nếu có
            child_boms = self.env['dl.bom'].search([
                ('semi_product_id', '=', self.semi_finished_id.id),
                ('status', 'in', ('confirmed', 'locked')),
                ('bom_type', '=', 'quotation'),
            ], order='version desc', limit=1)
            if child_boms:
                self.price_snapshot = child_boms.total_material_cost

    @api.constrains('component_type', 'material_id', 'semi_finished_id')
    def _check_component_ref(self):
        for line in self:
            if line.component_type == 'raw_material' and not line.material_id:
                raise ValidationError(_(
                    'Dòng loại "Vật tư thô" phải chọn vật tư.'))
            if line.component_type == 'semi_finished' and not line.semi_finished_id:
                raise ValidationError(_(
                    'Dòng loại "Bán thành phẩm" phải chọn bán thành phẩm.'))

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Số lượng phải lớn hơn 0.'))

    @api.constrains('is_override', 'override_reason')
    def _check_override_reason(self):
        for line in self:
            if line.is_override and not line.override_reason:
                raise ValidationError(_(
                    'Phải nhập lý do khi ghi đè số lượng tự tính.'))

    @api.constrains('input_length_mm', 'input_width_mm', 'input_thickness_mm')
    def _check_dimensions(self):
        for line in self:
            for dim, label in [
                (line.input_length_mm, 'Chiều dài'),
                (line.input_width_mm, 'Chiều rộng'),
                (line.input_thickness_mm, 'Độ dày'),
            ]:
                if dim and dim < 0:
                    raise ValidationError(
                        _('%s phải lớn hơn hoặc bằng 0.') % label)
