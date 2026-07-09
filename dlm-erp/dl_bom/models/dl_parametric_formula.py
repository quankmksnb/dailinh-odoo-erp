from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    from simpleeval import simple_eval
except ImportError:  # pragma: no cover
    simple_eval = None


class DlParametricFormula(models.Model):
    
    _name = 'dl.parametric.formula'
    _description = 'Công thức tham số kỹ thuật'
    _order = 'material_id'

    material_id = fields.Many2one(
        'dl.material', string='Vật tư', required=True, ondelete='cascade',
    )
    formula_type = fields.Selection([
        ('volume_density', 'Khối lượng theo thể tích (L×W×T×ρ → kg, tấm thép)'),
        ('linear_density', 'Khối lượng theo chiều dài (L×kg/m → ống, thanh)'),
        ('area_based', 'Diện tích (L×W×hệ số → m²)'),
        ('direct_count', 'Đếm trực tiếp (nhập tay — ốc vít, số lượng...)'),
        ('custom_expression', 'Biểu thức tùy chỉnh (hình dạng mới)'),
    ], string='Loại công thức', required=True, default='volume_density')

    formula_expression = fields.Char(
        string='Biểu thức (custom_expression)',
        help='Chỉ dùng khi formula_type=custom_expression. Biến khả dụng: '
             'length_mm, width_mm, thickness_mm, coefficient_value. '
             'VD: ((width_mm/1000)**2-((width_mm-2*thickness_mm)/1000)**2)'
             '*(length_mm/1000)*coefficient_value',
    )
    coefficient_value = fields.Float(
        string='Hệ số', default=0.0,
        help='VD: khối lượng riêng thép = 7850 kg/m3 (volume_density); '
             'kg/m (linear_density); hệ số diện tích (area_based)',
    )
    coefficient_uom_id = fields.Many2one(
        'uom.uom', string='Đơn vị hệ số (audit)',
        help='Đơn vị của coefficient_value, chỉ mang tính ghi chú/audit.',
    )
    output_uom_id = fields.Many2one(
        'uom.uom', string='Đơn vị kết quả', required=True,
        help='PHẢI khớp material_id.uom_id.',
    )
    formula_note = fields.Text(string='Ghi chú công thức')

    # Sandbox test-case trước khi active (đúng case Ống thép vuông trong TDS)
    test_length_mm = fields.Float(string='Test: dài (mm)')
    test_width_mm = fields.Float(string='Test: rộng (mm)')
    test_thickness_mm = fields.Float(string='Test: dày (mm)')
    test_expected_result = fields.Float(string='Kết quả mong đợi (Admin tự tính tay)')
    test_actual_result = fields.Float(string='Kết quả hệ thống chạy', readonly=True)
    is_test_confirmed = fields.Boolean(string='Đã xác nhận test-case khớp', readonly=True)

    active = fields.Boolean(default=True)
    updated_by = fields.Many2one(
        "res.users",
        string="Người cập nhật",
        readonly=True,
        default=lambda self: self.env.user,
    )

    def _evaluate(self, length_mm=0.0, width_mm=0.0, thickness_mm=0.0):
        self.ensure_one()
        if self.formula_type == 'direct_count':
            return 1.0
        if self.formula_type == 'volume_density':
            return (length_mm / 1000.0) * (width_mm / 1000.0) * (
                thickness_mm / 1000.0) * self.coefficient_value
        if self.formula_type == 'linear_density':
            return (length_mm / 1000.0) * self.coefficient_value
        if self.formula_type == 'area_based':
            return (length_mm / 1000.0) * (width_mm / 1000.0) * self.coefficient_value
        if self.formula_type == 'custom_expression':
            if not self.formula_expression:
                return 0.0
            if simple_eval is None:
                raise UserError(_(
                    'Thiếu thư viện simpleeval trên server — không thể chạy '
                    'custom_expression. Liên hệ Admin IT.'))
            names = {
                'length_mm': length_mm,
                'width_mm': width_mm,
                'thickness_mm': thickness_mm,
                'coefficient_value': self.coefficient_value,
            }
            try:
                return float(simple_eval(self.formula_expression, names=names))
            except Exception as exc:
                raise UserError(_(
                    'Biểu thức công thức không hợp lệ: %s') % exc)
        return 0.0

    @api.constrains('formula_type', 'formula_expression')
    def _check_custom_expression(self):
        for rec in self:
            if rec.formula_type == 'custom_expression' and not rec.formula_expression:
                raise ValidationError(_(
                    'Loại "Biểu thức tùy chỉnh" phải nhập formula_expression.'))

    @api.constrains('material_id', 'active')
    def _check_one_active_per_material(self):
        # 1 vật tư → tối đa 1 công thức active (index strategy TDS §3.4) —
        # không dùng SQL UNIQUE cứng vì cho phép giữ lịch sử bản ghi inactive.
        for rec in self:
            if not rec.active:
                continue
            dup = self.search([
                ('material_id', '=', rec.material_id.id),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'Vật tư "%s" đã có công thức tham số đang active (%s). '
                    'Vô hiệu hoá công thức cũ trước khi tạo công thức mới.'
                ) % (rec.material_id.name, dup.name if hasattr(dup, 'name') else dup.id))

    def write(self, vals):
        if not self.env.context.get('skip_updated_by'):
            vals.setdefault("updated_by", self.env.user.id)
        return super().write(vals)

    def action_run_test(self):
        """Admin bấm chạy sandbox test-case trước khi active công thức mới
        (đặc biệt bắt buộc với custom_expression)."""
        for rec in self:
            rec.test_actual_result = rec._evaluate(
                rec.test_length_mm, rec.test_width_mm, rec.test_thickness_mm)
            if (rec.test_expected_result
                    and abs(rec.test_actual_result - rec.test_expected_result) < 0.01):
                rec.is_test_confirmed = True
            else:
                rec.is_test_confirmed = False

    @api.constrains("material_id", "output_uom_id")
    def _check_output_uom(self):
        for rec in self:
            if (
                rec.material_id
                and rec.output_uom_id
                and rec.material_id.uom_id != rec.output_uom_id
            ):
                raise ValidationError(
                    _("Đơn vị kết quả phải trùng với đơn vị tính của vật tư.")
                )