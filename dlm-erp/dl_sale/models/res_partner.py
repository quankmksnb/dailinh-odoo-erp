from odoo import models, fields, api


class ResPartner(models.Model):
    """
    Mở rộng res.partner cho nghiệp vụ DLM (theo TDS 4.0 §2.1 — dl.partner).
    Không tạo bảng mới — các trường được thêm vào res_partner (kế thừa Odoo native).

    partner_role: cột duy nhất quyết định 1 partner là Khách hàng hay NCC
    (theo TDS 4.0 — thay cho 2 cờ Boolean is_dlm_customer/is_dlm_supplier cũ).
    Lưu ý: khác thiết kế cũ, TDS không cho phép 1 partner vừa là Khách hàng
    vừa là NCC cùng lúc (enum đơn giá trị) — nếu nghiệp vụ thực sự cần 1 đối
    tác vừa mua vừa bán, cần tạo 2 bản ghi partner riêng.
    """
    _inherit = 'res.partner'

    # ── Phân loại DLM (TDS 4.0 §2.1) ───────────────────────────────────
    partner_role = fields.Selection([
        ('customer', 'Khách hàng'),
        ('supplier', 'NCC / Thầu phụ'),
    ], string='Vai trò')

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

    # MST dùng field native `vat` có sẵn trên res.partner (TDS 4.0 — Cap_Nhat_S04),
    # không tự chế field riêng nữa.

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
    @api.constrains('partner_role', 'customer_type')
    def _check_customer_type(self):
        for rec in self:
            if rec.partner_role == 'customer' and not rec.customer_type:
                raise models.ValidationError(
                    'Khách hàng DLM phải có Loại khách hàng.'
                )
