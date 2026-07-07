from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class DlQuotationRequest(models.Model):
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
    request_date = fields.Datetime(
        string='Ngày nhận yêu cầu', required=True,
        default=fields.Datetime.now, tracking=True,
    )
    deadline = fields.Date(string='Deadline khách cần báo giá', tracking=True)

    # Thông tin sản phẩm
    product_category_id = fields.Many2one(
        'dl.product.category', string='Nhóm sản phẩm dự kiến',
    )
    product_description = fields.Text(
        string='Mô tả yêu cầu',
        help='Chi tiết yêu cầu: sản phẩm, kích thước, số lượng, vật liệu',
    )
    dimension_spec = fields.Char(string='Kích thước (DxRxC, mm)')
    material_spec = fields.Char(string='Vật liệu chính')
    quantity = fields.Float(string='Số lượng', default=1.0)
    special_note = fields.Text(string='Ghi chú đặc biệt')
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

    # Giao cho kỹ thuật
    technician_id = fields.Many2one(
        'res.users', string='Kỹ thuật viên phụ trách', tracking=True,
        domain=lambda self: [('groups_id', 'in', [
            self.env.ref('dl_base.dl_group_tech').id])],
    )
    assigned_date = fields.Datetime(string='Ngày giao KT', readonly=True)

    # Kết quả đánh giá kỹ thuật
    product_check_result = fields.Selection([
        ('new_product', 'Sản phẩm mới hoàn toàn'),
        ('similar_product', 'Sản phẩm tương tự (có BOM tham chiếu)'),
        ('existing_product', 'Sản phẩm cũ (đã có BOM)'),
    ], string='Kết quả kiểm tra sản phẩm', tracking=True)
    check_note = fields.Text(string='Ghi chú kiểm tra KT')

    # Liên kết BOM/sản phẩm tham chiếu
    reference_product_id = fields.Many2one(
        'dl.product', string='Sản phẩm tham chiếu',
        help='Sản phẩm tương tự hoặc sản phẩm cũ đã có',
    )
    reference_bom_id = fields.Many2one(
        'dl.bom', string='BOM tham chiếu',
        domain=[('status', 'in', ('confirmed', 'locked'))],
        help='BOM có thể tái sử dụng hoặc tham khảo',
    )

    # Liên kết kết quả
    created_bom_id = fields.Many2one(
        'dl.bom', string='BOM đã tạo', readonly=True,
    )
    quotation_id = fields.Many2one(
        'dl.quotation', string='Báo giá liên kết', readonly=True,
    )

    created_by = fields.Many2one(
        'res.users', string='Người tạo', default=lambda self: self.env.uid,
        readonly=True,
    )

    # Computed
    is_overdue = fields.Boolean(compute='_compute_is_overdue')
    similar_bom_ids = fields.Many2many(
        'dl.bom', compute='_compute_similar_boms', string='BOM tương tự',
    )

    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_overdue = rec.deadline and rec.deadline < today and rec.status not in ('quoted', 'cancelled')

    @api.depends('product_category_id', 'material_spec')
    def _compute_similar_boms(self):
        for rec in self:
            domain = [('status', 'in', ('confirmed', 'locked'))]
            if rec.product_category_id:
                product_ids = self.env['dl.product'].search([
                    ('category_id', '=', rec.product_category_id.id),
                ]).ids
                if product_ids:
                    domain.append(('product_id', 'in', product_ids))
                else:
                    rec.similar_bom_ids = False
                    continue
            rec.similar_bom_ids = self.env['dl.bom'].search(domain, limit=10)

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
            summary=_('Kiểm tra RFQ %s — đánh giá sản phẩm mới/tương tự/cũ') % self.name,
        )

    def action_start_processing(self):
        self.ensure_one()
        self.write({'status': 'processing'})

    def action_create_bom(self):
        self.ensure_one()
        if not self.product_check_result:
            raise UserError(_(
                'Vui lòng đánh giá kết quả kiểm tra sản phẩm trước khi tạo BOM.'))

        context = {
            'default_bom_type': 'quotation',
            'default_rfq_id': self.id,
            'default_status': 'draft',
        }

        if self.product_check_result == 'existing_product' and self.reference_bom_id:
            new_bom = self.reference_bom_id.action_create_new_version()
            if isinstance(new_bom, dict) and new_bom.get('res_id'):
                bom = self.env['dl.bom'].browse(new_bom['res_id'])
                bom.write({'rfq_id': self.id})
                self.write({'created_bom_id': bom.id, 'status': 'processing'})
            return new_bom

        if self.product_check_result == 'similar_product' and self.reference_bom_id:
            new_bom = self.reference_bom_id.copy({
                'bom_type': 'quotation',
                'status': 'draft',
                'version': 1,
                'rfq_id': self.id,
                'change_note': _('Sao chép từ BOM tham chiếu %s cho RFQ %s') % (
                    self.reference_bom_id.name, self.name),
                'confirmed_by': False,
                'confirmed_date': False,
            })
            self.write({'created_bom_id': new_bom.id, 'status': 'processing'})
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
        self.write({'status': 'processing'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tạo BOM mới cho RFQ %s') % self.name,
            'res_model': 'dl.bom',
            'view_mode': 'form',
            'target': 'current',
            'context': context,
        }

    def action_cancel(self):
        self.write({'status': 'cancelled'})

    def action_reset_new(self):
        self.write({'status': 'new'})
