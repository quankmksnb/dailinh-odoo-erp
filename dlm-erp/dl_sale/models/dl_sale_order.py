from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DlSaleOrder(models.Model):
    """Đơn bán hàng — sinh ra từ báo giá khi khách hàng đồng ý (§ luồng bán hàng).
    Đây là bản chốt thương mại: dòng + số tiền được snapshot từ báo giá nguồn.
    Lệnh sản xuất / yêu cầu mua vật tư là phase sau (chưa làm ở đây)."""

    _name = 'dl.sale.order'
    _description = 'Đơn bán hàng'
    _order = 'date_order desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Số đơn', required=True, copy=False,
                       readonly=True, default='New')
    partner_id = fields.Many2one(
        'res.partner', string='Khách hàng', required=True,
        domain=[('partner_role', 'in', ('customer', 'both'))], tracking=True)
    quotation_id = fields.Many2one(
        'dl.quotation', string='Báo giá nguồn', readonly=True,
        ondelete='restrict', index=True, copy=False,
        help='Báo giá đã được khách đồng ý và chuyển thành đơn này.')
    date_order = fields.Date(string='Ngày lên đơn', required=True,
                             default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('done', 'Hoàn tất'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='draft', tracking=True, copy=False)
    note = fields.Text(string='Ghi chú')
    currency_id = fields.Many2one(
        'res.currency', string='Tiền tệ',
        default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Công ty', readonly=True,
        default=lambda self: self.env.company)
    line_ids = fields.One2many('dl.sale.order.line', 'order_id', string='Chi tiết')

    # --- Các lớp tiền (snapshot theo báo giá nguồn, đặc tả §7.3) ---
    discount_pct = fields.Float(string='Chiết khấu (%)', digits=(5, 2), tracking=True)
    vat_pct = fields.Float(string='VAT (%)', digits=(5, 2), tracking=True)
    amount_untaxed = fields.Float(
        string='Giá trước chiết khấu', compute='_compute_amount', store=True,
        digits='Product Price')
    discount_amount = fields.Float(
        string='Chiết khấu', compute='_compute_amount', store=True,
        digits='Product Price')
    amount_before_vat = fields.Float(
        string='Sau chiết khấu, trước VAT', compute='_compute_amount', store=True,
        digits='Product Price')
    vat_amount = fields.Float(
        string='Tiền VAT', compute='_compute_amount', store=True,
        digits='Product Price')
    amount_total = fields.Float(
        string='Tổng thanh toán', compute='_compute_amount', store=True,
        digits='Product Price')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dl.sale.order') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.price_subtotal', 'line_ids.qty',
                 'discount_pct', 'vat_pct')
    def _compute_amount(self):
        for rec in self:
            untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            discount = untaxed * (rec.discount_pct or 0.0) / 100.0
            before_vat = untaxed - discount
            vat = before_vat * (rec.vat_pct or 0.0) / 100.0
            rec.amount_untaxed = untaxed
            rec.discount_amount = discount
            rec.amount_before_vat = before_vat
            rec.vat_amount = vat
            rec.amount_total = before_vat + vat

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_open_quotation(self):
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_('Đơn này không có báo giá nguồn.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.quotation',
            'view_mode': 'form',
            'res_id': self.quotation_id.id,
            'target': 'current',
        }


class DlSaleOrderLine(models.Model):
    _name = 'dl.sale.order.line'
    _description = 'Chi tiết đơn bán hàng'

    order_id = fields.Many2one('dl.sale.order', string='Đơn bán hàng',
                               ondelete='cascade', required=True)
    name = fields.Char(string='Mô tả', required=True)
    qty = fields.Float(string='SL', default=1.0)
    price_unit = fields.Float(string='Đơn giá', digits='Product Price')
    price_subtotal = fields.Float(string='Thành tiền', compute='_compute_subtotal',
                                  store=True, digits='Product Price')
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    line_type = fields.Selection([
        ('trading', 'Thương mại'),
        ('manufactured', 'Gia công'),
    ], string='Loại dòng', default='trading', readonly=True)

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
