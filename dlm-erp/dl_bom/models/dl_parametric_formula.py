from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    from simpleeval import simple_eval
except ImportError:  # pragma: no cover
    simple_eval = None


class DlParametricFormula(models.Model):
    """C3 — dl.parametric.formula: công thức tính quantity của dl.bom.line theo
    kích thước tham số (length/width/thickness). Cấu hình do Admin IT nhập —
    Kỹ thuật chỉ cung cấp thông số trên giấy/email (đúng RACI trong TDS),
    Kỹ thuật chỉ có quyền xem (readonly)."""
    _name = 'dl.parametric.formula'
    _description = 'Công thức tham số kỹ thuật'
    _order = 'material_id'
    _sql_constraints = [
        ('material_uniq', 'unique(material_id)',
         'Vật tư này đã có công thức tham số — mỗi vật tư chỉ 1 công thức active.'),
    ]

    material_id = fields.Many2one(
        'dl.material', string='Vật tư', required=True, ondelete='cascade',
    )
    formula_type = fields.Selection([
        ('volume_density', 'Khối lượng theo thể tích (dài×rộng×dày×khối lượng riêng)'),
        ('custom_expression', 'Biểu thức tùy chỉnh'),
        ('direct_count', 'Đếm trực tiếp (không theo kích thước)'),
    ], string='Loại công thức', required=True, default='volume_density')

    formula_expression = fields.Char(
        string='Biểu thức (custom_expression)',
        help='Chỉ dùng khi formula_type=custom_expression. Biến khả dụng: '
             'length_mm, width_mm, thickness_mm, coefficient_value. '
             'VD: ((width_mm/1000)**2-((width_mm-2*thickness_mm)/1000)**2)'
             '*(length_mm/1000)*coefficient_value',
    )
    coefficient_value = fields.Float(
        string='Hệ số (khối lượng riêng...)', default=0.0,
        help='VD: khối lượng riêng thép = 7850 kg/m3',
    )
    output_uom_id = fields.Many2one('uom.uom', string='Đơn vị kết quả')
    formula_note = fields.Char(string='Ghi chú công thức')

    # Sandbox test-case trước khi active (đúng case Ống thép vuông trong TDS)
    test_length_mm = fields.Float(string='Test: dài (mm)')
    test_width_mm = fields.Float(string='Test: rộng (mm)')
    test_thickness_mm = fields.Float(string='Test: dày (mm)')
    test_expected_result = fields.Float(string='Kết quả mong đợi (KTV tính tay)')
    test_actual_result = fields.Float(string='Kết quả hệ thống chạy', readonly=True)
    is_test_confirmed = fields.Boolean(string='Đã xác nhận test-case', readonly=True)

    active = fields.Boolean(default=True)

    def _evaluate(self, length_mm=0.0, width_mm=0.0, thickness_mm=0.0):
        self.ensure_one()
        if self.formula_type == 'direct_count':
            return 1.0
        if self.formula_type == 'volume_density':
            return (length_mm / 1000.0) * (width_mm / 1000.0) * (
                thickness_mm / 1000.0) * self.coefficient_value
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

    def action_run_test(self):
        """Admin bấm chạy sandbox test-case trước khi active công thức mới
        (đặc biệt bắt buộc với custom_expression) — ghi vào G1 audit log qua
        mail tracking chuẩn (tracking=True ở field liên quan nếu cần)."""
        for rec in self:
            rec.test_actual_result = rec._evaluate(
                rec.test_length_mm, rec.test_width_mm, rec.test_thickness_mm)
            if (rec.test_expected_result
                    and abs(rec.test_actual_result - rec.test_expected_result) < 0.01):
                rec.is_test_confirmed = True
            else:
                rec.is_test_confirmed = False
