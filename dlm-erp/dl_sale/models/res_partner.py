import re
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

# Regex nghiệp vụ (TDS §3.1 A1) — SĐT Việt Nam & email.
_PHONE_RE = re.compile(r'^(0|\+84)[0-9]{9,10}$')
_EMAIL_RE = re.compile(r'^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$')
_SPLIT_THRESHOLD_KEY = 'dl_sale.split_order_threshold'
_SPLIT_THRESHOLD_DEFAULT = 20_000_000.0


class ResPartner(models.Model):
    """
    Mở rộng res.partner cho nghiệp vụ DLM (TDS A1 — dl.partner).
    Không tạo bảng mới — field bổ sung nằm trong bảng res_partner.

    Vai trò đối tác (partner_role) là NGUỒN SỰ THẬT theo TDS §3.3:
        customer / supplier / both
    Hai cờ is_dlm_customer / is_dlm_supplier được GIỮ LẠI dưới dạng field
    computed(store)+inverse suy ra từ partner_role — đảm bảo tương thích
    ngược cho S04 (NCC) và module dlm_material vốn lọc theo 2 cờ này.
    """
    _inherit = 'res.partner'

    partner_role = fields.Selection(
        selection=[
            ('customer', 'Khách hàng'),
            ('supplier', 'Nhà cung cấp'),
            ('both', 'Cả hai'),
        ],
        string='Vai trò đối tác',
        index=True,
        tracking=True,
        help='Phân loại đối tác theo TDS: Khách hàng / Nhà cung cấp / Cả hai',
    )

    is_dlm_customer = fields.Boolean(
        string='Là khách hàng',
        compute='_compute_role_flags',
        inverse='_inverse_role_flags',
        store=True,
        help='Đánh dấu đây là khách hàng của Đại Linh (suy ra từ Vai trò đối tác)',
    )
    is_dlm_supplier = fields.Boolean(
        string='Là NCC / Thầu phụ',
        compute='_compute_role_flags',
        inverse='_inverse_role_flags',
        store=True,
        help='Đánh dấu đây là nhà cung cấp / thầu phụ (suy ra từ Vai trò đối tác)',
    )
    dlm_code = fields.Char(
        string='Mã KH',
        readonly=True,
        copy=False,
        index=True,
        help='Mã khách hàng tự sinh, duy nhất (VD: KH-0001)',
    )
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
    partner_type = fields.Selection(
        selection=[
            ('individual', 'Cá nhân'),
            ('company', 'Doanh nghiệp'),
            ('dealer', 'Đại lý'),
        ],
        string='Loại khách hàng',
        default='individual',
        help='Phân loại phục vụ lọc báo cáo và chiết khấu tự động (D6)',
    )

    tax_code = fields.Char(
        string='Mã số thuế (MST)',
        help='Bắt buộc điền khi xuất hóa đơn VAT cho doanh nghiệp',
    )
    dlm_allow_dup_tax = fields.Boolean(
        string='Cho phép trùng MST (chi nhánh khác)',
        default=False,
        help='Tích khi đây là chi nhánh khác dùng chung MST — bỏ qua kiểm tra trùng (EX-05)',
    )

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
    dlm_open_quote_count = fields.Integer(
        string='BG chưa đóng',
        compute='_compute_dlm_quote_stats',
        help='Số báo giá còn mở (Nháp / Đã gửi) — dùng cảnh báo khi vô hiệu hóa KH (EX-30)',
    )
    dlm_recent_quote_count = fields.Integer(
        string='BG trong 7 ngày',
        compute='_compute_dlm_quote_stats',
    )
    dlm_currency_id = fields.Many2one(
        'res.currency', string='Tiền tệ',
        compute='_compute_dlm_currency',
        help='Tiền tệ hiển thị số liệu báo giá (theo công ty)',
    )
    dlm_recent_quote_total = fields.Monetary(
        string='Tổng BG 7 ngày',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
        help='Tổng giá trị báo giá trong 7 ngày gần đây (EX-42)',
    )
    dlm_split_warning = fields.Boolean(
        string='Cảnh báo gộp đơn',
        compute='_compute_dlm_quote_stats',
        help='≥2 báo giá cho KH này trong 7 ngày VÀ tổng gộp vượt ngưỡng auto '
             '(chống chia nhỏ né duyệt — EX-42)',
    )
    dlm_split_threshold = fields.Monetary(
        string='Ngưỡng gộp đơn',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
    )
    partner_type_label = fields.Char(
        string='Loại',
        compute='_compute_partner_type_label',
        store=False,
    )
    dlm_status_label = fields.Char(
        string='Trạng thái',
        compute='_compute_dlm_status_label',
        store=False,
    )

    @api.depends('active')
    def _compute_dlm_status_label(self):
        for rec in self:
            rec.dlm_status_label = 'Đang hợp tác' if rec.active else 'Ngừng hợp tác'

    _DLM_AVA_PALETTE = [
        ('#fde2e4', '#b23a48'), ('#dbe7ff', '#1e4fa3'), ('#e3f6e8', '#1b7a3d'),
        ('#fff1cc', '#8a5a00'), ('#ece0fb', '#5b3fa0'), ('#ffe1f0', '#a3226e'),
        ('#d9f2f4', '#0f6b73'),
    ]

    dlm_has_photo = fields.Boolean(
        string='Có ảnh đại diện',
        compute='_compute_dlm_has_photo', store=True,
    )
    dlm_initial = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_bg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_fg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)

    @api.depends('image_128')
    def _compute_dlm_has_photo(self):
        for rec in self:
            rec.dlm_has_photo = bool(rec.image_128)

    @api.depends('name')
    def _compute_dlm_avatar_letter(self):
        palette = self._DLM_AVA_PALETTE
        for rec in self:
            name = (rec.name or '').strip()
            rec.dlm_initial = name[0].upper() if name else '?'
            h = 0
            for ch in name:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            bg, fg = palette[h % len(palette)]
            rec.dlm_avatar_bg = bg
            rec.dlm_avatar_fg = fg

    @api.depends('partner_role')
    def _compute_role_flags(self):
        for rec in self:
            rec.is_dlm_customer = rec.partner_role in ('customer', 'both')
            rec.is_dlm_supplier = rec.partner_role in ('supplier', 'both')

    def _inverse_role_flags(self):
        """Giữ tương thích ngược: khi module khác ghi is_dlm_customer/
        is_dlm_supplier (S04, dlm_material), suy ngược ra partner_role."""
        for rec in self:
            rec.partner_role = self._compose_role(
                rec.is_dlm_customer, rec.is_dlm_supplier)

    @staticmethod
    def _compose_role(is_customer, is_supplier):
        if is_customer and is_supplier:
            return 'both'
        if is_customer:
            return 'customer'
        if is_supplier:
            return 'supplier'
        return False

    def _compute_dlm_currency(self):
        currency = self.env.company.currency_id
        for rec in self:
            rec.dlm_currency_id = currency

    @api.depends('partner_type')
    def _compute_partner_type_label(self):
        mapping = dict(self._fields['partner_type'].selection)
        for rec in self:
            rec.partner_type_label = mapping.get(rec.partner_type, '')

    @api.depends('dlm_quotation_ids', 'dlm_quotation_ids.state',
                 'dlm_quotation_ids.date_order', 'dlm_quotation_ids.amount_total')
    def _compute_dlm_quote_stats(self):
        today = fields.Date.context_today(self)
        window_start = today - timedelta(days=7)
        threshold = self._get_split_threshold()
        for rec in self:
            quotes = rec.dlm_quotation_ids
            rec.dlm_quotation_count = len(quotes)
            accepted = len(quotes.filtered(lambda q: q.state == 'approved'))
            lost = len(quotes.filtered(lambda q: q.state == 'rejected'))
            denom = accepted + lost
            rec.dlm_win_rate = (accepted / denom * 100.0) if denom else 0.0
            rec.dlm_open_quote_count = len(
                quotes.filtered(lambda q: q.state in ('draft', 'sent')))
            recent = quotes.filtered(
                lambda q: q.date_order and q.date_order >= window_start)
            rec.dlm_recent_quote_count = len(recent)
            rec.dlm_recent_quote_total = sum(recent.mapped('amount_total'))
            rec.dlm_split_threshold = threshold
            # Cảnh báo khi ≥2 BG/7 ngày VÀ tổng gộp vượt ngưỡng auto.
            rec.dlm_split_warning = (
                len(recent) >= 2 and rec.dlm_recent_quote_total > threshold)

    def _get_split_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            _SPLIT_THRESHOLD_KEY, _SPLIT_THRESHOLD_DEFAULT)
        try:
            return float(param)
        except (TypeError, ValueError):
            return _SPLIT_THRESHOLD_DEFAULT

    # Auto sinh mã KH / mã NCC khi tạo mới
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.is_dlm_customer and not rec.dlm_code:
                rec.dlm_code = self.env['ir.sequence'].next_by_code('dlm.customer') or '/'
            if rec.is_dlm_supplier and not rec.dlm_supplier_code:
                rec.dlm_supplier_code = self.env['ir.sequence'].next_by_code('dlm.supplier') or '/'
        return records

    # Chỉ Trưởng KD / Admin được vô hiệu hóa khách hàng 
    def write(self, vals):
        if 'active' in vals and not vals['active'] and not self.env.su:
            is_manager = (
                self.env.user.has_group('dl_base.dl_group_sales_manager')
                or self.env.user.has_group('dl_base.dl_group_admin'))
            if not is_manager and any(r.is_dlm_customer for r in self):
                raise AccessError(_(
                    'Chỉ Trưởng phòng Kinh doanh hoặc Admin mới được vô hiệu '
                    'hóa khách hàng. Sales không có quyền này.'))
        return super().write(vals)

    @api.constrains('is_dlm_customer', 'partner_type')
    def _check_partner_type(self):
        for rec in self:
            if rec.is_dlm_customer and not rec.partner_type:
                raise ValidationError(_('Khách hàng DLM phải có Loại khách hàng.'))

    @api.constrains('is_dlm_customer', 'partner_type', 'tax_code')
    def _check_company_tax_code(self):
        """MST bắt buộc với khách doanh nghiệp (dùng trên PDF báo giá S09)."""
        for rec in self:
            if rec.is_dlm_customer and rec.partner_type == 'company' \
                    and not (rec.tax_code and rec.tax_code.strip()):
                raise ValidationError(_(
                    'Khách hàng Doanh nghiệp bắt buộc phải có Mã số thuế (MST).'))

    @api.constrains('is_dlm_customer', 'phone', 'mobile')
    def _check_phone_format(self):
        """Validate SĐT Việt Nam (TDS A1): ^(0|+84)[0-9]{9,10}$."""
        for rec in self:
            if not rec.is_dlm_customer:
                continue
            for label, value in (('Điện thoại', rec.phone), ('Di động', rec.mobile)):
                if not value:
                    continue
                cleaned = re.sub(r'[\s.\-]', '', value)
                if not _PHONE_RE.match(cleaned):
                    raise ValidationError(_(
                        "%s '%s' không hợp lệ. Số điện thoại Việt Nam phải bắt "
                        "đầu bằng 0 hoặc +84 và gồm 10–11 chữ số."
                    ) % (label, value))

    @api.constrains('is_dlm_customer', 'email')
    def _check_email_format(self):
        for rec in self:
            if rec.is_dlm_customer and rec.email and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_(
                    "Email '%s' không hợp lệ.") % rec.email)

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
                raise ValidationError(_(
                    "MST '%s' đã tồn tại trong hệ thống (KH: %s%s).\n"
                    "Nếu đây là chi nhánh khác dùng chung MST, hãy tích "
                    "'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do."
                ) % (rec.tax_code, dup.name, ref))
