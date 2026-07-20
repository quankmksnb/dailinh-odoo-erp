from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError

_SPLIT_THRESHOLD_KEY = 'dl_sale.split_order_threshold'
_SPLIT_THRESHOLD_DEFAULT = 20_000_000.0

_CUSTOMER_ROLES = ('customer', 'both')

# Phân loại nhóm khách hàng — đồng bộ key với CUSTOMER_GROUP_SELECTION ở
# dl_config/models/pricing_commercial.py (2 module không phụ thuộc nhau nên giữ
# 2 bản). Chiết khấu theo nhóm ở dl_config khớp key với nhóm auto-tính tại đây.
CUSTOMER_GROUP_SELECTION = [
    ('new', 'Khách mới'),
    ('existing', 'Khách cũ'),
    ('loyal', 'Khách thân thiết'),
]

# Ngưỡng doanh số để khách cũ tự lên "Khách thân thiết". CEO/Admin sửa được ở
# màn Cấu hình báo giá (tab Lợi nhuận & chiết khấu). Lưu ir.config_parameter —
# mặc định 150 triệu; không cần seed vì get_param đã có fallback.
_LOYAL_THRESHOLD_KEY = 'dl_sale.loyal_customer_threshold'
_LOYAL_THRESHOLD_DEFAULT = 150_000_000.0


