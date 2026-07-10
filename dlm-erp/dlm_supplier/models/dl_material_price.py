from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DlMaterialPrice(models.Model):
    _inherit = 'dl.material.price'

    # Cảnh báo "NCC không còn hoạt động" ở màn Giá Vật tư (S04 mục 6 / S06).
    supplier_active = fields.Boolean(related='supplier_id.active', string='NCC đang hoạt động',
                                      store=False)

    @api.constrains('supplier_id')
    def _check_supplier_active(self):
        for rec in self:
            if not rec.supplier_id:
                continue
            if not rec.supplier_id.active:
                raise ValidationError(
                    'Không thể chọn NCC đã Ngừng hoạt động (Inactive) cho Giá vật tư.'
                )
            if rec.supplier_id.partner_role not in ('supplier', 'both'):
                raise ValidationError(
                    'supplier_id phải là một Nhà cung cấp (partner_role = supplier/both).'
                )
