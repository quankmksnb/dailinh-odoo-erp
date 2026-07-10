from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DlMaterial(models.Model):
    _inherit = 'dl.material'

    # NCC mặc định gợi ý cho vật tư này (TDS 4.0 §2.2 — dl.material.supplier_id,
    # nullable). Khác dl.material.price.supplier_id (NCC của riêng 1 lần nhập giá).
    supplier_id = fields.Many2one(
        'res.partner', string='Nhà cung cấp mặc định',
        domain=[('partner_role', 'in', ('supplier', 'both')), ('active', '=', True)])

    @api.constrains('supplier_id')
    def _check_supplier_role(self):
        for rec in self:
            if rec.supplier_id and rec.supplier_id.partner_role not in ('supplier', 'both'):
                raise ValidationError(
                    'NCC mặc định phải là một Nhà cung cấp (partner_role = supplier/both).'
                )
