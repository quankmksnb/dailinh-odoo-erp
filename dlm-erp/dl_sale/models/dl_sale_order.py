from odoo import models, fields, api, _
from markupsafe import escape

from odoo.exceptions import AccessError, UserError, ValidationError


class DlSaleOrder(models.Model):
    """Đơn bán hàng — bản chốt thương mại, sinh ra khi bấm "Tạo đơn bán hàng"
    trên báo giá khách đã đồng ý. Dòng và số tiền chép nguyên từ báo giá nguồn.
    Lệnh sản xuất / mua vật tư là việc của phase sau, chưa làm ở đây."""

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
    reset_draft_reason = fields.Text(
        string='Lý do đưa về nháp gần nhất', readonly=True,
        copy=False, tracking=True)
    reset_draft_by = fields.Many2one(
        'res.users', string='Người đưa về nháp', readonly=True, copy=False)
    reset_draft_at = fields.Datetime(
        string='Thời điểm đưa về nháp', readonly=True, copy=False)
    currency_id = fields.Many2one(
        'res.currency', string='Tiền tệ',
        default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Công ty', readonly=True,
        default=lambda self: self.env.company)
    line_ids = fields.One2many('dl.sale.order.line', 'order_id', string='Chi tiết')

    # --- Các lớp tiền ở khối tổng cuối form Đơn (chép từ báo giá nguồn) ---
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
        """Cấp số đơn tự động. Báo giá tạo đơn thẳng ở trạng thái 'confirmed'
        (không qua nút Xác nhận) nên phải chuẩn hoá SP gia công ngay tại đây."""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dl.sale.order') or 'New'
        orders = super().create(vals_list)
        # Đơn sinh thẳng ở 'confirmed' vẫn phải nâng cấp SP gia công còn Nháp.
        orders.filtered(lambda o: o.state == 'confirmed')._promote_draft_products()
        return orders

    def write(self, vals):
        """Khoá cứng khách hàng của đơn đã gắn báo giá / đã rời Nháp.

        Đơn là bản chốt của một báo giá cho đúng một khách; đổi khách sẽ làm
        lệch truy vết đơn↔báo giá và sai giá/chiết khấu (tính theo nhóm khách
        gốc). Form đã để readonly, chặn thêm ở đây để bịt cả đường API/import.
        Ghi lại đúng khách cũ thì cho qua."""
        if 'partner_id' in vals:
            for order in self:
                if order.partner_id.id == vals['partner_id']:
                    continue
                if order.quotation_id or order.state != 'draft':
                    raise UserError(_(
                        'Không thể đổi khách hàng của đơn "%s": đơn đã chốt từ '
                        'báo giá nguồn (hoặc không còn ở trạng thái Nháp). '
                        'Nếu cần đổi khách, hãy tạo đơn mới từ báo giá tương ứng.'
                    ) % order.name)
        res = super().write(vals)
        # Mọi đường chuyển sang 'confirmed' (nút Xác nhận, sửa tay) đều phải
        # nâng cấp SP gia công còn Nháp.
        if vals.get('state') == 'confirmed':
            self._promote_draft_products()
        return res

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

    @api.constrains('date_order', 'quotation_id')
    def _check_order_after_quotation(self):
        """Chặn Ngày lên đơn sớm hơn ngày báo giá nguồn — không thể chốt đơn
        trước khi báo giá ra đời. So với ngày báo giá chứ không so hôm nay để
        đơn cũ vẫn sửa được."""
        for order in self:
            if order.date_order and order.quotation_id.date_order \
                    and order.date_order < order.quotation_id.date_order:
                raise ValidationError(_(
                    'Ngày lên đơn (%(nld)s) không được trước ngày báo giá nguồn '
                    '(%(nbg)s).') % {
                        'nld': order.date_order,
                        'nbg': order.quotation_id.date_order})

    def action_confirm(self):
        """Nút "Xác nhận" trên form Đơn — phần nâng cấp SP gia công do write() lo."""
        self.write({'state': 'confirmed'})

    def _promote_draft_products(self):
        """Chốt đơn thì "khai sinh" chính thức cho SP gia công đi kèm.

        SP Kỹ thuật tạo tạm khi xử lý RFQ đang ở Nháp — giờ chuẩn hoá (cấp Mã
        SP chính thức, gọn tên) rồi nâng lên "Đã duyệt" để vào danh mục dùng
        lại, đồng thời xác nhận + khoá BOM để đơn cũ luôn tra được đúng bản đã
        làm. sudo vì Sales chốt đơn nhưng không có quyền sửa SP/BOM."""
        products = self.mapped('line_ids.product_id').filtered(
            lambda p: p.dlm_lifecycle_state == 'draft')
        if products:
            # Chuẩn hóa TRƯỚC (sinh mã/gọn tên) rồi mới nâng trạng thái.
            products.sudo()._dlm_standardize_on_promote()
            products.sudo().write({'dlm_lifecycle_state': 'active'})
        # Đóng băng BOM tại thời điểm lên đơn:
        # 1) BOM còn Nháp (có vật tư) → "Đã xác nhận". BOM rỗng bỏ qua để không
        #    làm crash luồng chốt đơn (xác nhận BOM bắt buộc phải có dòng).
        # 2) BOM đã xác nhận → "Đã khoá" cho bất biến: sửa thiết kế sau này bắt
        #    buộc tạo bản mới, đơn cũ vẫn giữ đúng bản đã dùng.
        boms = self.mapped('line_ids.bom_id').filtered(lambda b: b.line_ids).sudo()
        draft_boms = boms.filtered(lambda b: b.status == 'draft')
        if draft_boms:
            draft_boms.action_confirm()
        to_lock = boms.filtered(lambda b: b.status == 'confirmed')
        if to_lock:
            to_lock.action_lock()

    def action_done(self):
        """Nút "Hoàn tất" trên form Đơn."""
        self.write({'state': 'done'})

    def action_cancel(self):
        """Nút "Huỷ" trên form Đơn."""
        self.write({'state': 'cancelled'})

    def _reset_draft_blockers(self):
        """Tìm xem đã có chứng từ nào bám vào đơn này chưa (giao hàng, hoá đơn…).

        Dò tự động qua metadata: bất kỳ model nào có Many2one trỏ về đơn mà đã
        có bản ghi thì tính là chứng từ sau đơn. Làm kiểu này để khi phase sau
        thêm giao hàng/hoá đơn, điều kiện "đã lỡ có chứng từ, không cho về nháp"
        vẫn tự đúng mà không phải sửa lại đây."""
        self.ensure_one()
        excluded_models = {
            'dl.sale.order',
            'dl.sale.order.line',
            'dl.sale.order.reset.draft.wizard',
        }
        relation_fields = self.env['ir.model.fields'].sudo().search([
            ('relation', '=', self._name),
            ('ttype', '=', 'many2one'),
            ('store', '=', True),
            ('model', 'not in', list(excluded_models)),
        ])
        blockers = []
        for relation_field in relation_fields:
            model_name = relation_field.model
            if not self.env.registry.get(model_name):
                continue
            Model = self.env[model_name]
            if Model._transient or relation_field.name not in Model._fields:
                continue
            count = Model.sudo().search_count([
                (relation_field.name, '=', self.id),
            ], limit=1)
            if count:
                blockers.append(relation_field.model_id.name or model_name)
        return blockers

    def _check_can_reset_draft(self):
        """Chốt các điều kiện được đưa đơn về nháp: đúng vai trò, đơn không sinh
        từ báo giá, đang ở "Đã xác nhận", và chưa lỡ có chứng từ sau đơn."""
        self.ensure_one()
        user = self.env.user
        if not self.env.su and not (
                user.has_group('dl_base.dl_group_sales_manager')
                or user.has_group('dl_base.dl_group_admin')):
            raise AccessError(_(
                'Chỉ Trưởng phòng Kinh doanh hoặc Admin được đưa đơn về nháp.'))
        if self.quotation_id:
            raise UserError(_(
                'Đơn %s được tạo từ báo giá đã được khách đồng ý nên không được '
                'đưa về nháp. Hãy hủy đơn, lập bản điều chỉnh báo giá và tạo đơn mới.'
            ) % self.name)
        if self.state != 'confirmed':
            raise UserError(_(
                'Chỉ đơn bán trực tiếp đang ở trạng thái Đã xác nhận mới được '
                'đưa về nháp.'))
        blockers = self._reset_draft_blockers()
        if blockers:
            raise UserError(_(
                'Không thể đưa đơn về nháp vì đã phát sinh chứng từ sau đơn: %s.'
            ) % ', '.join(sorted(set(blockers))))
        return True

    def action_reset_draft(self):
        """Nút "Đưa về nháp" trên form Đơn — mở dialog bắt nhập lý do, không đổi
        trạng thái ngay."""
        self._check_can_reset_draft()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đưa đơn bán hàng về nháp'),
            'res_model': 'dl.sale.order.reset.draft.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _reset_to_draft_with_reason(self, reason):
        """Dialog "Đưa đơn về nháp" bấm xong gọi vào đây: kiểm điều kiện lần
        nữa, đổi trạng thái và ghi lý do + người + thời điểm vào chatter."""
        self._check_can_reset_draft()
        reason = (reason or '').strip()
        if not reason:
            raise ValidationError(_('Vui lòng nhập lý do đưa đơn về nháp.'))
        now = fields.Datetime.now()
        self.write({
            'state': 'draft',
            'reset_draft_reason': reason,
            'reset_draft_by': self.env.user.id,
            'reset_draft_at': now,
        })
        self.message_post(body=_(
            'Đơn được đưa về Nháp bởi %(user)s.<br/>'
            '<strong>Lý do:</strong> %(reason)s',
            user=escape(self.env.user.display_name),
            reason=escape(reason),
        ))
        return True

    def action_open_quotation(self):
        """Smart button "Báo giá nguồn" — mở báo giá đã sinh ra đơn này."""
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
    qty = fields.Float(string='Số lượng', default=1.0)
    price_unit = fields.Float(string='Đơn giá', digits='Product Price')
    price_subtotal = fields.Float(string='Thành tiền', compute='_compute_subtotal',
                                  store=True, digits='Product Price')
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    # BOM chốt cho dòng gia công (chép từ báo giá) — dùng để xác nhận/khoá BOM
    # lúc chốt đơn (xem _promote_draft_products).
    bom_id = fields.Many2one('dl.bom', string='BOM', readonly=True)
    # Ảnh chụp BOM đã dùng — chép giá trị từ dòng báo giá, chỉ để tra cứu,
    # KHÔNG hiện trên form.
    bom_version = fields.Integer(string='Phiên bản BOM', readonly=True, copy=False)
    bom_approved_by = fields.Many2one(
        'res.users', string='Người duyệt BOM', readonly=True, copy=False)
    bom_confirmed_date = fields.Datetime(
        string='Ngày duyệt BOM', readonly=True, copy=False)
    line_type = fields.Selection([
        ('trading', 'Thương mại'),
        ('manufactured', 'Gia công'),
    ], string='Loại dòng', default='trading', readonly=True)

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit
