from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date

# Ai được nhìn thấy giá vốn trên form Báo giá: Trưởng KD, CEO, Admin.
# Sales (BA) mở cùng form nhưng chỉ thấy giá bán/chiết khấu — mọi field gắn
# groups=_COST_GROUPS sẽ biến mất khỏi màn của họ.
_COST_GROUPS = (
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
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
    # Trạng thái vẽ ra thanh stepper trên đầu form Báo giá, và quyết định nút
    # nào hiện ở header.
    #   Đường chính:  nháp → duyệt nội bộ → gửi khách → khách đồng ý → lên đơn.
    #   approved = công ty duyệt (vượt ngưỡng), accepted = khách chốt mua —
    #   hai việc khác nhau nên tách 2 trạng thái.
    #   Nhánh sau khi gửi: khách xin sửa (revision_requested), từ chối
    #   (rejected, bắt nhập lý do), hết hạn không phản hồi (expired), hoặc bị
    #   thay bằng bản mới (superseded — giữ lại để tra cứu, không xoá).
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

    # --- Điều khoản in vào file gửi khách ---
    # Nhập ở tab "Điều khoản & Ghi chú" trên form Báo giá, in ra PDF/Word khi
    # bấm "Xuất / Gửi báo giá". Chỉ là văn bản mô tả — không ảnh hưởng tiền hay
    # luồng phê duyệt nên cho sửa tự do tới khi lên đơn.
    payment_terms = fields.Text(
        string='Điều khoản thanh toán',
        help='Vd: Tạm ứng 50% khi ký hợp đồng, 50% khi giao hàng.')
    delivery_terms = fields.Text(
        string='Điều khoản giao hàng',
        help='Thời gian / địa điểm giao hàng, phương thức vận chuyển.')
    warranty_terms = fields.Text(
        string='Bảo hành',
        help='Điều kiện và thời gian bảo hành.')

    # Dải cảnh báo vàng trên form Báo giá khi khách còn thiếu MST/địa chỉ.
    # Chỉ NHẮC, không chặn: cố ý dùng field tính thay vì @api.constrains để
    # Sales vẫn gửi được. Nội dung này cũng được ghi vào chatter lúc bấm Gửi.
    customer_data_warning = fields.Char(
        string='Cảnh báo dữ liệu khách',
        compute='_compute_customer_data_warning')

    # --- Hạn hiệu lực với khách ---
    # Quá hạn mà khách im lặng: cron _cron_expire_quotations tự đẩy sang
    # "Hết hiệu lực", hoặc Sales bấm tay nút "Hết hiệu lực" trên form.
    validity_date = fields.Date(
        string='Hạn hiệu lực', tracking=True, copy=False,
        help='Ngày báo giá hết hiệu lực với khách. Quá hạn mà khách chưa chốt '
             'sẽ được chuyển sang Hết hiệu lực (thủ công hoặc tự động).')

    # --- Lý do từ chối ---
    # Chỉ ghi được qua wizard "Từ chối báo giá" (bắt buộc chọn lý do), không
    # sửa tay trên form.
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

    # --- Khách yêu cầu điều chỉnh ---
    # Ghi qua wizard "Khách yêu cầu điều chỉnh". Loại điều chỉnh quyết định dải
    # hướng dẫn hiện trên form: sửa giá thì Sales tự làm, đổi vật liệu thì phải
    # chuyển ngược về Kỹ thuật.
    revision_request_type = fields.Selection([
        ('commercial', 'Giá / chiết khấu'),
        ('technical', 'Vật liệu / kích thước / thiết kế'),
        ('terms', 'Giao hàng / điều khoản / khác'),
    ], string='Loại điều chỉnh khách yêu cầu', readonly=True, copy=False)
    revision_request_note = fields.Text(
        string='Nội dung khách yêu cầu', readonly=True, copy=False)

    # --- Phiên bản báo giá (Q-001 → Q-001-R2 → …) ---
    # Khách xin sửa thì KHÔNG ghi đè bản cũ: nút "Lập phiên bản mới" copy sang
    # bản mới và trỏ ngược về bản trước, để sau này còn tra được đã chào khách
    # giá nào vào lúc nào. Hai smart button trên form đi theo liên kết này.
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

    @api.depends('partner_id', 'partner_id.vat', 'partner_id.street')
    def _compute_customer_data_warning(self):
        """Ghép câu cảnh báo "khách còn thiếu MST/địa chỉ" cho dải vàng trên
        form Báo giá. Rỗng = đủ dữ liệu, dải tự ẩn."""
        for rec in self:
            missing = []
            partner = rec.partner_id
            if partner and not partner.vat:
                missing.append(_("mã số thuế"))
            if partner and not partner.street:
                missing.append(_("địa chỉ"))
            rec.customer_data_warning = (_(
                "Khách hàng thiếu %s — nên bổ sung trước khi gửi báo giá cho "
                "doanh nghiệp.") % ", ".join(missing)) if missing else False
    # copy=True vì nút "Lập phiên bản mới" dùng copy() — Odoo mặc định KHÔNG
    # copy one2many, bỏ dòng này thì bản mới ra rỗng trơn.
    line_ids = fields.One2many('dl.quotation.line', 'quotation_id',
                               string='Chi tiết', copy=True)
    currency_id = fields.Many2one('res.currency', string='Tiền tệ',
                                  default=lambda self: self.env.company.currency_id)

    # --- RFQ nguồn & ngày khoá giá ---
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

    # --- Các lớp tiền hiện ở khối tổng cuối form Báo giá ---
    # Xếp chồng: cộng tiền hàng → trừ chiết khấu → cộng VAT → tổng thanh toán.
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

    # Tô màu dòng trên DANH SÁCH Báo giá: báo giá còn sống mà sắp/đã quá hạn
    # thì đổi màu để Sales xử lý trước khi cron tự đánh dấu Hết hiệu lực.
    # Báo giá đã đóng luôn để 'ok' — không cần giục nữa.
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

    # Cột "Hạn hiệu lực" trên danh sách: in kèm đếm ngược ("còn 3 ngày") để
    # không bị nhầm với cột Ngày báo giá (cùng định dạng ngày). Non-stored nên
    # cột này không bấm sắp xếp được — cố ý, tránh sắp theo chuỗi ra kết quả sai.
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

    # Lãi gộp & cơ cấu giá thành — chỉ để HIỂN THỊ ở trang Phân tích giá thành
    # (không lưu, suy thẳng từ số đã có): lãi gộp = doanh thu ròng − giá thành;
    # cơ cấu = tổng vật tư/công đoạn/điều chỉnh theo dòng × số lượng đặt.
    gross_profit = fields.Float(
        string='Lãi gộp', compute='_compute_cost_breakdown',
        digits='Product Price', groups=_COST_GROUPS)
    # Markup niêm yết = lãi trên giá BÁN GỐC (trước chiết khấu) — bằng lợi nhuận
    # mục tiêu vì mỗi dòng được định giá ở đúng mục tiêu. Markup thực thu
    # (effective_markup) đo trên doanh thu SAU chiết khấu nên luôn thấp hơn khi
    # có CK: đây là hiện tượng đúng bản chất (CK ăn vào lãi niêm yết), không
    # phải lỗi. Ta hiển thị cả hai để đọc được mức bào mòn, và lấy GIÁ SÀN
    # (markup tối thiểu) làm lằn ranh cảnh báo thay vì so với mục tiêu.
    list_markup = fields.Float(
        string='Markup niêm yết (%)', compute='_compute_cost_breakdown',
        digits=(16, 2), groups=_COST_GROUPS)
    floor_markup = fields.Float(
        string='Markup tại giá sàn (%)', compute='_compute_cost_breakdown',
        digits=(16, 2), groups=_COST_GROUPS)
    cost_material_total = fields.Float(
        string='Vật tư', compute='_compute_cost_breakdown',
        digits='Product Price', groups=_COST_GROUPS)
    cost_operation_total = fields.Float(
        string='Công đoạn', compute='_compute_cost_breakdown',
        digits='Product Price', groups=_COST_GROUPS)
    cost_adjustment_total = fields.Float(
        string='Chi phí chung/điều chỉnh', compute='_compute_cost_breakdown',
        digits='Product Price', groups=_COST_GROUPS)

    # Diễn giải giá thành dạng "công thức" — đọc theo từng sản phẩm: vật tư cho
    # 1 sp → cộng, công đoạn cho 1 sp → cộng, chi phí chung → GIÁ THÀNH 1 SẢN
    # PHẨM, rồi mới × số lượng đặt, cuối cùng cộng markup ra giá bán. Bảng phẳng
    # cũ gộp mọi dòng đã ×số lượng nên không đọc được cost/1sp (yêu cầu user).
    cost_breakdown_html = fields.Html(
        string='Diễn giải giá thành', compute='_compute_cost_breakdown_html',
        sanitize=False, groups=_COST_GROUPS)

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
        related='partner_id.dlm_customer_group', string='Nhóm khách hàng',
        readonly=True)

    # --- Định tuyến phê duyệt ---
    # Server tự tính (xem _reevaluate_approval), người dùng không nhập. Kết quả
    # đẩy ra 2 nơi: dải cảnh báo trên form Báo giá và màn Phê duyệt báo giá.
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
    # Người đang mở form có được duyệt yêu cầu đang treo không — quyết định 2
    # nút "Phê duyệt / Từ chối" ngay trên form Báo giá có hiện hay không.
    # ⚠️ related_sudo=False là BẮT BUỘC: can_resolve tính theo user hiện tại,
    # đọc bằng sudo sẽ ghi cache dưới khoá su=True trong khi request web đọc
    # bằng su=False ⇒ lỗi "Compute method failed to assign". Vai trò nào cũng
    # đọc được yêu cầu duyệt nên bỏ sudo không mất quyền gì.
    approval_can_resolve = fields.Boolean(
        string='Được duyệt yêu cầu này',
        related='approval_request_id.can_resolve', related_sudo=False)
    below_floor = fields.Boolean(string='Dưới giá sàn', readonly=True,
                                 groups=_COST_GROUPS)
    discount_above_default = fields.Boolean(string='Chiết khấu > mặc định', readonly=True)
    discount_above_max = fields.Boolean(string='Chiết khấu > tối đa', readonly=True)

    # --- Dải thông báo ngay dưới stepper trên form Báo giá ---
    # Mỗi báo giá chỉ hiện ĐÚNG MỘT dải: server chọn sẵn mức màu + nội dung,
    # view chỉ việc in ra. Trước đây view tự xếp ~10 dải alert theo trạng thái,
    # có lúc 2–3 dải chồng nhau đẩy nội dung báo giá xuống dưới màn hình.
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
        """Chọn dải thông báo cho form Báo giá — xét từ nặng tới nhẹ (bị từ
        chối → chờ duyệt → hết hạn → khách xin sửa → …), gặp cái nào trước thì
        lấy cái đó và dừng."""
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

    # --- Dòng gợi ý nhỏ ngay dưới ô "Chiết khấu" (tab Chi tiết) ---
    # Luôn nói rõ nhóm khách này được giảm tối đa bao nhiêu, và đổi màu theo
    # con số Sales vừa gõ. Thay cho 3 dải alert cũ xếp phía trên ô nhập.
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
        """Câu gợi ý + màu cho ô Chiết khấu trên form Báo giá."""
        for rec in self:
            # Qua Nháp là ô chiết khấu đã khoá, gợi ý không còn tác dụng gì.
            # Chưa biết nhóm khách thì cũng không suy ra được khoảng cho phép.
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

    # Nuôi smart button "Đơn bán hàng" ở góc phải form Báo giá. Tìm bằng search
    # thay vì lưu sẵn: chiều sở hữu liên kết nằm ở dl.sale.order.quotation_id,
    # lưu thêm một bản ở đây là có 2 nguồn sự thật lệch nhau.
    sale_order_id = fields.Many2one(
        'dl.sale.order', string='Đơn bán hàng', compute='_compute_sale_order_id')

    def _compute_sale_order_id(self):
        """Tìm đơn bán hàng (chưa huỷ) sinh ra từ báo giá này."""
        Order = self.env['dl.sale.order'].sudo()
        for rec in self:
            rec.sale_order_id = Order.search([
                ('quotation_id', '=', rec.id),
                ('state', '!=', 'cancelled'),
            ], limit=1)

    # Các trạng thái coi như "đã đóng sổ": không còn là báo giá đang hiệu lực
    # của RFQ nên KHÔNG bị ràng buộc trùng bên dưới tính đến. Nhờ vậy lập phiên
    # bản mới không phải xoá bản cũ đi.
    _CLOSED_STATES = ('cancelled', 'superseded', 'expired', 'rejected')

    def init(self):
        """Dựng khoá chống trùng ở tầng DB: mỗi RFQ chỉ được có tối đa MỘT báo
        giá đang sống. Chặn ở đây (không chỉ ở Python) để hai người bấm "Tạo
        báo giá" cùng lúc không ra 2 bản.

        Phải viết SQL tay vì helper của Odoo không làm được UNIQUE kèm WHERE.
        DROP trước để bản index cũ (chỉ loại 'cancelled') được thay khi -u."""
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
        """Cấp số báo giá tự động — ô "Số báo giá" trên form là readonly."""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dl.quotation') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.price_subtotal', 'line_ids.total_cost',
                 'line_ids.floor_price', 'line_ids.qty',
                 'discount_pct', 'vat_pct')
    def _compute_amount(self):
        """Khối tổng tiền cuối form Báo giá + 3 số nội bộ (giá thành, giá sàn,
        markup thực) cho trang Phân tích giá thành. Chạy lại mỗi khi dòng hoặc
        chiết khấu/VAT đổi."""
        for rec in self:
            untaxed = sum(rec.line_ids.mapped('price_subtotal'))
            # Hiện mọi dòng đều chịu chiết khấu; cờ no_discount trên cấu phần
            # là để dành cho khoản phụ phí ở phase sau, chưa dùng tới.
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

    @api.depends('line_ids.material_cost', 'line_ids.operation_cost',
                 'line_ids.adjustment_cost', 'line_ids.qty',
                 'amount_untaxed', 'amount_before_vat', 'total_cost',
                 'floor_amount')
    def _compute_cost_breakdown(self):
        """3 hộp cơ cấu chi phí + hàng lãi/lỗ ở trang Phân tích giá thành."""
        for rec in self:
            rec.cost_material_total = sum(
                line.material_cost * line.qty for line in rec.line_ids)
            rec.cost_operation_total = sum(
                line.operation_cost * line.qty for line in rec.line_ids)
            rec.cost_adjustment_total = sum(
                line.adjustment_cost * line.qty for line in rec.line_ids)
            rec.gross_profit = rec.amount_before_vat - rec.total_cost
            cost = rec.total_cost
            rec.list_markup = (
                (rec.amount_untaxed - cost) / cost * 100.0 if cost else 0.0)
            rec.floor_markup = (
                (rec.floor_amount - cost) / cost * 100.0 if cost else 0.0)

    # --- Bảng "công thức" giá thành ở trang Phân tích giá thành --------------
    # Xếp cấu phần giá của dòng vào 3 nhóm hiển thị. Không có markup và
    # trading_base ở đây: markup in riêng ở chân bảng, trading_base thuộc nhánh
    # dòng thương mại.
    _RECIPE_CATEGORY = {
        'material': 'material', 'processed_material': 'material',
        'recovery': 'material', 'operation': 'operation',
        'operation_setup': 'operation', 'adjustment': 'overhead',
    }

    @api.depends('line_ids', 'line_ids.component_ids', 'line_ids.qty',
                 'line_ids.total_cost', 'line_ids.material_cost',
                 'line_ids.operation_cost', 'line_ids.adjustment_cost',
                 'line_ids.price_subtotal', 'line_ids.price_unit',
                 'line_ids.line_type', 'line_ids.name')
    def _compute_cost_breakdown_html(self):
        """Dựng sẵn HTML bảng giá thành cho trang Phân tích giá thành (form Báo
        giá) và cho màn Phê duyệt báo giá — hai nơi dùng chung một bảng."""
        for rec in self:
            if not rec.line_ids:
                rec.cost_breakdown_html = False
                continue
            # Nhiều sản phẩm: mỗi dòng gấp lại thành 1 hàng tóm tắt, bấm mới
            # bung công thức — đọc như bảng so sánh lãi giữa các sản phẩm.
            # Chỉ 1 sản phẩm thì bung sẵn, đỡ bắt người dùng bấm thêm.
            single = len(rec.line_ids) == 1
            blocks = [rec._cost_recipe_line_html(line, single)
                      for line in rec.line_ids]
            rec.cost_breakdown_html = Markup(
                '<div class="dl-recipe">%s%s</div>') % (
                    rec._cost_recipe_header_html(), Markup('').join(blocks))

    def _cost_recipe_header_html(self):
        # Hàng tiêu đề cột cho các dòng gấp (đồng bộ lưới với .dl-recipe-sum).
        return Markup(
            '<div class="dl-recipe-colhead">'
            '<span class="c-prod">Sản phẩm</span>'
            '<span class="c-qty">Số lượng đặt</span>'
            '<span class="c-unit">Giá thành/sp</span>'
            '<span class="c-sell">Giá bán dòng</span>'
            '<span class="c-mk">Markup</span></div>')

    def _cost_recipe_summary_html(self, line, unit_txt, markup_chip):
        # Hàng tóm tắt (thẻ <summary>): tên · SL · giá thành/1sp · giá bán dòng
        # · chip markup — đọc được kết luận mà không cần bung khối chi tiết.
        return Markup(
            '<summary class="dl-recipe-sum">'
            '<span class="c-prod"><i class="fa fa-chevron-right dl-recipe-chev" '
            'aria-hidden="true"></i><span class="t">%s</span></span>'
            '<span class="c-qty">%s</span>'
            '<span class="c-unit">%s</span>'
            '<span class="c-sell">%s</span>'
            '<span class="c-mk">%s</span></summary>') % (
                line.name or '', self._fmt_qty(line.qty or 0.0),
                unit_txt, self._fmt_money(line.price_subtotal), markup_chip)

    def _cost_markup_chip(self, markup_rate):
        # Chip markup theo sức khỏe: âm/0 = đỏ, dưới mục tiêu = vàng, đạt = xanh.
        rate = round(markup_rate, 1)
        target = self.target_markup or 0.0
        if rate <= 0:
            cls = 'text-bg-danger'
        elif target and rate < target:
            cls = 'text-bg-warning'
        else:
            cls = 'text-bg-success'
        sign = '+' if rate > 0 else ''
        return Markup('<span class="badge %s">%s%s%%</span>') % (
            cls, sign, self._fmt_qty(rate))

    @staticmethod
    def _fmt_money(value):
        # VND: nhóm nghìn bằng dấu chấm, không phần lẻ (đồng bộ widget dl_money).
        return "{:,.0f}".format(value or 0.0).replace(",", ".")

    @staticmethod
    def _fmt_qty(value):
        # Số lượng có thể lẻ: bỏ số 0 thừa, dấu phẩy thập phân kiểu VN.
        return ("%g" % (value or 0.0)).replace(".", ",")

    def _cost_component_label(self, comp):
        """Nhãn hiển thị của một cấu phần. Vật tư/SP lấy từ m2o đã lưu; công
        đoạn/điều chỉnh không lưu tên nên tra SỐNG từ rule nguồn (chỉ nhãn — số
        tiền vẫn là snapshot bất biến), có fallback nếu rule đã bị xoá."""
        if comp.material_id:
            return comp.material_id.display_name
        model, res_id = comp.source_model, comp.source_id
        if model and res_id and model in self.env:
            src = self.env[model].sudo().browse(res_id).exists()
            if src:
                if 'operation_id' in src._fields and src.operation_id:
                    return src.operation_id.display_name
                if 'name' in src._fields and src.name:
                    return src.name
                return src.display_name
        return dict(comp._fields['component_type'].selection).get(
            comp.component_type, comp.component_type)

    def _cost_recipe_cat_html(self, title, comps, subtotal_unit, order_qty, with_qty):
        """Một khối nhóm (Vật tư / Công đoạn / Chi phí chung) trong bảng công
        thức: liệt kê từng cấu phần rồi cộng lại cho 1 sản phẩm."""
        if not comps:
            return Markup('')
        rows = []
        for comp in comps:
            amt_unit = (comp.amount / order_qty) if order_qty else comp.amount
            label = self._cost_component_label(comp)
            if comp.component_type == 'operation_setup':
                label = label + ' — phí setup/lô'
            meta = Markup('<span class="q"></span>')
            if with_qty and comp.component_type in (
                    'material', 'processed_material', 'recovery'):
                q_unit = (comp.qty / order_qty) if order_qty else comp.qty
                meta = Markup('<span class="q">%s × %s</span>') % (
                    self._fmt_qty(q_unit), self._fmt_money(comp.unit_price))
            rows.append(Markup(
                '<div class="dl-recipe-row"><span class="n">%s</span>%s'
                '<span class="a">%s</span></div>') % (
                    label, meta, self._fmt_money(amt_unit)))
        return Markup(
            '<div class="dl-recipe-cat">'
            '<div class="dl-recipe-cat-title">%s</div>%s'
            '<div class="dl-recipe-sub"><span>Cộng %s / 1 sp</span>'
            '<span class="a">%s</span></div></div>') % (
                title, Markup('').join(rows),
                title.lower(), self._fmt_money(subtotal_unit))

    def _cost_recipe_line_html(self, line, single=False):
        """Khối công thức của MỘT dòng báo giá: hàng tóm tắt gấp/mở + 3 nhóm
        chi phí + chân bảng đi từ giá thành 1 sp ra giá bán cả dòng."""
        qty = line.qty or 0.0
        open_attr = Markup(' open') if single else Markup('')

        # Hàng thương mại mua về bán lại, không qua engine tính giá thành nên
        # chỉ có đơn giá bán để in.
        if line.line_type == 'trading':
            summary = self._cost_recipe_summary_html(
                line, unit_txt='—',
                markup_chip=Markup(
                    '<span class="badge text-bg-secondary">Thương mại</span>'))
            body = Markup(
                '<div class="dl-recipe-cat"><div class="dl-recipe-row">'
                '<span class="n">Sản phẩm thương mại — đơn giá bán</span>'
                '<span class="q"></span><span class="a">%s</span></div></div>'
                '<div class="dl-recipe-foot"><div class="dl-recipe-sell">'
                '<span>Giá bán cả dòng (trước chiết khấu)</span>'
                '<span class="a">%s</span></div></div>') % (
                    self._fmt_money(line.price_unit),
                    self._fmt_money(line.price_subtotal))
            return Markup(
                '<details class="dl-recipe-line"%s>%s'
                '<div class="dl-recipe-body">%s</div></details>') % (
                    open_attr, summary, body)

        groups = {'material': [], 'operation': [], 'overhead': []}
        for comp in line.component_ids:
            cat = self._RECIPE_CATEGORY.get(comp.component_type)
            if cat:
                groups[cat].append(comp)

        cats = Markup('').join([
            self._cost_recipe_cat_html(
                'Vật tư', groups['material'], line.material_cost, qty, True),
            self._cost_recipe_cat_html(
                'Công đoạn', groups['operation'], line.operation_cost, qty, False),
            self._cost_recipe_cat_html(
                'Chi phí chung', groups['overhead'], line.adjustment_cost, qty, False),
        ])

        line_cost = line.total_cost * qty
        line_markup = line.price_subtotal - line_cost
        markup_rate = (line_markup / line_cost * 100.0) if line_cost else 0.0
        summary = self._cost_recipe_summary_html(
            line, unit_txt=self._fmt_money(line.total_cost),
            markup_chip=self._cost_markup_chip(markup_rate))
        foot = Markup(
            '<div class="dl-recipe-foot">'
            '<div class="dl-recipe-unit"><span>Giá thành 1 sản phẩm</span>'
            '<span class="a">%s</span></div>'
            '<div class="dl-recipe-mul"><span>× %s sản phẩm = Giá thành cả dòng</span>'
            '<span class="a">%s</span></div>'
            '<div class="dl-recipe-markup"><span>+ Lợi nhuận (markup ~%s%%)</span>'
            '<span class="a">%s</span></div>'
            '<div class="dl-recipe-sell"><span>Giá bán cả dòng (trước chiết khấu)</span>'
            '<span class="a">%s</span></div></div>') % (
                self._fmt_money(line.total_cost),
                self._fmt_qty(qty), self._fmt_money(line_cost),
                self._fmt_qty(round(markup_rate, 1)), self._fmt_money(line_markup),
                self._fmt_money(line.price_subtotal))

        return Markup(
            '<details class="dl-recipe-line"%s>%s'
            '<div class="dl-recipe-body">%s%s</div></details>') % (
                open_attr, summary, cats, foot)

    # Sửa mấy field này là tiền đổi ⇒ phải xét lại xem báo giá còn cần duyệt
    # hay không.
    _REEVAL_TRIGGER_FIELDS = {'discount_pct', 'line_ids', 'partner_id'}

    def write(self, vals):
        """Sau khi lưu form Báo giá, tự xét lại điều kiện phê duyệt nếu người
        dùng vừa đụng vào chiết khấu / dòng hàng / khách hàng."""
        # Sửa dòng trên form thực chất đi qua write của header (lệnh one2many),
        # nên cắm cờ để dl.quotation.line.write không xét lại lần nữa — chỉ
        # chạy đúng một lần ở đây.
        res = super(DlQuotation, self.with_context(dl_skip_line_reeval=True)).write(vals)
        if self._REEVAL_TRIGGER_FIELDS & set(vals):
            for rec in self:
                # Báo giá đã lên đơn / đã đóng thì thôi, không xét lại nữa.
                if rec.state in ('draft', 'approved', 'sent'):
                    rec._reevaluate_approval()
        return res

    def _reevaluate_approval(self):
        """Xét lại điều kiện phê duyệt sau khi tiền đổi.

        Nếu phát sinh điều kiện phải duyệt mà báo giá đã trót ở "Đã duyệt nội
        bộ"/"Đã gửi khách" thì kéo về Nháp cho đi lại luồng. Tình huống này chỉ
        xảy ra khi ghi thẳng qua RPC — trên form các field đó đã khoá ngoài Nháp."""
        self.ensure_one()
        evaluation = self.env['dl.quotation.pricing.service'].reevaluate_quotation(self)
        if evaluation['required'] and self.state in ('approved', 'sent'):
            self.sudo().write({'state': 'draft'})
            self.message_post(body=_(
                "Dữ liệu giá thay đổi làm phát sinh điều kiện phê duyệt — "
                "báo giá quay về Nháp."))

    def _check_internal_approver(self):
        """Ai được bấm nút "Duyệt nội bộ". Ngoài 3 vai trò cố định còn chấp
        nhận công tắc "Duyệt báo giá" mà Admin tick ở màn Phân quyền."""
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
        """Nút "Duyệt nội bộ" trên header form Báo giá (chỉ hiện ở Nháp) —
        chuyển sang Đã duyệt nội bộ để gửi khách được.

        Kiểm quyền lại ở server vì ẩn nút chỉ là ẩn ở UI, và chặn đường tắt
        vượt mặt yêu cầu phê duyệt đang treo."""
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
        # sudo vì Trưởng KD được duyệt nhưng ACL model chỉ cho họ đọc báo giá —
        # quyền thật đã kiểm ở _check_internal_approver phía trên.
        self.sudo().write({'state': 'approved'})

    def action_send(self):
        """Nút "Gửi khách hàng" trên header form Báo giá.

        Duyệt nội bộ và duyệt theo ngưỡng là CÙNG một cổng, không bắt duyệt hai
        lần:
          - Dưới ngưỡng: Sales gửi thẳng từ Nháp.
          - Vượt ngưỡng: người duyệt xử lý yêu cầu → báo giá tự sang "Đã duyệt
            nội bộ" → lúc đó mới gửi được.
        Chưa nhập hạn hiệu lực thì tự điền mặc định."""
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
                # Từ Nháp chỉ được gửi thẳng khi thực sự không cần duyệt.
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
        # Kẹp bản PDF vào chatter làm bằng chứng "đã chào khách giá này" — sau
        # này khách thắc mắc thì mở đúng bản đã gửi ra đối chiếu.
        for rec in self:
            # Nhắc (không chặn) nếu hồ sơ khách còn thiếu MST/địa chỉ.
            if rec.customer_data_warning:
                rec.message_post(body=_(
                    "Lưu ý khi phát hành: %s") % rec.customer_data_warning)
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
        """Chặn nhập Hạn hiệu lực trước Ngày báo giá trên form — báo giá hết
        hạn trước cả khi phát hành là vô nghĩa.

        So với NGÀY BÁO GIÁ chứ không so với hôm nay: báo giá đã hết hiệu lực
        thì hạn nằm ở quá khứ là đúng, so với hôm nay sẽ không mở nổi bản ghi cũ."""
        for rec in self:
            if rec.validity_date and rec.date_order \
                    and rec.validity_date < rec.date_order:
                raise ValidationError(_(
                    'Hạn hiệu lực (%(hh)s) không được trước ngày báo giá '
                    '(%(nbg)s).') % {
                        'hh': rec.validity_date, 'nbg': rec.date_order})

    # ------------------------------------------------------------------
    # Hai hàm dưới do màn Phê duyệt báo giá gọi ngược về khi người duyệt bấm
    # Phê duyệt / Từ chối trên yêu cầu duyệt.
    # ------------------------------------------------------------------
    def _on_approval_approved(self, request):
        """Người duyệt đã đồng ý ⇒ mở khoá báo giá cho Sales gửi khách."""
        self.ensure_one()
        # sudo vì người duyệt (vd Trưởng KD) chỉ có quyền đọc báo giá; quyền
        # duyệt đã được yêu cầu duyệt kiểm trước khi gọi vào đây.
        vals = {'approval_state': 'approved'}
        # Duyệt xong là báo giá TỰ sang "Đã duyệt nội bộ", không bắt Sales đi
        # xin duyệt lần hai. Chỉ áp khi còn Nháp, trạng thái khác giữ nguyên.
        if self.state == 'draft':
            vals['state'] = 'approved'
        self.sudo().write(vals)
        if vals.get('state'):
            # sudo vì đăng chatter mặc định đòi quyền write, mà người duyệt chỉ
            # có read. Vẫn giữ uid nên chatter hiển thị đúng tên người duyệt.
            self.sudo().message_post(body=_(
                "Yêu cầu phê duyệt đã được %s chấp thuận — báo giá tự chuyển "
                "sang Đã duyệt nội bộ, sẵn sàng gửi khách."
            ) % (request.resolved_by_id.name or _("người duyệt")))

    def _on_approval_rejected(self, request):
        """Người duyệt từ chối ⇒ báo giá kẹt lại, Sales phải sửa rồi xin lại."""
        self.ensure_one()
        self.sudo().write({'approval_state': 'rejected'})

    def action_open_approval_request(self):
        """Smart button mở yêu cầu phê duyệt gắn với báo giá này."""
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
        """Nút "Phê duyệt" hiện ngay trên form Báo giá cho người có quyền duyệt
        — đỡ phải sang màn Phê duyệt báo giá. Quyền do chính yêu cầu duyệt kiểm."""
        self.ensure_one()
        req = self.approval_request_id
        if not req or req.state != 'pending':
            raise UserError(_("Báo giá không có yêu cầu phê duyệt đang chờ."))
        req.action_approve()

    def action_approval_open_reject(self):
        """Nút "Từ chối" trên form Báo giá — mở yêu cầu duyệt dạng dialog để
        người duyệt nhập lý do."""
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
        """Nút "Khách đồng ý" — Sales bấm khi khách chốt mua; mở ra nút Tạo đơn
        bán hàng."""
        for rec in self:
            if rec.state != 'sent':
                raise UserError(_(
                    "Chỉ ghi nhận khách đồng ý trên báo giá đã gửi khách."))
        self.write({'state': 'accepted'})

    def action_customer_withdraw(self):
        """Nút "Khách rút đồng ý" — khách đổi ý trước khi lên đơn.

        Kéo báo giá về "Đã gửi khách" để mở lại đủ 3 nhánh (đồng ý lại / xin
        điều chỉnh / từ chối). Đã lên đơn rồi thì không rút được nữa."""
        for rec in self:
            if rec.state != 'accepted':
                raise UserError(_(
                    "Chỉ rút lại đồng ý trên báo giá khách đã đồng ý (chưa lên đơn)."))
        self.write({'state': 'sent'})
        for rec in self:
            rec.message_post(body=_(
                "Khách rút lại đồng ý — báo giá quay về Đã gửi khách để xử lý tiếp."))

    def action_open_revision_wizard(self):
        """Nút "Khách yêu cầu điều chỉnh" — mở dialog chọn loại điều chỉnh +
        nội dung. Loại chọn ở đây quyết định dải hướng dẫn hiện sau đó trên form."""
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
        """Dialog "Khách yêu cầu điều chỉnh" bấm Xác nhận thì gọi vào đây: ghi
        nhận yêu cầu + đổi trạng thái + đăng chatter."""
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
        """Nút "Chuyển Kỹ thuật sửa BOM" — dùng khi khách đòi đổi vật liệu/kích
        thước, việc Sales không tự sửa được.

        Khép báo giá hiện tại lại và đẩy RFQ nguồn về "Đang xử lý" cho Kỹ
        thuật; sửa BOM xong Sales tạo báo giá mới. Màn hình nhảy sang RFQ."""
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
    # Từ chối báo giá. Nút không đổi trạng thái ngay mà mở dialog bắt nhập lý
    # do — mất đơn thì phải biết vì sao.
    # ------------------------------------------------------------------
    _REJECTABLE_STATES = ('draft', 'approved', 'sent', 'revision_requested')

    def action_open_reject_wizard(self):
        """Nút "Từ chối" trên form Báo giá — mở dialog chọn lý do."""
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
        """Dialog "Từ chối báo giá" gọi vào: ghi lý do + đóng báo giá.

        Đồng thời huỷ yêu cầu phê duyệt còn treo, nếu không nó nằm mãi trong
        hàng chờ của màn Phê duyệt báo giá dù báo giá đã chết."""
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
    # Hết hiệu lực: Sales bấm tay, hoặc cron tự chạy khi quá hạn.
    # ------------------------------------------------------------------
    _EXPIRABLE_STATES = ('approved', 'sent', 'revision_requested')

    def action_expire(self):
        """Nút "Hết hiệu lực" — đóng báo giá khách không phản hồi."""
        for rec in self:
            if rec.state not in self._EXPIRABLE_STATES:
                raise UserError(_(
                    "Chỉ đánh dấu hết hiệu lực báo giá Đã duyệt / Đã gửi / Yêu "
                    "cầu điều chỉnh."))
        self.write({'state': 'expired'})
        for rec in self:
            rec.message_post(body=_("Báo giá đã hết hiệu lực."))

    def action_reopen(self):
        """Nút "Gia hạn" trên báo giá đã hết hiệu lực — đưa lại về Đã gửi
        khách. Bắt Sales sửa Hạn hiệu lực sang tương lai trước, không thì gia
        hạn xong cron lại đóng ngay."""
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
        """Cron chạy nền hằng ngày: báo giá đã gửi khách mà quá hạn thì tự
        chuyển sang Hết hiệu lực (không cần ai bấm)."""
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
    # Lập phiên bản mới: Q-001 → Q-001-R2, bản cũ vẫn nằm đó để tra cứu.
    # ------------------------------------------------------------------
    _REVISABLE_STATES = ('sent', 'revision_requested', 'rejected', 'expired')

    def action_create_revision(self):
        """Nút "Sửa & gửi lại" — copy báo giá sang bản mới ở Nháp rồi mở luôn
        bản mới đó. Bản cũ còn sống thì đánh dấu "đã thay bản mới"; bản đã đóng
        (từ chối/hết hạn) giữ nguyên lý do, chỉ nối liên kết."""
        self.ensure_one()
        if self.state not in self._REVISABLE_STATES:
            raise UserError(_(
                "Chỉ lập phiên bản mới từ báo giá Đã gửi / Yêu cầu điều chỉnh / "
                "Từ chối / Hết hiệu lực."))
        base_name = (self.name or '').split('-R')[0]
        new_rev = (self.revision or 1) + 1
        # Phải đóng bản cũ TRƯỚC khi copy, vì một RFQ chỉ được có 1 báo giá
        # sống (khoá chống trùng ở init).
        # ⚠️ flush_recordset là bắt buộc: không đẩy lệnh UPDATE xuống DB ngay
        # thì lúc INSERT bản mới, khoá chống trùng vẫn thấy bản cũ đang sống ⇒
        # nổ lỗi trùng khoá.
        if self.state in ('sent', 'revision_requested'):
            self.write({'state': 'superseded'})
            self.flush_recordset(['state'])
        # sudo vì copy phải ĐỌC được các field giá vốn trên dòng để nhân bản,
        # mà Sales lại không có quyền đọc chúng.
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
        """Smart button "Bản báo giá trước" — nhảy về phiên bản liền trước."""
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
        """Smart button "Bản lập lại sau" — mở danh sách các phiên bản sinh ra
        từ báo giá này."""
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
        """Nút "Về nháp" — mở khoá báo giá để sửa lại."""
        for rec in self:
            if rec.state not in (
                    'approved', 'sent', 'revision_requested',
                    'rejected', 'expired'):
                raise UserError(_(
                    "Chỉ đưa về Nháp báo giá Đã duyệt / Đã gửi / Yêu cầu điều "
                    "chỉnh / Từ chối / Hết hiệu lực."))
        self.write({'state': 'draft'})

    def action_create_sale_order(self):
        """Nút "Tạo đơn bán hàng" (chỉ hiện khi khách đã đồng ý) — chép dòng +
        số tiền sang đơn mới, khoá báo giá lại rồi mở form đơn vừa tạo."""
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError(_(
                "Chỉ tạo đơn bán hàng khi khách đã đồng ý báo giá."))
        existing = self.env['dl.sale.order'].search([
            ('quotation_id', '=', self.id),
            ('state', '!=', 'cancelled'),
        ], limit=1)
        if existing:
            # Đơn đã có sẵn (bấm 2 lần, hoặc báo giá từng bị đưa về nháp) —
            # không tạo thêm đơn thứ hai, chỉ khoá lại báo giá cho khớp.
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
                    # Chép dấu vết BOM sang đơn để sau này tra được đơn này
                    # làm theo bản vẽ/định mức nào.
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
        """Smart button "Đơn bán hàng" — mở đơn đã tạo từ báo giá này."""
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
    qty = fields.Float(string='Số lượng', default=1.0)
    price_unit = fields.Float(string='Đơn giá', digits='Product Price')
    price_subtotal = fields.Float(string='Thành tiền', compute='_compute_subtotal',
                                  store=True, digits='Product Price')

    # --- Nguồn gốc dòng: từ dòng RFQ nào, sản phẩm/BOM nào ---
    rfq_line_id = fields.Many2one('dl.quotation.request.line', string='Dòng RFQ',
                                  ondelete='set null', readonly=True)
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    bom_id = fields.Many2one('dl.bom', string='BOM', readonly=True)
    # Ảnh chụp BOM tại lúc tạo báo giá — KHÔNG hiện trên form, chỉ để tra cứu
    # sau này. Cố ý copy giá trị chứ không related sống về bom_id.version: BOM
    # lên phiên bản mới thì báo giá cũ vẫn phải nhớ đúng bản đã dùng.
    bom_version = fields.Integer(string='Phiên bản BOM', readonly=True, copy=False)
    bom_approved_by = fields.Many2one(
        'res.users', string='Người duyệt BOM', readonly=True, copy=False)
    bom_confirmed_date = fields.Datetime(
        string='Ngày duyệt BOM', readonly=True, copy=False)
    line_type = fields.Selection([
        ('trading', 'Thương mại'),
        ('manufactured', 'Gia công'),
    ], string='Loại dòng', default='trading', readonly=True)

    # --- Giá vốn nội bộ: hiện ở trang Phân tích giá thành, ẩn với Sales ---
    base_price = fields.Float(string='Giá nền', digits='Product Price',
                              readonly=True, groups=_COST_GROUPS)
    material_cost = fields.Float(string='Chi phí vật tư/đv', digits='Product Price',
                                 readonly=True, groups=_COST_GROUPS)
    # Tiền công cắt/hàn/sơn cho 1 sản phẩm + phần phí setup lô chia đều.
    # Cộng cả 3 dòng chi phí ra total_cost.
    operation_cost = fields.Float(string='Chi phí công đoạn/đv', digits='Product Price',
                                  readonly=True, groups=_COST_GROUPS)
    # Các khoản cộng thêm ngoài vật tư và công: overhead, đóng gói, phụ phí
    # giao gấp, phụ phí đơn nhỏ, dự phòng.
    adjustment_cost = fields.Float(string='Chi phí chung/điều chỉnh/đv',
                                   digits='Product Price',
                                   readonly=True, groups=_COST_GROUPS)
    total_cost = fields.Float(string='Giá thành/đơn vị', digits='Product Price',
                              readonly=True, groups=_COST_GROUPS)
    floor_price = fields.Float(string='Giá sàn/đơn vị', digits='Product Price',
                               readonly=True, groups=_COST_GROUPS)

    component_ids = fields.One2many('dl.quotation.price.component', 'quotation_line_id',
                                    string='Cấu phần giá')

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit

    # Sửa/xoá dòng thẳng qua RPC (không đi qua form) cũng phải xét lại điều
    # kiện phê duyệt. Sửa trên form thì header đã xét rồi và cắm cờ
    # dl_skip_line_reeval để khỏi chạy hai lần.
    _LINE_REEVAL_FIELDS = {'price_unit', 'qty'}

    def write(self, vals):
        """Đổi đơn giá/số lượng của dòng ⇒ xét lại điều kiện phê duyệt."""
        res = super().write(vals)
        if (self._LINE_REEVAL_FIELDS & set(vals)
                and not self.env.context.get('dl_skip_line_reeval')):
            for quo in self.mapped('quotation_id'):
                if quo.state in ('draft', 'approved', 'sent'):
                    quo._reevaluate_approval()
        return res

    def unlink(self):
        """Xoá bớt dòng làm tổng tiền giảm ⇒ cũng xét lại điều kiện phê duyệt."""
        quotations = self.mapped('quotation_id')
        res = super().unlink()
        if not self.env.context.get('dl_skip_line_reeval'):
            for quo in quotations.exists():
                if quo.state in ('draft', 'approved', 'sent'):
                    quo._reevaluate_approval()
        return res
