from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DlmCustomer(models.Model):
    """Mở rộng res.partner để quản lý khách hàng theo nghiệp vụ Đại Linh.

    Chiến lược: _inherit res.partner — không tạo bảng DB mới (Entity A1).
    Chỉ hiển thị các partner là khách hàng (customer_rank > 0) trong module này.
    """

    _inherit = 'res.partner'

    customer_type = fields.Selection(
        selection=[
            ('individual', 'Cá nhân'),
            ('enterprise', 'Doanh nghiệp'),
            ('dealer', 'Đại lý'),
        ],
        string='Loại khách hàng',
        default='individual',
        tracking=True,
        help='Phân loại khách hàng theo đặc thù kinh doanh của Đại Linh.',
    )

    dlm_note = fields.Text(
        string='Ghi chú nội bộ',
        help='Ghi chú dành cho BA/Sales — không hiển thị cho khách hàng.',
    )

    # ── Computed display ──────────────────────────────────────────────────

    dlm_customer_type_label = fields.Char(
        string='Loại',
        compute='_compute_customer_type_label',
        store=False,
    )

    @api.depends('customer_type')
    def _compute_customer_type_label(self):
        label_map = {
            'individual': 'Cá nhân',
            'enterprise': 'Doanh nghiệp',
            'dealer': 'Đại lý',
        }
        for rec in self:
            rec.dlm_customer_type_label = label_map.get(rec.customer_type, '')

    # ── Constraints ───────────────────────────────────────────────────────

    @api.constrains('customer_type')
    def _check_customer_type_required(self):
        for rec in self:
            if rec.customer_type is False and rec._origin.customer_type:
                raise ValidationError(
                    'Vui lòng chọn Loại khách hàng trước khi lưu.'
                )
