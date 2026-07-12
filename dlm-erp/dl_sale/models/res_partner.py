from datetime import timedelta

from odoo import models, fields, api

_SPLIT_THRESHOLD_KEY = 'dl_sale.split_order_threshold'
_SPLIT_THRESHOLD_DEFAULT = 20_000_000.0


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
            rec.dlm_split_warning = (
                len(recent) >= 2 and rec.dlm_recent_quote_total > threshold)

    def _get_split_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            _SPLIT_THRESHOLD_KEY, _SPLIT_THRESHOLD_DEFAULT)
        try:
            return float(param)
        except (TypeError, ValueError):
            return _SPLIT_THRESHOLD_DEFAULT
