from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError

_SPLIT_THRESHOLD_KEY = 'dl_sale.split_order_threshold'
_SPLIT_THRESHOLD_DEFAULT = 20_000_000.0

_CUSTOMER_ROLES = ('customer', 'both')

# Ba nhóm khách hàng. Key phải trùng bản CUSTOMER_GROUP_SELECTION bên
# dl_config để bảng chiết khấu theo nhóm khớp với nhóm tự tính ở đây. Hai module
# không phụ thuộc nhau nên buộc phải giữ 2 bản — sửa bên này nhớ sửa bên kia.
CUSTOMER_GROUP_SELECTION = [
    ('new', 'Khách mới'),
    ('existing', 'Khách cũ'),
    ('loyal', 'Khách thân thiết'),
]

# Mốc doanh số để khách cũ tự lên "Khách thân thiết". CEO/Admin chỉnh ở màn
# Cấu hình báo giá. Mặc định 150 triệu; get_param đã có sẵn fallback nên không
# cần seed.
_LOYAL_THRESHOLD_KEY = 'dl_sale.loyal_customer_threshold'
_LOYAL_THRESHOLD_DEFAULT = 150_000_000.0


class ResPartnerQuoteStats(models.Model):
    """Gắn thống kê báo giá lên hồ sơ Khách hàng: số báo giá, tỷ lệ thắng,
    nhóm khách tự phân loại, cảnh báo tách đơn né duyệt."""
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
        string='Tỷ lệ thắng (%)',
        compute='_compute_dlm_quote_stats',
        help='Tỷ lệ Accepted / (Accepted + Rejected/Lost)',
    )
    dlm_open_quote_count = fields.Integer(
        string='Báo giá chưa đóng',
        compute='_compute_dlm_quote_stats',
        help='Số báo giá còn mở (Nháp / Đã gửi) — dùng để cảnh báo khi định vô hiệu hoá khách hàng',
    )
    dlm_recent_quote_count = fields.Integer(
        string='Báo giá trong 7 ngày',
        compute='_compute_dlm_quote_stats',
    )
    dlm_currency_id = fields.Many2one(
        'res.currency', string='Tiền tệ',
        compute='_compute_dlm_currency',
        help='Tiền tệ hiển thị số liệu báo giá (theo công ty)',
    )
    dlm_recent_quote_total = fields.Monetary(
        string='Tổng báo giá 7 ngày',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
        help='Tổng giá trị báo giá trong 7 ngày gần đây',
    )
    dlm_split_warning = fields.Boolean(
        string='Cảnh báo gộp đơn',
        compute='_compute_dlm_quote_stats',
        help='Bật khi ≥2 báo giá cho khách này trong 7 ngày VÀ tổng gộp vượt ngưỡng — nghi tách nhỏ để né phê duyệt',
    )
    dlm_split_threshold = fields.Monetary(
        string='Ngưỡng gộp đơn',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
    )

    # ── Nhóm khách tự phân loại (Mới / Cũ / Thân thiết) ──────────────
    # Mới (chưa thắng đơn nào) → Cũ (đã thắng ≥1) → Thân thiết (tổng đơn thắng
    # vượt ngưỡng). Lưu store để lọc/nhóm nhanh trên danh sách Khách hàng, tự
    # tính lại khi báo giá đổi trạng thái/giá trị.
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
        """Đếm các con số báo giá cho hồ sơ Khách hàng. Ai không có quyền đọc
        báo giá (vd Kỹ thuật) thì trả 0 hết, tránh vỡ khi mở hồ sơ khách."""
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

    # ── Tính nhóm khách ──────────────────────────────────────
    @api.depends('partner_role', 'dlm_quotation_ids.state',
                 'dlm_quotation_ids.amount_total')
    def _compute_dlm_customer_group(self):
        """Xếp nhóm cho khách. Chỉ đối tác là khách hàng mới có nhóm. Mốc
        "thắng đơn" = báo giá đã đồng ý hoặc đã lên đơn."""
        threshold = self._get_loyal_threshold()
        for rec in self:
            if rec.partner_role not in _CUSTOMER_ROLES:
                rec.dlm_customer_group = False
                continue
            # Đọc qua sudo để nhóm lưu ra giống nhau bất kể ai chạm phải việc
            # tính lại — kể cả người không có quyền xem giá (vd Kỹ thuật).
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
        """Màn Cấu hình báo giá gọi để nạp ngưỡng hiện tại + user có được sửa không."""
        return {
            'threshold': self._get_loyal_threshold(),
            'canEdit': self._can_edit_classification(),
        }

    @api.model
    def set_loyal_threshold(self, value):
        """Màn Cấu hình báo giá lưu ngưỡng mới, rồi phân loại lại TẤT CẢ khách.
        Ngưỡng không nằm trong @api.depends nên phải ép tính lại bằng tay."""
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
