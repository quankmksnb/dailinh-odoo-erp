import logging
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Chặn sửa dòng giá đã lưu (BR-Material-05) — ngoại trừ status/invalid_reason.
_IMMUTABLE_FIELDS = {'material_id', 'supplier_id', 'unit_price', 'source', 'valid_from', 'valid_to'}


class DlMaterialPrice(models.Model):
    _name = 'dl.material.price'
    _description = 'Bảng giá Vật tư'
    _order = 'material_id, valid_from desc'

    material_id = fields.Many2one('dl.material', string='Vật tư', required=True,
                                   ondelete='restrict', index=True)
    supplier_id = fields.Many2one('res.partner', string='Nhà cung cấp', required=True,
                                   domain=[('is_dlm_supplier', '=', True)])
    unit_price = fields.Float(string='Đơn giá', required=True)
    source = fields.Char(string='Nguồn giá')
    valid_from = fields.Date(string='Ngày hiệu lực', required=True,
                              default=fields.Date.context_today)
    valid_to = fields.Date(string='Ngày hết hiệu lực')
    status = fields.Selection([
        ('active', 'Hiệu lực'),
        ('expired', 'Hết hạn'),
        ('invalid', 'Không hợp lệ'),
    ], string='Trạng thái', default='active')
    invalid_reason = fields.Text(string='Lý do không hợp lệ')
    auto_close_preview = fields.Char(string='Cảnh báo đóng giá cũ',
                                      compute='_compute_auto_close_preview', store=False)

    @api.depends('material_id', 'valid_from')
    def _compute_auto_close_preview(self):
        for rec in self:
            rec.auto_close_preview = False
            if not rec.material_id or not rec.valid_from:
                continue
            open_price = self.search([
                ('material_id', '=', rec.material_id.id),
                ('status', '=', 'active'),
                ('valid_to', '=', False),
            ], limit=1) - rec
            if open_price and open_price.valid_from < rec.valid_from:
                close_date = rec.valid_from - timedelta(days=1)
                rec.auto_close_preview = _(
                    "Lưu dòng giá này sẽ TỰ ĐỘNG đóng hiệu lực dòng giá đang mở hiện tại "
                    "(NCC: %(supplier)s, từ %(from)s) — đặt Ngày hết hạn = %(close)s."
                ) % {
                    'supplier': open_price.supplier_id.display_name,
                    'from': open_price.valid_from,
                    'close': close_date,
                }

    @api.constrains('valid_from', 'valid_to')
    def _check_valid_from_before_valid_to(self):
        for rec in self:
            if rec.valid_to and rec.valid_from > rec.valid_to:
                raise ValidationError(_(
                    "Ngày hiệu lực (%(f)s) phải trước hoặc bằng Ngày hết hiệu lực (%(t)s)."
                ) % {'f': rec.valid_from, 't': rec.valid_to})

    @api.constrains('material_id', 'valid_from', 'valid_to', 'status')
    def _check_no_overlap(self):
        for rec in self:
            if rec.status == 'invalid':
                continue
            siblings = self.search([
                ('id', '!=', rec.id),
                ('material_id', '=', rec.material_id.id),
                ('status', '!=', 'invalid'),
            ])
            new_from = rec.valid_from
            new_to = rec.valid_to or date.max
            for sib in siblings:
                sib_from = sib.valid_from
                sib_to = sib.valid_to or date.max
                if new_from <= sib_to and sib_from <= new_to:
                    raise ValidationError(_(
                        "Khoảng hiệu lực %(f)s → %(t)s của vật tư '%(m)s' bị chồng lấn với "
                        "dòng giá đã có (%(sf)s → %(st)s, NCC: %(sup)s). Vui lòng điều chỉnh ngày."
                    ) % {
                        'f': new_from,
                        't': rec.valid_to or 'vô hạn',
                        'm': rec.material_id.display_name,
                        'sf': sib_from,
                        'st': sib.valid_to or 'vô hạn',
                        'sup': sib.supplier_id.display_name,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if vals.get('status', 'active') == 'active' and vals.get('material_id') and vals.get('valid_from'):
                open_price = self.search([
                    ('material_id', '=', vals['material_id']),
                    ('status', '=', 'active'),
                    ('valid_to', '=', False),
                ], limit=1)
                new_from = fields.Date.to_date(vals['valid_from'])
                if open_price and open_price.valid_from < new_from:
                    close_date = new_from - timedelta(days=1)
                    open_price.with_context(dlm_auto_close=True).write({'valid_to': close_date})
                    open_price.material_id.message_post(body=_(
                        "Tự động đóng hiệu lực dòng giá cũ (NCC: %(supplier)s) — "
                        "Ngày hết hạn = %(close)s do dòng giá mới bắt đầu %(new)s."
                    ) % {
                        'supplier': open_price.supplier_id.display_name,
                        'close': close_date,
                        'new': new_from,
                    })
            records |= super(DlMaterialPrice, self).create([vals])
        return records

    def write(self, vals):
        if (not self.env.su and not self.env.context.get('dlm_auto_close')
                and _IMMUTABLE_FIELDS & vals.keys()):
            raise UserError(_(
                'Dòng giá đã lưu không được sửa — dùng "Cập nhật giá mới" để tạo dòng mới.'
            ))
        return super().write(vals)

    def action_mark_invalid(self):
        if not self.env.su and not self.env.user.has_group('dl_base.dl_group_accountant'):
            raise AccessError(_('Chỉ Kế toán nội bộ được đánh dấu giá không hợp lệ.'))
        self.write({'status': 'invalid'})

    @api.model
    def get_active_price(self, material_id, at_date=None):
        at_date = at_date or fields.Date.context_today(self)
        return self.search([
            ('material_id', '=', material_id),
            ('status', '=', 'active'),
            ('valid_from', '<=', at_date),
            '|', ('valid_to', '=', False), ('valid_to', '>=', at_date),
        ], order='valid_from desc', limit=1)

    @api.model
    def _cron_scan_price_validity(self):
        today = fields.Date.context_today(self)

        to_expire = self.search([
            ('status', '=', 'active'),
            ('valid_to', '!=', False),
            ('valid_to', '<', today),
        ])
        to_expire.write({'status': 'expired'})
        _logger.info('dlm_material cron: %s dòng giá chuyển Expired.', len(to_expire))

        threshold = int(self.env['ir.config_parameter'].sudo().get_param(
            'dlm_material.expiry_warning_days', 15))
        accountant_users = self.env.ref('dl_base.dl_group_accountant').users
        warned = 0
        for material in self.env['dl.material'].search([('status', '=', 'active')]):
            if material.has_active_price:
                continue
            last_price = self.search(
                [('material_id', '=', material.id)],
                order='valid_to desc, valid_from desc', limit=1)
            overdue_days = ((today - last_price.valid_to).days
                            if last_price and last_price.valid_to else None)
            if overdue_days is None or overdue_days > threshold:
                material.message_post(body=_(
                    "Vật tư '%(name)s' đang thiếu giá hiệu lực (quá hạn > %(threshold)s ngày). "
                    "Vui lòng bổ sung giá mới."
                ) % {'name': material.display_name, 'threshold': threshold})
                if accountant_users:
                    material.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary=_('Bổ sung giá vật tư: %s') % material.display_name,
                        user_id=accountant_users[0].id)
                warned += 1
        _logger.info('dlm_material cron: đã cảnh báo %s vật tư quá hạn/thiếu giá (ngưỡng %s ngày).',
                     warned, threshold)
