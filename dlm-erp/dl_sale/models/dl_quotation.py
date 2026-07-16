from odoo import models, fields, api

# Nhóm được xem cấu phần giá thành trên dòng báo giá (giống BOM): Kế toán,
# Trưởng KD, CEO, Admin. Sales (BA) chỉ thấy giá bán/chiết khấu, không thấy chi
# phí gốc.
_COST_GROUPS = (
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
    "dl_base.dl_group_accountant,"
    "dl_base.dl_group_sales_manager"
)


class DlQuotation(models.Model):
    _name = 'dl.quotation'
    _description = 'Báo giá'
    _order = 'date_order desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Số báo giá', required=True, copy=False,
                       readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Khách hàng', required=True,
                                 domain=[('partner_role', 'in', ('customer', 'both'))],
                                 tracking=True)
    date_order = fields.Date(string='Ngày báo giá', required=True,
                             default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('sent', 'Đã gửi'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='draft', tracking=True)
    note = fields.Text(string='Ghi chú')
    line_ids = fields.One2many('dl.quotation.line', 'quotation_id', string='Chi tiết')
    currency_id = fields.Many2one('res.currency', string='Tiền tệ',
                                  default=lambda self: self.env.company.currency_id)

    # --- Truy vết & ngữ cảnh tính giá (đặc tả §17.2) ---
    quotation_request_id = fields.Many2one(
        'dl.quotation.request', string='Yêu cầu báo giá (RFQ)',
        ondelete='restrict', index=True, copy=False, readonly=True,
        help='RFQ nguồn đã tạo ra báo giá này.')
    company_id = fields.Many2one(
        'res.company', string='Công ty', readonly=True,
        default=lambda self: self.env.company)
    pricing_date = fields.Date(
        string='Ngày tính giá', readonly=True,
        help='Ngày khóa logic tính giá — chọn đúng rule/bảng giá hiệu lực.')

    # --- Các lớp tiền (đặc tả §7.3) ---
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

    # --- Đánh giá thương mại nội bộ (ẩn với Sales) ---
    total_cost = fields.Float(
        string='Tổng giá thành', compute='_compute_amount', store=True,
        digits='Product Price', groups=_COST_GROUPS)
    effective_markup = fields.Float(
        string='Markup thực (%)', compute='_compute_amount', store=True,
        digits=(16, 2), groups=_COST_GROUPS)

    component_ids = fields.One2many(
        'dl.quotation.price.component', 'quotation_id',
        string='Cấu phần giá (snapshot)')

    def init(self):
        """Partial unique index (Decision C7 + review #1): mỗi RFQ chỉ có tối đa
        một báo giá CHƯA hủy. Không dùng unique tuyệt đối để P2 còn tạo được
        revision (hủy bản cũ rồi tạo bản mới) mà không phải drop constraint.
        Odoo helper không hỗ trợ đồng thời UNIQUE + WHERE nên dùng SQL trực tiếp
        (tên bảng là hằng an toàn)."""
        self._cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS dl_quotation_reqid_active_uniq
            ON %s (quotation_request_id)
            WHERE quotation_request_id IS NOT NULL AND state != 'cancelled'
            """ % self._table
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dl.quotation') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.price_subtotal', 'line_ids.total_cost', 'line_ids.qty',
                 'discount_pct', 'vat_pct')
    def _compute_amount(self):
        for rec in self:
            untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            # P0: toàn bộ dòng đều chịu chiết khấu (no_discount là P1).
            discount = untaxed * (rec.discount_pct or 0.0) / 100.0
            before_vat = untaxed - discount
            vat = before_vat * (rec.vat_pct or 0.0) / 100.0
            rec.amount_untaxed = untaxed
            rec.discount_amount = discount
            rec.amount_before_vat = before_vat
            rec.vat_amount = vat
            rec.amount_total = before_vat + vat
            # Giá thành = tổng total_cost từng dòng × số lượng (chỉ dòng gia công
            # có cost; dòng thương mại total_cost = 0).
            total_cost = sum(line.total_cost * line.qty for line in rec.line_ids)
            rec.total_cost = total_cost
            rec.effective_markup = (
                (before_vat - total_cost) / total_cost * 100.0
                if total_cost else 0.0
            )

    def action_send(self):
        self.state = 'sent'

    def action_approve(self):
        self.state = 'approved'

    def action_reject(self):
        self.state = 'rejected'

    def action_reset_draft(self):
        self.state = 'draft'


class DlQuotationLine(models.Model):
    _name = 'dl.quotation.line'
    _description = 'Chi tiết báo giá'

    quotation_id = fields.Many2one('dl.quotation', string='Báo giá', ondelete='cascade')
    name = fields.Char(string='Mô tả', required=True)
    qty = fields.Float(string='SL', default=1.0)
    price_unit = fields.Float(string='Đơn giá', digits='Product Price')
    price_subtotal = fields.Float(string='Thành tiền', compute='_compute_subtotal',
                                  store=True, digits='Product Price')

    # --- Truy vết & phân loại (đặc tả §17.2) ---
    rfq_line_id = fields.Many2one('dl.quotation.request.line', string='Dòng RFQ',
                                  ondelete='set null', readonly=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    bom_id = fields.Many2one('dl.bom', string='BOM', readonly=True)
    line_type = fields.Selection([
        ('trading', 'Thương mại'),
        ('manufactured', 'Gia công'),
    ], string='Loại dòng', default='trading', readonly=True)

    # --- Phân tích chi phí nội bộ (ẩn với Sales) ---
    base_price = fields.Float(string='Giá nền', digits='Product Price',
                              readonly=True, groups=_COST_GROUPS)
    material_cost = fields.Float(string='Chi phí vật tư/đv', digits='Product Price',
                                 readonly=True, groups=_COST_GROUPS)
    total_cost = fields.Float(string='Giá thành/đv', digits='Product Price',
                              readonly=True, groups=_COST_GROUPS)
    floor_price = fields.Float(string='Giá sàn/đv', digits='Product Price',
                               readonly=True, groups=_COST_GROUPS)

    component_ids = fields.One2many('dl.quotation.price.component', 'quotation_line_id',
                                    string='Cấu phần giá')

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
