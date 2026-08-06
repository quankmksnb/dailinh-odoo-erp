from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date

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
    # Nhánh phản hồi của khách (đặc tả luồng "Sale gửi báo giá"): khách xin sửa
    # (revision_requested → lập phiên bản mới), từ chối (rejected, bắt lý do),
    # quá hạn không phản hồi (expired), hoặc bị thay bằng phiên bản mới
    # (superseded — giữ lại để truy vết, không xóa).
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('approved', 'Đã duyệt nội bộ'),
        ('sent', 'Đã gửi khách'),
        ('revision_requested', 'Yêu cầu điều chỉnh'),
        ('accepted', 'Khách đồng ý'),
        ('ordered', 'Đã lên đơn'),
        ('rejected', 'Từ chối'),
        ('expired', 'Hết hiệu lực'),
        ('superseded', 'Đã thay bằng bản mới'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='draft', tracking=True)
    note = fields.Text(string='Ghi chú')

    # --- Hạn hiệu lực với khách (đặc tả "Trường hợp 5 — khách không phản hồi") ---
    validity_date = fields.Date(
        string='Hạn hiệu lực', tracking=True, copy=False,
        help='Ngày báo giá hết hiệu lực với khách. Quá hạn mà khách chưa chốt '
             'sẽ được chuyển sang Hết hiệu lực (thủ công hoặc tự động).')

    # --- Lý do từ chối (bắt buộc chọn — "Trường hợp 4") ---
    reject_reason = fields.Selection([
        ('price_high', 'Giá cao'),
        ('lead_time', 'Thời gian giao hàng lâu'),
        ('tech_not_met', 'Không đáp ứng kỹ thuật'),
        ('chose_competitor', 'Khách chọn nhà cung cấp khác'),
        ('demand_cancelled', 'Khách hủy nhu cầu'),
        ('no_contact', 'Không liên hệ được'),
        ('other', 'Lý do khác'),
    ], string='Lý do từ chối', readonly=True, copy=False, tracking=True)
    reject_reason_note = fields.Text(
        string='Chi tiết từ chối', readonly=True, copy=False)

    # --- Khách yêu cầu điều chỉnh (phân loại để hướng dẫn bước tiếp theo) ---
    revision_request_type = fields.Selection([
        ('commercial', 'Giá / chiết khấu'),
        ('technical', 'Vật liệu / kích thước / thiết kế'),
        ('terms', 'Giao hàng / điều khoản / khác'),
    ], string='Loại điều chỉnh khách yêu cầu', readonly=True, copy=False)
    revision_request_note = fields.Text(
        string='Nội dung khách yêu cầu', readonly=True, copy=False)

    # --- Phiên bản báo giá (đặc tả "Quản lý phiên bản": Q-001 v1, v2…) ---
    # Không sửa đè bản cũ khi khách xin điều chỉnh — lập bản mới, giữ liên kết
    # về bản trước để truy vết phương án kỹ thuật/giá tại từng thời điểm.
    revision = fields.Integer(
        string='Phiên bản', default=1, readonly=True, copy=False)
    origin_quotation_id = fields.Many2one(
        'dl.quotation', string='Bản báo giá trước', readonly=True, copy=False,
        ondelete='set null', index=True,
        help='Bản báo giá liền trước mà báo giá này được lập lại từ.')
    revision_ids = fields.One2many(
        'dl.quotation', 'origin_quotation_id', string='Bản lập lại sau')
    revision_count = fields.Integer(
        string='Số bản lập lại', compute='_compute_revision_count')

    @api.depends('revision_ids')
    def _compute_revision_count(self):
        for rec in self:
            rec.revision_count = len(rec.revision_ids)
    # copy=True: "Lập phiên bản mới" (action_create_revision → copy) phải mang
    # theo toàn bộ dòng chi tiết sang bản mới (Odoo mặc định KHÔNG copy o2m).
    line_ids = fields.One2many('dl.quotation.line', 'quotation_id',
                               string='Chi tiết', copy=True)
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

    # --- Tín hiệu cận hạn cho danh sách (review UX list #f3) ---
    # Báo giá đang sống (Đã duyệt / Đã gửi / Yêu cầu điều chỉnh) mà Hạn hiệu lực
    # sắp tới hoặc đã qua → tô màu dòng để Sales ưu tiên xử lý trước khi cron tự
    # đánh dấu Hết hiệu lực. Không tính cho trạng thái đã đóng.
    validity_state = fields.Selection([
        ('ok', 'Còn hạn'),
        ('soon', 'Sắp hết hạn'),
        ('overdue', 'Quá hạn'),
    ], string='Tình trạng hiệu lực', compute='_compute_validity_state')

    @api.depends('validity_date', 'state')
    def _compute_validity_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            vs = 'ok'
            if rec.state in self._EXPIRABLE_STATES and rec.validity_date:
                if rec.validity_date < today:
                    vs = 'overdue'
                elif (rec.validity_date - today).days <= 7:
                    vs = 'soon'
            rec.validity_state = vs

    # Hạn hiệu lực kèm đếm ngược ngay trong ô (review UX list #f5) — tách khỏi
    # cột "Ngày" (cùng định dạng, khó phân biệt). Không sortable (computed
    # non-stored) nên không có bẫy sắp xếp theo chuỗi.
    validity_label = fields.Char(
        string='Hạn hiệu lực', compute='_compute_validity_label')

    @api.depends('validity_date', 'state')
    def _compute_validity_label(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.validity_date:
                rec.validity_label = ''
                continue
            shown = format_date(rec.env, rec.validity_date)
            if rec.state in self._EXPIRABLE_STATES:
                delta = (rec.validity_date - today).days
                if delta < 0:
                    shown += _(' (quá hạn %s ngày)') % (-delta)
                elif delta == 0:
                    shown += _(' (hết hạn hôm nay)')
                else:
                    shown += _(' (còn %s ngày)') % delta
            rec.validity_label = shown

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
    # Nhóm khách (từ res.partner) — hiển thị cho Sales biết khoảng chiết khấu
    # được phép thương lượng (mặc định/tối đa) ngay trên báo giá.
    partner_group = fields.Selection(
        related='partner_id.dlm_customer_group', string='Nhóm khách',
        readonly=True)

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

    # --- Dải trạng thái ngữ cảnh (gộp >10 alert cũ thành MỘT thông báo) ---
    # Trước đây form khai báo ~10 dải alert xếp chồng theo trạng thái; ở vài
    # trạng thái 2–3 dải cùng hiện, đẩy nội dung báo giá xuống sâu (review UX
    # #f2). Gom về một field tính toán: mỗi bản ghi chỉ có ĐÚNG một thông báo
    # (mức + nội dung), ưu tiên từ khẩn cấp → thông tin. View chỉ còn một dải
    # duy nhất ngay dưới stepper.
    status_banner_level = fields.Selection([
        ('info', 'Thông tin'),
        ('success', 'Thành công'),
        ('warning', 'Cảnh báo'),
        ('danger', 'Nguy hiểm'),
        ('secondary', 'Trung tính'),
    ], string='Mức thông báo trạng thái', compute='_compute_status_banner')
    status_banner_message = fields.Html(
        string='Thông báo trạng thái', compute='_compute_status_banner',
        sanitize=False)

    @api.depends('state', 'approval_required', 'approval_state', 'approval_level',
                 'approval_reasons', 'reject_reason', 'reject_reason_note',
                 'revision_request_type', 'revision_request_note', 'line_ids')
    def _compute_status_banner(self):
        reject_labels = dict(self._fields['reject_reason'].selection)
        for rec in self:
            level, msg = False, ''
            if rec.state == 'rejected':
                level = 'danger'
                reason = reject_labels.get(rec.reject_reason) or ''
                msg = Markup("<strong>Báo giá bị từ chối</strong> — lý do: %s") % reason
                if rec.reject_reason_note:
                    msg += Markup("<br/>%s") % rec.reject_reason_note
            elif rec.approval_state == 'rejected':
                level = 'danger'
                msg = Markup("Yêu cầu phê duyệt bị từ chối — cần chỉnh sửa báo giá.")
            elif rec.approval_required and rec.approval_state == 'pending':
                level = 'warning'
                msg = Markup(
                    "<strong>Báo giá cần phê duyệt — cấp: %s.</strong>") % (
                        rec.approval_level or '')
                if rec.approval_reasons:
                    msg += Markup(" %s") % rec.approval_reasons
            elif rec.state == 'expired':
                level = 'warning'
                msg = Markup(
                    "Báo giá đã <strong>hết hiệu lực</strong>. Đặt lại Hạn hiệu "
                    "lực ở tương lai rồi bấm <em>Gia hạn</em>, hoặc "
                    "<em>Sửa &amp; gửi lại</em> để lập phiên bản mới.")
            elif rec.state == 'revision_requested':
                note = rec.revision_request_note
                if rec.revision_request_type == 'technical':
                    level = 'warning'
                    msg = Markup(
                        "Khách muốn <strong>đổi vật liệu / kích thước / thiết "
                        "kế</strong>. Việc này cần Kỹ thuật sửa BOM — bấm "
                        "<em>Chuyển Kỹ thuật sửa BOM</em>.")
                elif rec.revision_request_type == 'terms':
                    level = 'info'
                    msg = Markup(
                        "Khách muốn điều chỉnh <strong>giao hàng / điều "
                        "khoản</strong>. Bấm <em>Sửa &amp; gửi lại</em> để chỉnh "
                        "rồi gửi lại khách.")
                else:
                    level = 'info'
                    msg = Markup(
                        "Khách muốn điều chỉnh <strong>giá / chiết khấu</strong>. "
                        "Bấm <em>Sửa &amp; gửi lại</em> để chỉnh chiết khấu/đơn "
                        "giá (xem khoảng cho phép ở tab Chi tiết) rồi gửi lại khách.")
                if note:
                    msg += Markup("<br/>Khách yêu cầu: %s") % note
            elif rec.state == 'superseded':
                level = 'secondary'
                msg = Markup(
                    "Báo giá này đã được <strong>thay bằng phiên bản mới</strong> "
                    "— chỉ lưu để truy vết.")
            elif rec.approval_state == 'approved':
                level = 'success'
                msg = Markup("Đã được phê duyệt — sẵn sàng gửi khách.")
            elif (rec.state == 'draft' and not rec.approval_required
                  and rec.approval_state == 'not_required' and rec.line_ids):
                level = 'success'
                msg = Markup(
                    "<strong>Báo giá đã sẵn sàng gửi khách.</strong> Giá trị nằm "
                    "trong ngưỡng không cần phê duyệt — bấm <em>Gửi khách "
                    "hàng</em> để gửi ngay.")
            rec.status_banner_level = level
            rec.status_banner_message = msg or False

    # --- Gợi ý chiết khấu (gộp 3 alert tab "Chi tiết" thành helper cạnh ô nhập) ---
    # Trước đây tab Chi tiết có 3 dải alert (khoảng cho phép / cao hơn mặc định /
    # vượt trần) xếp trên ô nhập Chiết khấu, đẩy ô nhập xuống (review UX #f3).
    # Gom thành MỘT helper ngắn ngay dưới ô Chiết khấu: luôn nêu khoảng cho phép
    # theo nhóm khách + phản ánh trạng thái hợp lệ hiện tại bằng màu.
    discount_hint_level = fields.Selection([
        ('info', 'Trong khoảng'),
        ('secondary', 'Trên mặc định'),
        ('warning', 'Vượt trần'),
    ], string='Mức gợi ý chiết khấu', compute='_compute_discount_hint')
    discount_hint_message = fields.Html(
        string='Gợi ý chiết khấu', compute='_compute_discount_hint',
        sanitize=False)

    @api.depends('state', 'partner_group', 'discount_default_rate',
                 'discount_max_rate', 'discount_above_default', 'discount_above_max')
    def _compute_discount_hint(self):
        for rec in self:
            # Chỉ hướng dẫn khi còn sửa được (Nháp) và biết nhóm khách để suy ra
            # khoảng cho phép; các trạng thái sau đã khóa chiết khấu.
            if rec.state != 'draft' or not rec.partner_group:
                rec.discount_hint_level = False
                rec.discount_hint_message = False
                continue
            group_label = dict(
                rec._fields['partner_group']._description_selection(rec.env)
            ).get(rec.partner_group, rec.partner_group)
            base = Markup(
                "Nhóm <strong>%s</strong>: mặc định %s%%, tối đa %s%%.") % (
                    group_label,
                    ('%g' % (rec.discount_default_rate or 0)),
                    ('%g' % (rec.discount_max_rate or 0)))
            if rec.discount_above_max:
                level = 'warning'
                msg = base + Markup(
                    " Chiết khấu <strong>vượt trần</strong> — cần Trưởng phòng KD "
                    "phê duyệt.")
            elif rec.discount_above_default:
                level = 'secondary'
                msg = base + Markup(
                    " Cao hơn mặc định nhưng vẫn trong giới hạn — gửi thẳng, "
                    "không cần duyệt.")
            else:
                level = 'info'
                msg = base + Markup(
                    " Deal tới mức tối đa gửi thẳng, chỉ vượt trần mới cần duyệt.")
            rec.discount_hint_level = level
            rec.discount_hint_message = msg

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

    # Trạng thái "đã đóng" — không còn là báo giá đang hiệu lực của RFQ, nên
    # KHÔNG tính vào ràng buộc "mỗi RFQ chỉ 1 báo giá đang hiệu lực". Nhờ đó khi
    # lập phiên bản mới, bản cũ (superseded/rejected/expired/cancelled) nhường
    # chỗ cho bản mới mà không phải drop constraint.
    _CLOSED_STATES = ('cancelled', 'superseded', 'expired', 'rejected')

    def init(self):
        """Partial unique index (Decision C7 + review #1): mỗi RFQ chỉ có tối đa
        MỘT báo giá đang hiệu lực. Các bản đã đóng (_CLOSED_STATES) được loại ra
        để versioning (lập bản mới, giữ bản cũ) không vi phạm. Odoo helper không
        hỗ trợ đồng thời UNIQUE + WHERE nên dùng SQL trực tiếp (tên bảng là hằng
        an toàn). DROP trước để định nghĩa index cũ (chỉ loại 'cancelled') được
        thay bằng định nghĩa mới khi -u."""
        self._cr.execute("DROP INDEX IF EXISTS dl_quotation_reqid_active_uniq")
        self._cr.execute(
            """
            CREATE UNIQUE INDEX dl_quotation_reqid_active_uniq
            ON {table} (quotation_request_id)
            WHERE quotation_request_id IS NOT NULL
              AND state NOT IN ('cancelled', 'superseded', 'expired', 'rejected')
            """.format(table=self._table)
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
        """Gửi báo giá cho khách hàng.

        "Duyệt nội bộ" và "duyệt theo ma trận" là CÙNG một cổng kiểm soát (quyết
        định gộp bước 2026-07-24). Vì vậy:
          - Không cần duyệt (dưới ngưỡng): Sales gửi THẲNG từ Nháp, không bắt ai
            duyệt thủ công.
          - Cần duyệt (vượt ngưỡng): phải qua ma trận phê duyệt → báo giá tự
            chuyển 'Đã duyệt nội bộ' rồi mới gửi được.
        Đặt hạn hiệu lực mặc định nếu Sales chưa nhập."""
        for rec in self:
            if rec.approval_state == 'pending':
                raise UserError(_(
                    "Báo giá đang chờ phê duyệt (%s) — chưa thể gửi khách."
                ) % (rec.approval_level or ''))
            if rec.approval_state == 'rejected':
                raise UserError(_(
                    "Yêu cầu phê duyệt đã bị từ chối — cần chỉnh sửa báo giá "
                    "trước khi gửi khách."))
            if rec.state == 'draft':
                # Chỉ cho gửi thẳng khi thực sự không cần duyệt.
                if rec.approval_required or rec.approval_state != 'not_required':
                    raise UserError(_(
                        "Báo giá cần được phê duyệt trước khi gửi khách."))
            elif rec.state != 'approved':
                raise UserError(_(
                    "Chỉ gửi khách báo giá ở Nháp (không cần duyệt) hoặc Đã "
                    "duyệt nội bộ."))
            if not rec.validity_date:
                rec.validity_date = rec._default_validity_date()
        self.write({'state': 'sent'})
        # Đính bản PDF vào chatter làm bằng chứng "bản đã gửi" (RV-02 / SALE-07).
        # Bản dựng bằng reportlab (thuần Python) — không phụ thuộc wkhtmltopdf.
        for rec in self:
            rec._post_quotation_document_to_chatter()

    def _default_validity_date(self):
        """Hạn hiệu lực mặc định = ngày báo giá + số ngày cấu hình
        (ir.config_parameter dl_sale.quotation_validity_days, mặc định 30)."""
        self.ensure_one()
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'dl_sale.quotation_validity_days', 30))
        base = self.date_order or fields.Date.context_today(self)
        return fields.Date.add(base, days=days)

    @api.constrains('date_order', 'validity_date')
    def _check_validity_after_order(self):
        """Hạn hiệu lực không được TRƯỚC ngày báo giá — một báo giá "hết hạn
        trước cả khi phát hành" là vô nghĩa. Kiểm tương đối theo ngày báo giá
        (KHÔNG so với hôm nay) để không phá bản ghi đã Hết hiệu lực: khi ấy
        validity_date nằm ở quá khứ là đúng bản chất."""
        for rec in self:
            if rec.validity_date and rec.date_order \
                    and rec.validity_date < rec.date_order:
                raise ValidationError(_(
                    'Hạn hiệu lực (%(hh)s) không được trước ngày báo giá '
                    '(%(nbg)s).') % {
                        'hh': rec.validity_date, 'nbg': rec.date_order})

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
        self.write({'state': 'accepted'})

    def action_open_revision_wizard(self):
        """Khách yêu cầu điều chỉnh — mở ô nhập LOẠI điều chỉnh (giá/chiết khấu,
        vật liệu-kỹ thuật, giao hàng-điều khoản) + nội dung, để hệ thống hướng
        dẫn đúng bước tiếp theo thay vì bắt người dùng tự đoán."""
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_(
                "Chỉ ghi nhận yêu cầu điều chỉnh trên báo giá đã gửi khách."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Khách yêu cầu điều chỉnh'),
            'res_model': 'dl.quotation.revision.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_quotation_id': self.id},
        }

    def _apply_revision_request(self, adjust_type, note):
        """Wizard gọi vào: ghi nhận yêu cầu điều chỉnh của khách + phân loại."""
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_(
                "Chỉ ghi nhận yêu cầu điều chỉnh trên báo giá đã gửi khách."))
        self.write({
            'state': 'revision_requested',
            'revision_request_type': adjust_type,
            'revision_request_note': note or False,
        })
        type_label = dict(
            self._fields['revision_request_type'].selection).get(
                adjust_type, adjust_type)
        body = _("Khách yêu cầu điều chỉnh (%s):") % type_label
        if note:
            body += "<br/>%s" % note
        self.message_post(body=body)

    def action_send_back_to_tech(self):
        """Khách đòi đổi vật liệu/kỹ thuật ⇒ cần Kỹ thuật sửa BOM. Khép báo giá
        hiện tại (superseded) và mở lại RFQ nguồn về 'Đang xử lý' để Kỹ thuật
        điều chỉnh BOM; sau đó Sales tạo lại báo giá."""
        self.ensure_one()
        rfq = self.quotation_request_id
        if not rfq:
            raise UserError(_(
                "Báo giá này không gắn RFQ nguồn nên không thể chuyển Kỹ thuật. "
                "Hãy dùng 'Sửa & gửi lại' để chỉnh trực tiếp."))
        if self.state != 'revision_requested':
            raise UserError(_(
                "Chỉ chuyển Kỹ thuật từ báo giá đang ở 'Yêu cầu điều chỉnh'."))
        self.write({'state': 'superseded'})
        rfq.action_reopen_for_revision(note=self.revision_request_note)
        self.message_post(body=_(
            "Đã chuyển yêu cầu về Kỹ thuật (RFQ %s) để điều chỉnh BOM.") % rfq.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Yêu cầu báo giá'),
            'res_model': 'dl.quotation.request',
            'res_id': rfq.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Từ chối — bắt buộc chọn lý do (mở wizard). action_reject giữ lại làm điểm
    # áp dụng chung (wizard gọi vào), không đặt trạng thái trực tiếp từ nút.
    # ------------------------------------------------------------------
    _REJECTABLE_STATES = ('draft', 'approved', 'sent', 'revision_requested')

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state not in self._REJECTABLE_STATES:
            raise UserError(_(
                "Chỉ từ chối báo giá đang ở Nháp / Đã duyệt / Đã gửi / Yêu cầu "
                "điều chỉnh."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Từ chối báo giá'),
            'res_model': 'dl.quotation.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_quotation_id': self.id},
        }

    def _apply_reject(self, reason, note):
        """Ghi nhận từ chối kèm lý do (wizard gọi). Hủy yêu cầu phê duyệt còn
        treo để không tồn đọng trong hàng chờ người duyệt."""
        reason_label = dict(
            self._fields['reject_reason'].selection).get(reason, reason)
        for rec in self:
            if rec.state not in self._REJECTABLE_STATES:
                raise UserError(_(
                    "Báo giá %s không ở trạng thái từ chối được.") % rec.name)
            req = rec.approval_request_id
            if req and req.state == 'pending':
                req.sudo().action_cancel_on_change(note=_(
                    "Yêu cầu bị hủy do báo giá %s đã bị từ chối.") % rec.name)
        self.write({
            'state': 'rejected',
            'reject_reason': reason,
            'reject_reason_note': note or False,
        })
        for rec in self:
            body = _("Báo giá bị từ chối — lý do: %s.") % reason_label
            if note:
                body += "<br/>%s" % note
            rec.message_post(body=body)

    # ------------------------------------------------------------------
    # Hết hiệu lực — thủ công + cron tự động khi quá hạn (Trường hợp 5).
    # ------------------------------------------------------------------
    _EXPIRABLE_STATES = ('approved', 'sent', 'revision_requested')

    def action_expire(self):
        for rec in self:
            if rec.state not in self._EXPIRABLE_STATES:
                raise UserError(_(
                    "Chỉ đánh dấu hết hiệu lực báo giá Đã duyệt / Đã gửi / Yêu "
                    "cầu điều chỉnh."))
        self.write({'state': 'expired'})
        for rec in self:
            rec.message_post(body=_("Báo giá đã hết hiệu lực."))

    def action_reopen(self):
        """Gia hạn báo giá đã hết hiệu lực — cần đặt lại Hạn hiệu lực ở tương
        lai trước khi mở lại (đưa về Đã gửi khách)."""
        self.ensure_one()
        if self.state != 'expired':
            raise UserError(_("Chỉ gia hạn báo giá đang Hết hiệu lực."))
        today = fields.Date.context_today(self)
        if not self.validity_date or self.validity_date < today:
            raise UserError(_(
                "Hãy đặt lại Hạn hiệu lực ở tương lai trước khi gia hạn."))
        self.write({'state': 'sent'})
        self.message_post(body=_(
            "Báo giá được gia hạn — hiệu lực đến %s.") % self.validity_date)

    @api.model
    def _cron_expire_quotations(self):
        """Cron: báo giá Đã gửi khách mà quá Hạn hiệu lực → Hết hiệu lực."""
        today = fields.Date.context_today(self)
        stale = self.search([
            ('state', '=', 'sent'),
            ('validity_date', '!=', False),
            ('validity_date', '<', today),
        ])
        for rec in stale:
            rec.state = 'expired'
            rec.message_post(body=_(
                "Báo giá tự động hết hiệu lực (quá hạn %s).") % rec.validity_date)
        return True

    # ------------------------------------------------------------------
    # Lập phiên bản mới (Q-001 → Q-001-R2). Giữ bản cũ để truy vết; bản cũ đang
    # "sống" (đã gửi / yêu cầu điều chỉnh) chuyển 'superseded' để nhường chỗ
    # ràng buộc 1-báo-giá-hiệu-lực-mỗi-RFQ. Bản đã đóng (rejected/expired) giữ
    # nguyên lý do, chỉ liên kết bản mới về nó.
    # ------------------------------------------------------------------
    _REVISABLE_STATES = ('sent', 'revision_requested', 'rejected', 'expired')

    def action_create_revision(self):
        self.ensure_one()
        if self.state not in self._REVISABLE_STATES:
            raise UserError(_(
                "Chỉ lập phiên bản mới từ báo giá Đã gửi / Yêu cầu điều chỉnh / "
                "Từ chối / Hết hiệu lực."))
        base_name = (self.name or '').split('-R')[0]
        new_rev = (self.revision or 1) + 1
        # Nhường chỗ TRƯỚC khi copy: bản mới (Nháp) và bản cũ không được cùng
        # "sống" trên một RFQ (partial-unique index). PHẢI flush lệnh UPDATE
        # (→superseded) xuống DB trước khi INSERT bản mới, nếu không partial
        # index vẫn thấy bản cũ "đang hiệu lực" ⇒ báo trùng khóa.
        if self.state in ('sent', 'revision_requested'):
            self.write({'state': 'superseded'})
            self.flush_recordset(['state'])
        # sudo: copy phải ĐỌC các field giá vốn trên dòng (base_price/…, gated
        # _COST_GROUPS) để nhân bản — Sales không có quyền đọc chúng. Giống
        # pricing service dùng sudo khi ghi field chi phí.
        new = self.sudo().copy({
            'name': '%s-R%s' % (base_name, new_rev),
            'revision': new_rev,
            'origin_quotation_id': self.id,
            'quotation_request_id': self.quotation_request_id.id,
            'state': 'draft',
            'date_order': fields.Date.context_today(self),
            'validity_date': False,
            'pricing_date': False,
            'reject_reason': False,
            'reject_reason_note': False,
            'approval_required': False,
            'approval_state': 'not_required',
            'approval_level': False,
            'approval_reasons': False,
            'approval_request_id': False,
        })
        self.message_post(body=_("Đã tạo bản chỉnh sửa %s.") % new.name)
        intro = _("Bản chỉnh sửa lập từ %s (phiên bản %s).") % (
            self.name, self.revision)
        if self.revision_request_note:
            intro += _("<br/>Khách yêu cầu: %s") % self.revision_request_note
        new.message_post(body=intro)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.quotation',
            'view_mode': 'form',
            'res_id': new.id,
            'target': 'current',
        }

    def action_open_origin(self):
        self.ensure_one()
        if not self.origin_quotation_id:
            raise UserError(_("Báo giá này không có bản trước."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dl.quotation',
            'view_mode': 'form',
            'res_id': self.origin_quotation_id.id,
            'target': 'current',
        }

    def action_open_revisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bản lập lại của %s') % self.name,
            'res_model': 'dl.quotation',
            'view_mode': 'tree,form',
            'domain': [('origin_quotation_id', '=', self.id)],
            'target': 'current',
        }

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in (
                    'approved', 'sent', 'revision_requested',
                    'rejected', 'expired'):
                raise UserError(_(
                    "Chỉ đưa về Nháp báo giá Đã duyệt / Đã gửi / Yêu cầu điều "
                    "chỉnh / Từ chối / Hết hiệu lực."))
        self.write({'state': 'draft'})

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
                    # Dấu vết BOM: copy scalar từ dòng báo giá sang dòng đơn (§5.3).
                    'bom_version': line.bom_version,
                    'bom_approved_by': line.bom_approved_by.id,
                    'bom_confirmed_date': line.bom_confirmed_date,
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
    # Dấu vết BOM tại thời điểm tạo báo giá (thiết kế BOM truy xuất §5.2) — lưu
    # để audit/truy xuất, KHÔNG hiển thị trên form. Không related sống về
    # bom_id.version (BOM có thể lên phiên bản mới sau này).
    bom_version = fields.Integer(string='Phiên bản BOM', readonly=True, copy=False)
    bom_approved_by = fields.Many2one(
        'res.users', string='Người duyệt BOM', readonly=True, copy=False)
    bom_confirmed_date = fields.Datetime(
        string='Ngày duyệt BOM', readonly=True, copy=False)
    line_type = fields.Selection([
        ('trading', 'Thương mại'),
        ('manufactured', 'Gia công'),
    ], string='Loại dòng', default='trading', readonly=True)

    # --- Phân tích chi phí nội bộ (ẩn với Sales) ---
    base_price = fields.Float(string='Giá nền', digits='Product Price',
                              readonly=True, groups=_COST_GROUPS)
    material_cost = fields.Float(string='Chi phí vật tư/đv', digits='Product Price',
                                 readonly=True, groups=_COST_GROUPS)
    # Chi phí công đoạn/đơn vị = biến đổi (cắt/hàn/sơn) + phí setup/lô phân bổ
    # (RV-01/B2). total_cost = material_cost + operation_cost.
    operation_cost = fields.Float(string='Chi phí công đoạn/đv', digits='Product Price',
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
