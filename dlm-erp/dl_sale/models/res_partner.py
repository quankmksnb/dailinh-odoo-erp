from odoo import models, fields, api


class ResPartner(models.Model):
    """
    Mở rộng res.partner cho nghiệp vụ DLM.
    Không tạo bảng mới — các trường được thêm vào res_partner (kế thừa Odoo native).

    A1 — dlm.customer  : is_dlm_customer=True
    A4 — dlm.supplier  : is_dlm_supplier=True
    Một partner có thể vừa là khách hàng vừa là NCC.
    """
    _inherit = 'res.partner'

    # ── Phân loại DLM ────────────────────────────────────────────────
    is_dlm_customer = fields.Boolean(
        string='Là khách hàng',
        default=False,
        help='Đánh dấu đây là khách hàng của Đại Linh',
    )
    is_dlm_supplier = fields.Boolean(
        string='Là NCC / Thầu phụ',
        default=False,
        help='Đánh dấu đây là nhà cung cấp hoặc thầu phụ của Đại Linh',
    )

    # ── A1: Loại khách hàng (Entity Proposal A1.customer_type) ───────
    customer_type = fields.Selection(
        selection=[
            ('individual', 'Cá nhân'),
            ('company', 'Doanh nghiệp'),
            ('dealer', 'Đại lý'),
        ],
        string='Loại khách hàng',
        default='individual',
        help='Phân loại phục vụ lọc báo cáo và chiết khấu tự động (D0)',
    )

    # ── Thông tin bổ sung ─────────────────────────────────────────────
    tax_code = fields.Char(
        string='Mã số thuế (MST)',
        help='Bắt buộc điền khi xuất hóa đơn VAT cho doanh nghiệp',
    )

    # ── Computed: tên hiển thị loại ───────────────────────────────────
    customer_type_label = fields.Char(
        string='Loại',
        compute='_compute_customer_type_label',
        store=False,
    )

    @api.depends('customer_type')
    def _compute_customer_type_label(self):
        mapping = {
            'individual': 'Cá nhân',
            'company': 'Doanh nghiệp',
            'dealer': 'Đại lý',
        }
        for rec in self:
            rec.customer_type_label = mapping.get(rec.customer_type, '')

    # ── Constraints ───────────────────────────────────────────────────
    @api.constrains('is_dlm_customer', 'customer_type')
    def _check_customer_type(self):
        for rec in self:
            if rec.is_dlm_customer and not rec.customer_type:
                raise models.ValidationError(
                    'Khách hàng DLM phải có Loại khách hàng.'
                )
