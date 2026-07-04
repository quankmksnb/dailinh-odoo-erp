from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dlm_material_expiry_warning_days = fields.Integer(
        string='Số ngày cảnh báo trước khi giá vật tư hết hạn',
        config_parameter='dlm_material.expiry_warning_days',
        default=15,
    )