class ResPartnerQuoteStats(models.Model):
    """Mở rộng res.partner với thống kê báo giá — phụ thuộc dl.quotation (dl_sale)."""
    _inherit = 'res.partner'

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
        help='≥2 báo giá cho KH này trong 7 ngày VÀ tổng gộp vượt ngưỡng auto (EX-42)',
    )
    dlm_split_threshold = fields.Monetary(
        string='Ngưỡng gộp đơn',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
    )

    # ── Nhóm khách hàng tự động (Khách mới / cũ / thân thiết) ──────────────
    # Mới khi tạo (chưa có báo giá duyệt) → Cũ khi đã có ≥1 báo giá duyệt →
    # Thân thiết khi tổng giá trị báo giá đã duyệt vượt ngưỡng cấu hình.
    # Field lưu (store) để lọc/nhóm/hiển thị nhanh trên danh sách khách hàng;
    # tính lại tự động khi báo giá đổi trạng thái/giá trị.
    dlm_customer_group = fields.Selection(
        CUSTOMER_GROUP_SELECTION, string='Nhóm khách hàng',
        compute='_compute_dlm_customer_group', store=True,
        help='Tự động: Khách mới (chưa có báo giá duyệt) → Khách cũ (đã có báo '
             'giá duyệt) → Khách thân thiết (tổng báo giá duyệt vượt ngưỡng cấu hình).',
    )

    def _compute_dlm_currency(self):
        currency = self.env.company.currency_id
        for rec in self:
            rec.dlm_currency_id = currency

    @api.depends('dlm_quotation_ids', 'dlm_quotation_ids.state',
                 'dlm_quotation_ids.date_order', 'dlm_quotation_ids.amount_total')
    def _compute_dlm_quote_stats(self):
        today = fields.Date.context_today(self)
        window_start = today - timedelta(days=7)
        threshold = self._get_split_threshold()
        can_read_quote = self.env['dl.quotation'].check_access_rights(
            'read', raise_exception=False)
        if not can_read_quote:
            for rec in self:
                rec.dlm_quotation_count = 0
                rec.dlm_win_rate = 0.0
                rec.dlm_open_quote_count = 0
                rec.dlm_recent_quote_count = 0
                rec.dlm_recent_quote_total = 0.0
                rec.dlm_split_threshold = threshold
                rec.dlm_split_warning = False
            return
        for rec in self:
            quotes = rec.dlm_quotation_ids
            rec.dlm_quotation_count = len(quotes)
            accepted = len(quotes.filtered(lambda q: q.state in ('accepted', 'ordered')))
            lost = len(quotes.filtered(lambda q: q.state == 'rejected'))
            denom = accepted + lost
            rec.dlm_win_rate = (accepted / denom * 100.0) if denom else 0.0
            rec.dlm_open_quote_count = len(
                quotes.filtered(lambda q: q.state in ('draft', 'approved', 'sent')))
            recent = quotes.filtered(
                lambda q: q.date_order and q.date_order >= window_start)
            rec.dlm_recent_quote_count = len(recent)
            rec.dlm_recent_quote_total = sum(recent.mapped('amount_total'))
            rec.dlm_split_threshold = threshold
            rec.dlm_split_warning = (
                len(recent) >= 2 and rec.dlm_recent_quote_total > threshold)

    def _get_split_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            _SPLIT_THRESHOLD_KEY, _SPLIT_THRESHOLD_DEFAULT)
        try:
            return float(param)
        except (TypeError, ValueError):
            return _SPLIT_THRESHOLD_DEFAULT

    # ── Phân loại khách hàng tự động ──────────────────────────────────────
    @api.depends('partner_role', 'dlm_quotation_ids.state',
                 'dlm_quotation_ids.amount_total')
    def _compute_dlm_customer_group(self):
        """Chỉ khách hàng mới có nhóm. 'Đơn hàng thành công' = báo giá khách đã
        đồng ý / đã lên đơn (accepted/ordered) — mốc thắng đơn thực tế."""
        threshold = self._get_loyal_threshold()
        for rec in self:
            if rec.partner_role not in _CUSTOMER_ROLES:
                rec.dlm_customer_group = False
                continue
            # Đọc qua sudo để giá trị lưu độc lập với quyền đọc báo giá của
            # người vô tình kích hoạt tính lại (VD Kỹ thuật không thấy giá).
            won = rec.sudo().dlm_quotation_ids.filtered(
                lambda q: q.state in ('accepted', 'ordered'))
            if not won:
                rec.dlm_customer_group = 'new'
            elif sum(won.mapped('amount_total')) > threshold:
                rec.dlm_customer_group = 'loyal'
            else:
                rec.dlm_customer_group = 'existing'

    @api.model
    def _get_loyal_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            _LOYAL_THRESHOLD_KEY, _LOYAL_THRESHOLD_DEFAULT)
        try:
            return float(param)
        except (TypeError, ValueError):
            return _LOYAL_THRESHOLD_DEFAULT

    def _can_edit_classification(self):
        u = self.env.user
        return u.has_group('dl_base.dl_group_admin') or \
            u.has_group('dl_base.dl_group_ceo')

    @api.model
    def get_customer_classification_config(self):
        """OWL màn Cấu hình báo giá gọi để nạp ngưỡng + quyền sửa."""
        return {
            'threshold': self._get_loyal_threshold(),
            'canEdit': self._can_edit_classification(),
        }

    @api.model
    def set_loyal_threshold(self, value):
        """Lưu ngưỡng lên Khách thân thiết rồi phân loại lại toàn bộ khách hàng.
        Ngưỡng nằm ngoài @api.depends nên phải tính lại thủ công."""
        if not self._can_edit_classification():
            raise AccessError(_(
                'Chỉ Admin/CEO được sửa ngưỡng phân loại khách hàng.'))
        try:
            val = float(value)
        except (TypeError, ValueError):
            raise ValidationError(_('Ngưỡng doanh số không hợp lệ.'))
        if val < 0:
            raise ValidationError(_('Ngưỡng doanh số không được âm.'))
        self.env['ir.config_parameter'].sudo().set_param(
            _LOYAL_THRESHOLD_KEY, val)
        partners = self.sudo().search([('partner_role', 'in', _CUSTOMER_ROLES)])
        partners._compute_dlm_customer_group()
        partners.flush_recordset(['dlm_customer_group'])
        return self._get_loyal_threshold()
