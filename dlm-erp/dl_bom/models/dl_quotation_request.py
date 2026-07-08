from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlQuotationRequest(models.Model):
    """D1 — dl.quotation.request (RFQ, header). Nhóm D thuộc phần Sales/Vinh —
    ở đây chỉ giữ đúng field chuẩn TDS (name, customer_id, description,
    requested_date, deadline, status) + phần phân công kỹ thuật viên xử lý
    chung cả RFQ. Đánh giá mới/tương tự/cũ (product_check_result) nằm ở CẤP
    DÒNG (dl.quotation.request.line) vì 1 RFQ có thể vừa có hàng gia công cần
    BOM vừa có hàng trading không cần (VD minh họa CT-200 + GS-100)."""
    _name = 'dl.quotation.request'
    _description = 'Yêu cầu báo giá (RFQ)'
    _order = 'name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Mã RFQ', required=True, tracking=True, copy=False,
        default=lambda self: _('New'), readonly=True,
    )
    customer_id = fields.Many2one(
        'res.partner', string='Khách hàng', required=True, tracking=True,
        domain=[('is_dlm_customer', '=', True)],
    )
    description = fields.Text(
        string='Ghi chú chung',
        help='Mô tả chung của cả RFQ, VD: hẹn nhận hàng tại kho, điều khoản thanh toán...',
    )
    requested_date = fields.Datetime(
        string='Ngày nhận yêu cầu', required=True,
        default=fields.Datetime.now, tracking=True,
    )
    deadline = fields.Date(string='Deadline khách cần báo giá', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', string='File đính kèm',
        help='Bản vẽ / ảnh mẫu từ khách hàng',
    )

    status = fields.Selection([
        ('new', 'Mới'),
        ('assigned', 'Đã giao KT'),
        ('processing', 'Đang xử lý'),
        ('quoted', 'Đã tạo BG'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='new', tracking=True)

    technician_id = fields.Many2one(
        'res.users', string='Kỹ thuật viên phụ trách', tracking=True,
        domain=lambda self: [('groups_id', 'in', [
            self.env.ref('dl_base.dl_group_tech').id])],
    )
    assigned_date = fields.Datetime(string='Ngày giao KT', readonly=True)

    line_ids = fields.One2many(
        'dl.quotation.request.line', 'quotation_request_id', string='Dòng sản phẩm',
    )
    line_count = fields.Integer(compute='_compute_line_count')

    quotation_id = fields.Many2one(
        'dl.quotation', string='Báo giá liên kết', readonly=True,
        help='D3 — tạo bởi Sales sau khi toàn bộ dòng đã có kết quả kỹ thuật.',
    )
    created_by = fields.Many2one(
        'res.users', string='Người tạo', default=lambda self: self.env.uid,
        readonly=True,
    )
    is_overdue = fields.Boolean(compute='_compute_is_overdue')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_overdue = bool(
                rec.deadline and rec.deadline < today
                and rec.status not in ('quoted', 'cancelled'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dl.quotation.request') or _('New')
        return super().create(vals_list)

    def action_assign_technician(self):
        self.ensure_one()
        if not self.technician_id:
            raise UserError(_('Vui lòng chọn kỹ thuật viên trước khi giao.'))
        self.write({
            'status': 'assigned',
            'assigned_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_('RFQ đã được giao cho kỹ thuật viên %s.') % self.technician_id.name,
            partner_ids=self.technician_id.partner_id.ids,
        )
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.technician_id.id,
            summary=_('Kiểm tra RFQ %s — đánh giá từng dòng sản phẩm mới/tương tự/cũ') % self.name,
        )

    def action_start_processing(self):
        self.write({'status': 'processing'})

    def action_mark_quoted(self):
        self.write({'status': 'quoted'})

    def action_cancel(self):
        self.write({'status': 'cancelled'})

    def action_reset_new(self):
        self.write({'status': 'new'})


class DlQuotationRequestLine(models.Model):
    """D1 line — dl.quotation.request.line: 1 dòng = 1 sản phẩm được hỏi giá.
    product_name là text tự do (TDS) vì sản phẩm mới có thể chưa tồn tại trong
    product_product lúc tạo RFQ. Phần product_check_result/reference_bom_id/
    created_bom_id là mở rộng của Kỹ thuật (Huy) trên nền D1 gốc của Sales."""
    _name = 'dl.quotation.request.line'
    _description = 'Dòng yêu cầu báo giá'
    _order = 'quotation_request_id, sequence, id'

    quotation_request_id = fields.Many2one(
        'dl.quotation.request', string='RFQ', required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Thứ tự', default=10)
    product_name = fields.Char(string='Tên sản phẩm yêu cầu', required=True)
    product_category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm dự kiến',
    )
    quantity = fields.Float(string='Số lượng', default=1.0, required=True)
    note = fields.Char(string='Ghi chú dòng')

    # --- Đánh giá kỹ thuật (Kỹ thuật viên) ---
    product_check_result = fields.Selection([
        ('new_product', 'Sản phẩm mới hoàn toàn'),
        ('similar_product', 'Sản phẩm tương tự (có BOM tham chiếu)'),
        ('existing_product', 'Sản phẩm cũ (đã có BOM)'),
        ('trading_no_bom', 'Hàng trading — không cần BOM'),
    ], string='Kết quả kiểm tra sản phẩm', tracking=True)
    check_note = fields.Text(string='Ghi chú kiểm tra KT')

    reference_product_id = fields.Many2one(
        'dl.product', string='Sản phẩm tham chiếu',
        help='Sản phẩm tương tự hoặc sản phẩm cũ đã có (nếu áp dụng).',
    )
    reference_bom_id = fields.Many2one(
        'dl.bom', string='BOM tham chiếu',
        domain=[('status', 'in', ('confirmed', 'locked'))],
    )
    created_bom_id = fields.Many2one(
        'dl.bom', string='BOM đã tạo', readonly=True,
    )
    similar_bom_ids = fields.Many2many(
        'dl.bom', compute='_compute_similar_boms', string='BOM tương tự (gợi ý)',
    )

    @api.depends('product_category_id')
    def _compute_similar_boms(self):
        for line in self:
            if not line.product_category_id:
                line.similar_bom_ids = False
                continue
            product_ids = self.env['dl.product'].search([
                ('category_id', '=', line.product_category_id.id),
            ]).ids
            domain = [('status', 'in', ('confirmed', 'locked'))]
            domain += [('product_id', 'in', product_ids)] if product_ids else [('id', '=', 0)]
            line.similar_bom_ids = self.env['dl.bom'].search(domain, limit=10)

    def action_create_bom(self):
        self.ensure_one()
        if not self.product_check_result:
            raise UserError(_(
                'Vui lòng đánh giá kết quả kiểm tra sản phẩm trước khi tạo BOM.'))
        if self.product_check_result == 'trading_no_bom':
            raise UserError(_('Hàng trading không cần tạo BOM.'))

        context = {
            'default_bom_type': 'template',
            'default_status': 'draft',
        }

        if self.product_check_result == 'existing_product' and self.reference_bom_id:
            new_bom = self.reference_bom_id.action_create_new_version()
            if isinstance(new_bom, dict) and new_bom.get('res_id'):
                self.created_bom_id = new_bom['res_id']
            return new_bom

        if self.product_check_result == 'similar_product' and self.reference_bom_id:
            new_bom = self.reference_bom_id.copy({
                'status': 'draft',
                'version': 1,
                'change_note': _('Sao chép từ BOM tham chiếu %s cho RFQ %s') % (
                    self.reference_bom_id.name, self.quotation_request_id.name),
                'confirmed_by': False,
                'confirmed_date': False,
            })
            self.created_bom_id = new_bom.id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'dl.bom',
                'res_id': new_bom.id,
                'view_mode': 'form',
                'target': 'current',
            }

        # new_product
        if self.reference_product_id:
            context['default_product_id'] = self.reference_product_id.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tạo BOM mới cho %s') % self.product_name,
            'res_model': 'dl.bom',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }
