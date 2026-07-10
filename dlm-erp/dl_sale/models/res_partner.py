import re
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

# Regex nghiệp vụ (TDS §3.1 A1) — SĐT Việt Nam & email.
_PHONE_RE = re.compile(r'^(0|\+84)[0-9]{9,10}$')
_EMAIL_RE = re.compile(r'^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$')
_SPLIT_THRESHOLD_KEY = 'dl_sale.split_order_threshold'
_SPLIT_THRESHOLD_DEFAULT = 20_000_000.0
_CUSTOMER_ROLES = ('customer', 'both')


class ResPartner(models.Model):
    """
    Mở rộng res.partner cho nghiệp vụ DLM (theo TDS 4.0 §2.1 — dl.partner).
    Không tạo bảng mới — các trường được thêm vào res_partner (kế thừa Odoo native).

    partner_role: cột quyết định 1 partner là Khách hàng, NCC, hay cả hai
    (theo TDS 4.0 — thay cho 2 cờ Boolean is_dlm_customer/is_dlm_supplier cũ).
    Chốt lại với nhóm (khác bản TDS 4.0 gốc): 1 partner CÓ THỂ vừa là Khách
    hàng vừa là NCC ('both') — dùng nút "Cũng là NCC" / "Cũng là Khách hàng"
    trên form để chuyển sang 'both' thay vì tạo 2 bản ghi riêng.
    """
    _inherit = 'res.partner'

    # ── Phân loại DLM (TDS 4.0 §2.1, mở rộng theo quyết định nhóm) ─────
    partner_role = fields.Selection([
        ('customer', 'Khách hàng'),
        ('supplier', 'NCC / Thầu phụ'),
        ('both', 'Khách hàng & NCC'),
    ], string='Vai trò')

    pending_link_partner_id = fields.Many2one(
        "res.partner",
        string="Liên kết với (gộp thành Khách hàng & NCC)",
        copy=False,
        store=True,
        help="Gõ tên để tìm Khách hàng ↔ NCC",
    )

    # ── S03: Mã khách hàng (Customer ID) tự sinh KH-0001 ──────────────
    dlm_code = fields.Char(
        string='Mã KH',
        readonly=True,
        copy=False,
        index=True,
        help='Mã khách hàng tự sinh, duy nhất (VD: KH-0001)',
    )

    # ── S04: Nhà cung cấp ─────────────────────────────────────────────
    # Mã NCC (supplier_code), Nhóm vật tư cung cấp (category_id — Tags native)
    # và Điều kiện thanh toán do module dlm_supplier đảm nhiệm theo đúng
    # TDS 4.0 đã thống nhất (Cap_Nhat_S04_Nha_Cung_Cap.md — "Công nợ" bị bỏ
    # hẳn ở Phase 1, "Nhóm vật tư cung cấp" dùng category_id chứ không phải
    # Selection riêng) — không định nghĩa lại ở đây để tránh trùng lặp.

    # ── A1: Loại khách hàng (Entity Proposal A1.partner_type) ───────
    partner_type = fields.Selection(
        selection=[
            ('individual', 'Cá nhân'),
            ('company', 'Doanh nghiệp'),
            ('dealer', 'Đại lý'),
        ],
        string='Loại khách hàng',
        default='individual',
        help='Phân loại phục vụ lọc báo cáo và chiết khấu tự động (D6)',
    )

    # MST dùng field native `vat` có sẵn trên res.partner (TDS 4.0 — Cap_Nhat_S04),
    # không tự chế field riêng nữa.
    dlm_allow_dup_tax = fields.Boolean(
        string='Cho phép trùng MST (chi nhánh khác)',
        default=False,
        help='Tích khi đây là chi nhánh khác dùng chung MST — bỏ qua kiểm tra trùng (EX-05)',
    )

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
        help='≥2 báo giá cho KH này trong 7 ngày VÀ tổng gộp vượt ngưỡng auto '
             '(chống chia nhỏ né duyệt — EX-42)',
    )
    dlm_split_threshold = fields.Monetary(
        string='Ngưỡng gộp đơn',
        compute='_compute_dlm_quote_stats',
        currency_field='dlm_currency_id',
    )
    partner_type_label = fields.Char(
        string='Loại',
        compute='_compute_partner_type_label',
        store=False,
    )
    dlm_status_label = fields.Char(
        string='Trạng thái',
        compute='_compute_dlm_status_label',
        store=False,
    )

    @api.depends('active')
    def _compute_dlm_status_label(self):
        for rec in self:
            rec.dlm_status_label = 'Đang hợp tác' if rec.active else 'Ngừng hợp tác'

    _DLM_AVA_PALETTE = [
        ('#fde2e4', '#b23a48'), ('#dbe7ff', '#1e4fa3'), ('#e3f6e8', '#1b7a3d'),
        ('#fff1cc', '#8a5a00'), ('#ece0fb', '#5b3fa0'), ('#ffe1f0', '#a3226e'),
        ('#d9f2f4', '#0f6b73'),
    ]

    dlm_has_photo = fields.Boolean(
        string='Có ảnh đại diện',
        compute='_compute_dlm_has_photo', store=True,
    )
    dlm_initial = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_bg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_fg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)

    @api.depends('image_128')
    def _compute_dlm_has_photo(self):
        for rec in self:
            rec.dlm_has_photo = bool(rec.image_128)

    @api.depends('name')
    def _compute_dlm_avatar_letter(self):
        palette = self._DLM_AVA_PALETTE
        for rec in self:
            name = (rec.name or '').strip()
            rec.dlm_initial = name[0].upper() if name else '?'
            h = 0
            for ch in name:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            bg, fg = palette[h % len(palette)]
            rec.dlm_avatar_bg = bg
            rec.dlm_avatar_fg = fg

    def _compute_dlm_currency(self):
        currency = self.env.company.currency_id
        for rec in self:
            rec.dlm_currency_id = currency

    @api.depends('partner_type')
    def _compute_partner_type_label(self):
        mapping = dict(self._fields['partner_type'].selection)
        for rec in self:
            rec.partner_type_label = mapping.get(rec.partner_type, '')

    @api.depends('dlm_quotation_ids', 'dlm_quotation_ids.state',
                 'dlm_quotation_ids.date_order', 'dlm_quotation_ids.amount_total')
    def _compute_dlm_quote_stats(self):
        today = fields.Date.context_today(self)
        window_start = today - timedelta(days=7)
        threshold = self._get_split_threshold()
        # Role không được cấp quyền đọc Báo giá (vd chỉ xem KH/NCC): để trống
        # thống kê thay vì đọc dl.quotation — tránh AccessError khi mở form KH.
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
            # Cảnh báo khi ≥2 BG/7 ngày VÀ tổng gộp vượt ngưỡng auto.
            rec.dlm_split_warning = (
                len(recent) >= 2 and rec.dlm_recent_quote_total > threshold)

    def _get_split_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            _SPLIT_THRESHOLD_KEY, _SPLIT_THRESHOLD_DEFAULT)
        try:
            return float(param)
        except (TypeError, ValueError):
            return _SPLIT_THRESHOLD_DEFAULT

    # ── Liên kết đối tác trùng tên: điền field ngay khi chọn (không cần lưu) ──
    @api.onchange('pending_link_partner_id')
    def _onchange_pending_link_partner(self):
        if self.pending_link_partner_id:
            target = self.pending_link_partner_id.sudo()
            for f in ('name', 'phone', 'mobile', 'email', 'website', 'vat',
                      'street', 'street2', 'city', 'country_id', 'comment'):
                self[f] = target[f]

    # ── Auto sinh mã KH khi tạo mới (mã NCC do dlm_supplier tự đảm nhiệm) ──
    # Khi có pending_link_partner_id: chuyển create() thành write() lên record
    # đã chọn (gộp thành 'both') thay vì tạo bản ghi trùng lặp.
    @api.model_create_multi
    def create(self, vals_list):
        to_create = []
        linked_records = self.browse()
        for vals in vals_list:
            target_id = vals.pop('pending_link_partner_id', False)
            if target_id:
                target = self.browse(target_id).sudo()
                write_vals = {k: v for k, v in vals.items() if k in target._fields}
                write_vals['partner_role'] = 'both'
                if target.partner_role == 'supplier' and not target.partner_type \
                        and not write_vals.get('partner_type'):
                    write_vals['partner_type'] = 'company'
                target.write(write_vals)
                target.message_post(body=_(
                    "Chuyển thành 'Khách hàng & NCC' — hợp nhất từ dữ liệu tạo mới."))
                linked_records |= target
            else:
                to_create.append(vals)
        created = super().create(to_create) if to_create else self.browse()
        for rec in created:
            if rec.partner_role in _CUSTOMER_ROLES and not rec.dlm_code:
                rec.dlm_code = self.env['ir.sequence'].next_by_code('dlm.customer') or '/'
        return created + linked_records

    # Cũng là NCC (customer → both) — nút trên form Khách hàng.
    # def action_mark_also_supplier(self):
    #     for rec in self:
    #         if rec.partner_role == 'customer':
    #             rec.partner_role = 'both'

    # Cũng là Khách hàng (supplier → both) — nút trên form NCC.
    # Set kèm partner_type mặc định 'company' nếu chưa có, tránh vướng
    # constraint _check_partner_type ngay khi chuyển sang 'both'.
    # def action_mark_also_customer(self):
    #     for rec in self:
    #         if rec.partner_role == 'supplier':
    #             vals = {'partner_role': 'both'}
    #             if not rec.partner_type:
    #                 vals['partner_type'] = 'company'
    #             rec.write(vals)
    #             if not rec.dlm_code:
    #                 rec.dlm_code = self.env['ir.sequence'].next_by_code('dlm.customer') or '/'

    # Vô hiệu hóa: KH ('customer'/'both') cần Trưởng KD hoặc Admin; NCC/'both'
    # cũng được Kế toán vô hiệu hóa (theo quyết định nhóm cho role 'both').
    def write(self, vals):
        if "active" in vals and not vals["active"] and not self.env.su:
            is_sales_manager = self.env.user.has_group("dl_base.dl_group_sales_manager")
            is_accountant = self.env.user.has_group("dl_base.dl_group_accountant")
            is_admin = self.env.user.has_group("dl_base.dl_group_admin")
            for rec in self:
                if rec.partner_role not in _CUSTOMER_ROLES:
                    continue
                allowed = (
                    is_admin
                    or is_sales_manager
                    or (rec.partner_role == "both" and is_accountant)
                )
                if not allowed:
                    raise AccessError(
                        _(
                            "Chỉ Trưởng phòng Kinh doanh, Kế toán (với đối tác cả "
                            "hai vai trò) hoặc Admin mới được vô hiệu hóa khách hàng."
                        )
                    )
        res = super().write(vals)
        if "pending_link_partner_id" in vals:
            self._process_pending_link()
        return res

    # ── Constraints ───────────────────────────────────────────────────
    @api.constrains('partner_role', 'partner_type')
    def _check_partner_type(self):
        for rec in self:
            if rec.partner_role in _CUSTOMER_ROLES and not rec.partner_type:
                raise ValidationError(
                    'Khách hàng DLM phải có Loại khách hàng.'
                )

    @api.constrains('partner_role', 'partner_type', 'vat')
    def _check_company_tax_code(self):
        """MST bắt buộc với khách doanh nghiệp (dùng trên PDF báo giá S09)."""
        for rec in self:
            if rec.partner_role in _CUSTOMER_ROLES and rec.partner_type == 'company' \
                    and not (rec.vat and rec.vat.strip()):
                raise ValidationError(_(
                    'Khách hàng Doanh nghiệp bắt buộc phải có Mã số thuế (MST).'))

    @api.constrains('partner_role', 'phone', 'mobile')
    def _check_phone_format(self):
        """Validate SĐT Việt Nam (TDS A1): ^(0|+84)[0-9]{9,10}$."""
        for rec in self:
            if rec.partner_role not in _CUSTOMER_ROLES:
                continue
            for label, value in (('Điện thoại', rec.phone), ('Di động', rec.mobile)):
                if not value:
                    continue
                cleaned = re.sub(r'[\s.\-]', '', value)
                if not _PHONE_RE.match(cleaned):
                    raise ValidationError(_(
                        "%s '%s' không hợp lệ. Số điện thoại Việt Nam phải bắt "
                        "đầu bằng 0 hoặc +84 và gồm 10–11 chữ số."
                    ) % (label, value))

    @api.constrains('partner_role', 'email')
    def _check_email_format(self):
        for rec in self:
            if rec.partner_role in _CUSTOMER_ROLES and rec.email and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_(
                    "Email '%s' không hợp lệ.") % rec.email)

    @api.constrains('vat', 'partner_role', 'dlm_allow_dup_tax')
    def _check_unique_tax_code(self):
        """EX-05: chặn tạo KH trùng MST; cho phép ghi đè nếu là chi nhánh khác."""
        for rec in self:
            if rec.partner_role not in _CUSTOMER_ROLES or not rec.vat or rec.dlm_allow_dup_tax:
                continue
            dup = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('partner_role', 'in', _CUSTOMER_ROLES),
                ('vat', '=', rec.vat),
            ], limit=1)
            if dup:
                ref = (' — ' + dup.dlm_code) if dup.dlm_code else ''
                raise ValidationError(
                    "MST '%s' đã tồn tại trong hệ thống (KH: %s%s).\n"
                    "Nếu đây là chi nhánh khác dùng chung MST, hãy tích "
                    "'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do."
                    % (rec.vat, dup.name, ref)
                )

    # Method phục vụ search ở màn tạo Khách Hàng/NCC
    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        role = self.env.context.get("dl_link_search_role")
        if role:
            domain = (args or []) + [("partner_role", "=", role), ("active", "=", True)]
            partners = self.sudo().search(
                domain + [("name", operator, name)], limit=limit
            )
            return [(p.id, p.name) for p in partners]
        return super().name_search(name=name, args=args, operator=operator, limit=limit)

    # Method xử lý khi lưu
    def _process_pending_link(self):
        for rec in self:
            if not rec.pending_link_partner_id:
                continue
            target = rec.pending_link_partner_id.sudo()
            if target.partner_role != "both":
                vals = {"partner_role": "both"}
                if target.partner_role == "supplier" and not target.partner_type:
                    vals["partner_type"] = "company"   # đã fix bug == thành =
                target.write(vals)
                target.message_post(body=_(
                    "Được gộp vai trò 'Khách hàng & NCC' — liên kết từ '%s' (bởi %s)"
                ) % (rec.name, self.env.user.name))
            rec.message_post(body=_(
                "Đã liên kết với đối tác trùng tên: %s → partner_role đã chuyển 'both'."
            ) % target.name)
            rec.pending_link_partner_id = False