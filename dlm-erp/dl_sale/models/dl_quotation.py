from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
    # Luồng: nháp → duyệt nội bộ → gửi khách → khách đồng ý → lên đơn bán hàng.
    # Tách "duyệt nội bộ" (approved) khỏi "khách đồng ý" (accepted): approved là
    # quyết định bên trong công ty (vượt ngưỡng…), accepted là khách chốt mua.
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('approved', 'Đã duyệt nội bộ'),
        ('sent', 'Đã gửi khách'),
        ('accepted', 'Khách đồng ý'),
        ('ordered', 'Đã lên đơn'),
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
    floor_amount = fields.Float(
        string='Tổng giá sàn', compute='_compute_amount', store=True,
        digits='Product Price', groups=_COST_GROUPS)

    component_ids = fields.One2many(
        'dl.quotation.price.component', 'quotation_id',
        string='Cấu phần giá (snapshot)')

    # --- Snapshot cấu hình thương mại đã dùng (để giải trình phê duyệt) ---
    target_markup = fields.Float(string='Lợi nhuận mục tiêu (%)', digits=(6, 2),
                                 readonly=True, groups=_COST_GROUPS)
    discount_default_rate = fields.Float(string='Chiết khấu mặc định (%)',
                                         digits=(6, 2), readonly=True)
    discount_max_rate = fields.Float(string='Chiết khấu tối đa (%)',
                                     digits=(6, 2), readonly=True)

    # --- Định tuyến phê duyệt (đặc tả §8) ---
    approval_required = fields.Boolean(string='Cần phê duyệt', readonly=True)
    approval_state = fields.Selection([
        ('not_required', 'Không cần duyệt'),
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Bị từ chối'),
    ], string='Trạng thái duyệt', default='not_required', readonly=True, tracking=True)
    approval_level = fields.Char(string='Cấp duyệt yêu cầu', readonly=True)
    approval_reasons = fields.Text(string='Lý do phải duyệt', readonly=True)
    approval_request_id = fields.Many2one(
        'dl.pricing.approval.request', string='Yêu cầu phê duyệt', readonly=True)
    # Quyền duyệt của user hiện tại trên yêu cầu đang treo — server tính
    # (_check_can_resolve), UI dựa vào để hiện nút Phê duyệt/Từ chối nhanh.
    # related_sudo=False BẮT BUỘC: can_resolve phụ thuộc ngữ cảnh user
    # (depends_context uid) — tính bằng sudo sẽ ghi cache dưới khóa su=True
    # trong khi request web đọc bằng su=False ⇒ "Compute method failed to
    # assign". Mọi vai trò đều có quyền đọc request nên không cần sudo.
    approval_can_resolve = fields.Boolean(
        string='Được duyệt yêu cầu này',
        related='approval_request_id.can_resolve', related_sudo=False)
    below_floor = fields.Boolean(string='Dưới giá sàn', readonly=True,
                                 groups=_COST_GROUPS)
    discount_above_default = fields.Boolean(string='Chiết khấu > mặc định', readonly=True)
    discount_above_max = fields.Boolean(string='Chiết khấu > tối đa', readonly=True)

    # Link ngược tới đơn bán hàng đã tạo (chiều sở hữu ở dl.sale.order.quotation_id).
    # Search-based để không nhân đôi nguồn sự thật.
    sale_order_id = fields.Many2one(
        'dl.sale.order', string='Đơn bán hàng', compute='_compute_sale_order_id')

    def _compute_sale_order_id(self):
        Order = self.env['dl.sale.order'].sudo()
        for rec in self:
            rec.sale_order_id = Order.search([
                ('quotation_id', '=', rec.id),
                ('state', '!=', 'cancelled'),
            ], limit=1)

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

    @api.depends('line_ids.price_subtotal', 'line_ids.total_cost',
                 'line_ids.floor_price', 'line_ids.qty',
                 'discount_pct', 'vat_pct')
    def _compute_amount(self):
        for rec in self:
            untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            # Toàn bộ dòng đều chịu chiết khấu (no_discount dành cho khoản phụ
            # phí ở phase sau).
            discount = untaxed * (rec.discount_pct or 0.0) / 100.0
            before_vat = untaxed - discount
            vat = before_vat * (rec.vat_pct or 0.0) / 100.0
            rec.amount_untaxed = untaxed
            rec.discount_amount = discount
            rec.amount_before_vat = before_vat
            rec.vat_amount = vat
            rec.amount_total = before_vat + vat
            # Giá thành / giá sàn = tổng theo dòng × số lượng (chỉ dòng gia công
            # có cost/floor; dòng thương mại = 0).
            total_cost = sum(line.total_cost * line.qty for line in rec.line_ids)
            rec.total_cost = total_cost
            rec.floor_amount = sum(line.floor_price * line.qty for line in rec.line_ids)
            rec.effective_markup = (
                (before_vat - total_cost) / total_cost * 100.0
                if total_cost else 0.0
            )

    # Field ảnh hưởng giá — đổi giá trị là phải đánh giá lại phê duyệt (mục 7).
    _REEVAL_TRIGGER_FIELDS = {'discount_pct', 'line_ids', 'partner_id'}

    def write(self, vals):
        # Khóa re-eval ở cấp dòng: sửa dòng qua form đi qua write header (lệnh
        # one2many) nên chỉ đánh giá lại MỘT lần ở đây.
        res = super(DlQuotation, self.with_context(dl_skip_line_reeval=True)).write(vals)
        if self._REEVAL_TRIGGER_FIELDS & set(vals):
            for rec in self:
                # Trạng thái cuối (ordered/cancelled/rejected) không đánh giá
                # lại — báo giá đã chốt hoặc đã đóng.
                if rec.state in ('draft', 'approved', 'sent'):
                    rec._reevaluate_approval()
        return res

    def _reevaluate_approval(self):
        """Đánh giá lại phê duyệt khi dữ liệu giá thay đổi (mục 7). Nếu phát
        sinh điều kiện duyệt mà báo giá đã qua bước duyệt nội bộ/gửi khách
        (chỉ xảy ra khi ghi thẳng qua RPC — UI đã khóa field ngoài Nháp) thì
        kéo về Nháp để đi lại luồng."""
        self.ensure_one()
        evaluation = self.env['dl.quotation.pricing.service'].reevaluate_quotation(self)
        if evaluation['required'] and self.state in ('approved', 'sent'):
            self.sudo().write({'state': 'draft'})
            self.message_post(body=_(
                "Dữ liệu giá thay đổi làm phát sinh điều kiện phê duyệt — "
                "báo giá quay về Nháp."))

    def _check_internal_approver(self):
        # Ngoài 3 vai trò cố định, chấp nhận op-group "Duyệt báo giá" — công
        # tắc mà màn Phân quyền tick cho vai trò khác (dl.rbac.operation).
        user = self.env.user
        if not self.env.su and not (
            user.has_group('dl_base.dl_group_ceo')
            or user.has_group('dl_base.dl_group_sales_manager')
            or user.has_group('dl_base.dl_group_admin')
            or user.has_group('dl_sale.dl_group_op_quote_approve')
        ):
            raise UserError(_(
                "Chỉ Giám đốc, Trưởng KD, Admin hoặc người được cấp thao tác "
                "'Duyệt báo giá' được duyệt nội bộ báo giá."))

    def action_approve(self):
        """Duyệt nội bộ — sẵn sàng gửi khách. Kiểm quyền server-side (nút chỉ
        ẩn ở UI) và không cho vượt mặt luồng phê duyệt theo ma trận (§8)."""
        self._check_internal_approver()
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Chỉ duyệt nội bộ báo giá ở trạng thái Nháp."))
            if rec.approval_state == 'pending':
                raise UserError(_(
                    "Báo giá đang chờ phê duyệt (%s) — chưa thể duyệt nội bộ."
                ) % (rec.approval_level or ''))
            if rec.approval_state == 'rejected':
                raise UserError(_(
                    "Yêu cầu phê duyệt đã bị từ chối — cần chỉnh sửa báo giá "
                    "để đánh giá lại trước khi duyệt."))
        # sudo: Trưởng KD được duyệt nội bộ nhưng ACL model chỉ cho đọc —
        # quyền đã kiểm ở trên.
        self.sudo().write({'state': 'approved'})

    def action_send(self):
        """Gửi báo giá cho khách hàng — chặn nếu đang chờ phê duyệt hoặc yêu
        cầu duyệt đã bị từ chối (§3 bước 7)."""
        for rec in self:
            if rec.approval_state == 'pending':
                raise UserError(_(
                    "Báo giá đang chờ phê duyệt (%s) — chưa thể gửi khách."
                ) % (rec.approval_level or ''))
            if rec.approval_state == 'rejected':
                raise UserError(_(
                    "Yêu cầu phê duyệt đã bị từ chối — cần chỉnh sửa báo giá "
                    "trước khi gửi khách."))
            if rec.state != 'approved':
                raise UserError(_("Chỉ gửi khách báo giá đã duyệt nội bộ."))
        self.state = 'sent'

    # ------------------------------------------------------------------
    # Hook được dl.pricing.approval.request gọi lại khi duyệt/từ chối (§8) —
    # báo giá là "target record" của yêu cầu.
    # ------------------------------------------------------------------
    def _on_approval_approved(self, request):
        self.ensure_one()
        # sudo: người duyệt (vd Trưởng KD) chỉ có quyền đọc trên báo giá —
        # quyền duyệt đã được _check_can_resolve của yêu cầu kiểm trước đó.
        vals = {'approval_state': 'approved'}
        # Gộp bước (quyết định 2026-07-24): người duyệt ma trận đã xác nhận thì
        # báo giá TỰ chuyển "Đã duyệt nội bộ" — không bắt duyệt 2 lần. Chỉ áp
        # dụng khi còn Nháp; trạng thái khác giữ nguyên.
        if self.state == 'draft':
            vals['state'] = 'approved'
        self.sudo().write(vals)
        if vals.get('state'):
            # sudo: _mail_post_access mặc định đòi quyền write mà người duyệt
            # (TrKD) chỉ có read trên báo giá; uid giữ nguyên nên tác giả vẫn
            # hiển thị đúng là người duyệt.
            self.sudo().message_post(body=_(
                "Yêu cầu phê duyệt đã được %s chấp thuận — báo giá tự chuyển "
                "sang Đã duyệt nội bộ, sẵn sàng gửi khách."
            ) % (request.resolved_by_id.name or _("người duyệt")))

    def _on_approval_rejected(self, request):
        self.ensure_one()
        self.sudo().write({'approval_state': 'rejected'})

    def action_open_approval_request(self):
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError(_("Báo giá này không có yêu cầu phê duyệt."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.pricing.approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_approval_approve(self):
        """Duyệt nhanh yêu cầu phê duyệt ngay trên form báo giá — quyền do
        _check_can_resolve của yêu cầu kiểm (nút chỉ ẩn/hiện ở UI)."""
        self.ensure_one()
        req = self.approval_request_id
        if not req or req.state != 'pending':
            raise UserError(_("Báo giá không có yêu cầu phê duyệt đang chờ."))
        req.action_approve()

    def action_approval_open_reject(self):
        """Mở yêu cầu duyệt dạng dialog để nhập lý do rồi Từ chối."""
        self.ensure_one()
        req = self.approval_request_id
        if not req or req.state != 'pending':
            raise UserError(_("Báo giá không có yêu cầu phê duyệt đang chờ."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Từ chối phê duyệt'),
            'res_model': 'dl.pricing.approval.request',
            'res_id': req.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_customer_accept(self):
        """Khách hàng đồng ý — sẵn sàng chuyển thành đơn bán hàng."""
        for rec in self:
            if rec.state != 'sent':
                raise UserError(_(
                    "Chỉ ghi nhận khách đồng ý trên báo giá đã gửi khách."))
        self.state = 'accepted'

    def action_reject(self):
        # Hủy yêu cầu phê duyệt còn treo — không để tồn đọng trong hàng chờ
        # của người duyệt khi báo giá đã bị từ chối.
        for rec in self:
            req = rec.approval_request_id
            if req and req.state == 'pending':
                req.sudo().action_cancel_on_change(note=_(
                    "Yêu cầu bị hủy do báo giá %s đã bị từ chối.") % rec.name)
        self.state = 'rejected'

    def action_reset_draft(self):
        self.state = 'draft'

    def action_create_sale_order(self):
        """Chuyển báo giá đã được khách đồng ý thành Đơn bán hàng.
        Snapshot dòng + số tiền sang đơn, khóa báo giá ở trạng thái 'ordered'."""
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError(_(
                "Chỉ tạo đơn bán hàng khi khách đã đồng ý báo giá."))
        existing = self.env['dl.sale.order'].search([
            ('quotation_id', '=', self.id),
            ('state', '!=', 'cancelled'),
        ], limit=1)
        if existing:
            # Đơn đã tồn tại (vd tạo từ phiên trước rồi báo giá bị reset):
            # vẫn phải khóa báo giá ở 'ordered' cho nhất quán.
            order = existing
            self.state = 'ordered'
        else:
            order = self.env['dl.sale.order'].create({
                'partner_id': self.partner_id.id,
                'quotation_id': self.id,
                'date_order': fields.Date.context_today(self),
                'currency_id': self.currency_id.id,
                'discount_pct': self.discount_pct,
                'vat_pct': self.vat_pct,
                'note': self.note,
                'state': 'confirmed',
                'line_ids': [(0, 0, {
                    'name': line.name,
                    'qty': line.qty,
                    'price_unit': line.price_unit,
                    'product_id': line.product_id.id,
                    'bom_id': line.bom_id.id,
                    'line_type': line.line_type,
                }) for line in self.line_ids],
            })
            self.state = 'ordered'
            self.message_post(body=_("Đã chuyển thành đơn bán hàng %s.") % order.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đơn bán hàng'),
            'res_model': 'dl.sale.order',
            'view_mode': 'form',
            'res_id': order.id,
            'target': 'current',
        }

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Báo giá này chưa có đơn bán hàng."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
        }


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

    # Field ảnh hưởng giá trên dòng — sửa/xóa thẳng dòng (RPC, không qua write
    # header) cũng phải đánh giá lại phê duyệt. Khi sửa qua form, header đã
    # re-eval và đặt cờ dl_skip_line_reeval để không chạy trùng.
    _LINE_REEVAL_FIELDS = {'price_unit', 'qty'}

    def write(self, vals):
        res = super().write(vals)
        if (self._LINE_REEVAL_FIELDS & set(vals)
                and not self.env.context.get('dl_skip_line_reeval')):
            for quo in self.mapped('quotation_id'):
                if quo.state in ('draft', 'approved', 'sent'):
                    quo._reevaluate_approval()
        return res

    def unlink(self):
        quotations = self.mapped('quotation_id')
        res = super().unlink()
        if not self.env.context.get('dl_skip_line_reeval'):
            for quo in quotations.exists():
                if quo.state in ('draft', 'approved', 'sent'):
                    quo._reevaluate_approval()
        return res
