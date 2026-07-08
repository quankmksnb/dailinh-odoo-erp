from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError


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

    # ── S03: Mã khách hàng (Customer ID) tự sinh KH-0001 ──────────────
    dlm_code = fields.Char(
        string='Mã KH',
        readonly=True,
        copy=False,
        index=True,
        help='Mã khách hàng tự sinh, duy nhất (VD: KH-0001)',
    )

    # ── S04: Nhà cung cấp ─────────────────────────────────────────────
    dlm_supplier_code = fields.Char(
        string='Mã NCC',
        readonly=True,
        copy=False,
        index=True,
        help='Mã nhà cung cấp tự sinh, duy nhất (VD: NCC-0001)',
    )
    dlm_supplier_group = fields.Selection(
        selection=[
            ('steel', 'Thép xây dựng'),
            ('paint', 'Sơn - mạ'),
            ('electric', 'Vật tư điện'),
            ('subcontract', 'Gia công ngoài'),
            ('other', 'Khác'),
        ],
        string='Nhóm vật tư cung cấp',
        help='Nhóm vật tư / dịch vụ mà NCC này cung cấp',
    )
    dlm_payment_days = fields.Integer(
        string='Công nợ (ngày)',
        help='Điều kiện thanh toán: số ngày công nợ cho phép',
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
    dlm_allow_dup_tax = fields.Boolean(
        string='Cho phép trùng MST (chi nhánh khác)',
        default=False,
        help='Tích khi đây là chi nhánh khác dùng chung MST — bỏ qua kiểm tra trùng (EX-05)',
    )

    # ── S03: Lịch sử báo giá theo khách ───────────────────────────────
    dlm_quotation_ids = fields.One2many(
        'dl.quotation', 'partner_id',
        string='Báo giá của khách',
    )
    dlm_quotation_count = fields.Integer(
        string='Số báo giá',
        compute='_compute_dlm_quote_stats',
    )
    dlm_win_rate = fields.Float(
        string='Win rate (%)',
        compute='_compute_dlm_quote_stats',
        help='Tỷ lệ Accepted / (Accepted + Rejected/Lost)',
    )
    dlm_split_warning = fields.Boolean(
        string='Cảnh báo gộp đơn',
        compute='_compute_dlm_quote_stats',
        help='≥2 báo giá cho KH này trong 7 ngày gần đây (chống chia nhỏ né duyệt)',
    )
    dlm_recent_quote_count = fields.Integer(
        string='BG trong 7 ngày',
        compute='_compute_dlm_quote_stats',
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

    @api.depends('dlm_quotation_ids', 'dlm_quotation_ids.state', 'dlm_quotation_ids.date_order')
    def _compute_dlm_quote_stats(self):
        today = fields.Date.context_today(self)
        window_start = today - timedelta(days=7)
        for rec in self:
            quotes = rec.dlm_quotation_ids
            rec.dlm_quotation_count = len(quotes)
            accepted = len(quotes.filtered(lambda q: q.state == 'approved'))
            lost = len(quotes.filtered(lambda q: q.state == 'rejected'))
            denom = accepted + lost
            rec.dlm_win_rate = (accepted / denom * 100.0) if denom else 0.0
            recent = quotes.filtered(
                lambda q: q.date_order and q.date_order >= window_start
            )
            rec.dlm_recent_quote_count = len(recent)
            rec.dlm_split_warning = len(recent) >= 2

    # ── Auto sinh mã KH / mã NCC khi tạo mới ──────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.is_dlm_customer and not rec.dlm_code:
                rec.dlm_code = self.env['ir.sequence'].next_by_code('dlm.customer') or '/'
            if rec.is_dlm_supplier and not rec.dlm_supplier_code:
                rec.dlm_supplier_code = self.env['ir.sequence'].next_by_code('dlm.supplier') or '/'
        return records

    # ── Constraints ───────────────────────────────────────────────────
    @api.constrains('is_dlm_customer', 'customer_type')
    def _check_customer_type(self):
        for rec in self:
            if rec.is_dlm_customer and not rec.customer_type:
                raise ValidationError(
                    'Khách hàng DLM phải có Loại khách hàng.'
                )

    @api.constrains('tax_code', 'is_dlm_customer', 'dlm_allow_dup_tax')
    def _check_unique_tax_code(self):
        """EX-05: chặn tạo KH trùng MST; cho phép ghi đè nếu là chi nhánh khác."""
        for rec in self:
            if not rec.is_dlm_customer or not rec.tax_code or rec.dlm_allow_dup_tax:
                continue
            dup = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('is_dlm_customer', '=', True),
                ('tax_code', '=', rec.tax_code),
            ], limit=1)
            if dup:
                ref = (' — ' + dup.dlm_code) if dup.dlm_code else ''
                raise ValidationError(
                    "MST '%s' đã tồn tại trong hệ thống (KH: %s%s).\n"
                    "Nếu đây là chi nhánh khác dùng chung MST, hãy tích "
                    "'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do."
                    % (rec.tax_code, dup.name, ref)
                )
