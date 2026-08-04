import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

_PHONE_RE = re.compile(r'^(0|\+84)[0-9]{9,10}$')
_EMAIL_RE = re.compile(r'^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$')
# MST: 10 chữ số, hoặc 10 chữ số-3 chữ số (mã chi nhánh). Chỉ số và dấu '-'.
# Đồng bộ với widget frontend dl_partner/static/src/fields/tax_code_field.js.
_TAX_CODE_RE = re.compile(r'^\d{10}(-\d{3})?$')
_CUSTOMER_ROLES = ('customer', 'both')


class ResPartner(models.Model):
    """
    Mở rộng res.partner cho nghiệp vụ DLM (theo TDS 4.0 §2.1 — dl.partner).
    Không tạo bảng mới — các trường được thêm vào res_partner (kế thừa Odoo native).

    partner_role: cột quyết định 1 partner là Khách hàng, NCC, hay cả hai.
    Chốt: 1 partner CÓ THỂ vừa là Khách hàng vừa là NCC ('both') — dùng nút
    "Cũng là NCC" / "Cũng là Khách hàng" trên form để chuyển sang 'both'.
    """
    _inherit = 'res.partner'

    # ── Phân loại DLM ─────────────────────────────────────────────────
    partner_role = fields.Selection([
        ('customer', 'Khách hàng'),
        ('supplier', 'NCC / Thầu phụ'),
        ('both', 'Khách hàng & NCC'),
    ], string='Vai trò')

    pending_link_partner_id = fields.Many2one(
        'res.partner',
        string='Liên kết với (gộp thành Khách hàng & NCC)',
        copy=False,
        store=True,
        help='Gõ tên để tìm Khách hàng ↔ NCC',
    )

    # ── S03: Mã khách hàng tự sinh KH-0001 ────────────────────────────
    dlm_code = fields.Char(
        string='Mã KH',
        readonly=True,
        copy=False,
        index=True,
        help='Mã khách hàng tự sinh, duy nhất (VD: KH-0001)',
    )

    # ── A1: Loại khách hàng ────────────────────────────────────────────
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

    # MST dùng field native `vat` của res.partner — không tự chế field riêng.
    dlm_allow_dup_tax = fields.Boolean(
        string='Cho phép trùng MST (chi nhánh khác)',
        default=False,
        help='Tích khi đây là chi nhánh khác dùng chung MST — bỏ qua kiểm tra trùng (EX-05)',
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

    dlm_has_photo = fields.Boolean(
        string='Có ảnh đại diện',
        compute='_compute_dlm_has_photo', store=True,
    )
    dlm_initial = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_bg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)
    dlm_avatar_fg = fields.Char(compute='_compute_dlm_avatar_letter', store=False)

    _DLM_AVA_PALETTE = [
        ('#fde2e4', '#b23a48'), ('#dbe7ff', '#1e4fa3'), ('#e3f6e8', '#1b7a3d'),
        ('#fff1cc', '#8a5a00'), ('#ece0fb', '#5b3fa0'), ('#ffe1f0', '#a3226e'),
        ('#d9f2f4', '#0f6b73'),
    ]

    @api.depends('active')
    def _compute_dlm_status_label(self):
        for rec in self:
            rec.dlm_status_label = 'Đang hợp tác' if rec.active else 'Ngừng hợp tác'

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

    @api.depends('partner_type')
    def _compute_partner_type_label(self):
        mapping = dict(self._fields['partner_type'].selection)
        for rec in self:
            rec.partner_type_label = mapping.get(rec.partner_type, '')

    @api.onchange('pending_link_partner_id')
    def _onchange_pending_link_partner(self):
        if self.pending_link_partner_id:
            target = self.pending_link_partner_id.sudo()
            for f in ('name', 'phone', 'mobile', 'email', 'website', 'vat',
                      'street', 'street2', 'city', 'country_id', 'comment'):
                self[f] = target[f]

    @api.model_create_multi
    def create(self, vals_list):
        to_create = []
        linked_records = self.browse()
        for vals in vals_list:
            # Contact con (child_ids) cũng là res.partner nhưng KHÔNG phải KH DLM.
            # default 'customer'/'company' của action KH rò xuống vals con → gỡ ở
            # đây (đường tạo mới KH có child_ids). Ở đường sửa KH cũ + thêm contact,
            # parent_id chưa nằm trong vals lúc này nên còn được chốt lần nữa SAU
            # khi tạo (xem vòng lặp bên dưới).
            if vals.get('parent_id'):
                vals.pop('partner_role', None)
                vals.pop('partner_type', None)
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
            # Contact con: dù client/default có gán 'customer'/'company' + mã KH thì
            # vẫn ép gỡ — người liên hệ KHÔNG phải KH DLM, không được lọt danh sách
            # KH hay bị coi là "khách hàng mới". Chốt cuối, đúng cả đường sửa KH cũ.
            if rec.parent_id:
                fix = {}
                if rec.partner_role:
                    fix['partner_role'] = False
                if rec.dlm_code:
                    fix['dlm_code'] = False
                if fix:
                    rec.write(fix)
                continue
            if rec.partner_role in _CUSTOMER_ROLES and not rec.dlm_code:
                rec.dlm_code = self.env['ir.sequence'].next_by_code('dlm.customer') or '/'
        return created + linked_records

    def write(self, vals):
        if 'active' in vals and not vals['active'] and not self.env.su:
            is_sales_manager = self.env.user.has_group('dl_base.dl_group_sales_manager')
            is_accountant = self.env.user.has_group('dl_base.dl_group_accountant')
            is_admin = self.env.user.has_group('dl_base.dl_group_admin')
            for rec in self:
                if rec.partner_role not in _CUSTOMER_ROLES:
                    continue
                allowed = (
                    is_admin
                    or is_sales_manager
                    or (rec.partner_role == 'both' and is_accountant)
                )
                if not allowed:
                    raise AccessError(_(
                        'Chỉ Trưởng phòng Kinh doanh, Kế toán (với đối tác cả '
                        'hai vai trò) hoặc Admin mới được vô hiệu hóa khách hàng.'
                    ))
        res = super().write(vals)
        if 'pending_link_partner_id' in vals:
            self._process_pending_link()
        return res

    # ── Constraints ───────────────────────────────────────────────────
    def _dl_is_customer_record(self):
        """Bản ghi này có phải KH DLM (đối tượng của các ràng buộc KH) không?

        Chỉ đúng với KH cấp cao (top-level). Người liên hệ (child_ids) cũng là
        res.partner nhưng có `parent_id` — KHÔNG phải KH DLM, dù default
        'customer'/'company' của action có rò xuống. Nếu không loại chúng ra,
        contact rỗng MST sẽ dính ràng buộc 'Doanh nghiệp bắt buộc có MST'."""
        self.ensure_one()
        return self.partner_role in _CUSTOMER_ROLES and not self.parent_id

    def _dl_is_customer_contact(self):
        """Bản ghi này có phải NGƯỜI LIÊN HỆ của một KH DLM không?

        Contact con (có `parent_id`) mà đối tác gốc (commercial_partner_id) là KH
        DLM. Dùng để validate định dạng SĐT/email cho người liên hệ — KHÔNG áp
        các ràng buộc KH khác (MST, loại KH...) vốn chỉ dành cho KH top-level."""
        self.ensure_one()
        return bool(self.parent_id) \
            and self.commercial_partner_id.partner_role in _CUSTOMER_ROLES

    @api.constrains('partner_role', 'partner_type')
    def _check_partner_type(self):
        for rec in self:
            if rec._dl_is_customer_record() and not rec.partner_type:
                raise ValidationError('Khách hàng DLM phải có Loại khách hàng.')

    @api.constrains('partner_role', 'partner_type', 'vat')
    def _check_company_tax_code(self):
        """MST bắt buộc với khách doanh nghiệp (dùng trên PDF báo giá S09)."""
        for rec in self:
            if rec._dl_is_customer_record() and rec.partner_type == 'company' \
                    and not (rec.vat and rec.vat.strip()):
                raise ValidationError(_(
                    'Khách hàng Doanh nghiệp bắt buộc phải có Mã số thuế (MST).'))

    @api.constrains('partner_role', 'vat')
    def _check_tax_code_format(self):
        """Định dạng MST: chỉ chữ số và dấu '-', theo mẫu 10 số hoặc 10 số-3 số.
        Áp cho cả Doanh nghiệp lẫn Cá nhân — Cá nhân KHÔNG bắt buộc nhập, nhưng
        nếu đã nhập thì vẫn phải đúng định dạng."""
        for rec in self:
            if not rec._dl_is_customer_record():
                continue
            vat = (rec.vat or '').strip()
            if not vat:
                continue
            if not _TAX_CODE_RE.match(vat):
                raise ValidationError(_(
                    "Mã số thuế '%s' không hợp lệ. MST chỉ gồm chữ số và dấu "
                    "'-', theo định dạng 10 chữ số (VD: 0123456789) hoặc 10 chữ "
                    'số-3 chữ số cho chi nhánh (VD: 0123456789-001).'
                ) % rec.vat)

    @api.constrains('partner_role', 'phone', 'mobile')
    def _check_phone_format(self):
        """Validate SĐT Việt Nam (TDS A1): ^(0|+84)[0-9]{9,10}$."""
        for rec in self:
            if not rec._dl_is_customer_record():
                continue
            for label, value in (('Điện thoại', rec.phone), ('Di động', rec.mobile)):
                if not value:
                    continue
                cleaned = re.sub(r'[\s.\-]', '', value)
                if not _PHONE_RE.match(cleaned):
                    raise ValidationError(_(
                        "%s '%s' không hợp lệ. Số điện thoại Việt Nam phải bắt "
                        'đầu bằng 0 hoặc +84 và gồm 10–11 chữ số.'
                    ) % (label, value))

    @api.constrains('partner_role', 'email')
    def _check_email_format(self):
        for rec in self:
            if rec._dl_is_customer_record() and rec.email \
                    and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_("Email '%s' không hợp lệ.") % rec.email)

    # ── Người liên hệ của KH: cùng chuẩn định dạng SĐT/email như KH ─────
    @api.constrains('parent_id', 'phone', 'mobile')
    def _check_contact_phone_format(self):
        """SĐT người liên hệ của KH (nếu nhập) phải đúng định dạng VN."""
        for rec in self:
            if not rec._dl_is_customer_contact():
                continue
            for label, value in (('Điện thoại', rec.phone), ('Di động', rec.mobile)):
                if not value:
                    continue
                cleaned = re.sub(r'[\s.\-]', '', value)
                if not _PHONE_RE.match(cleaned):
                    raise ValidationError(_(
                        "Người liên hệ '%s': %s '%s' không hợp lệ. Số điện thoại "
                        'Việt Nam phải bắt đầu bằng 0 hoặc +84 và gồm 10–11 chữ số.'
                    ) % (rec.name or '', label, value))

    @api.constrains('parent_id', 'email')
    def _check_contact_email_format(self):
        """Email người liên hệ của KH (nếu nhập) phải đúng định dạng."""
        for rec in self:
            if rec._dl_is_customer_contact() and rec.email \
                    and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_(
                    "Người liên hệ '%s': Email '%s' không hợp lệ."
                ) % (rec.name or '', rec.email))

    @api.constrains('vat', 'partner_role', 'dlm_allow_dup_tax')
    def _check_unique_tax_code(self):
        """EX-05: chặn tạo KH trùng MST; cho phép ghi đè nếu là chi nhánh khác."""
        for rec in self:
            if not rec._dl_is_customer_record() or not rec.vat or rec.dlm_allow_dup_tax:
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
                    'Nếu đây là chi nhánh khác dùng chung MST, hãy tích '
                    "'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do."
                    % (rec.vat, dup.name, ref)
                )

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        role = self.env.context.get('dl_link_search_role')
        if role:
            domain = (args or []) + [('partner_role', '=', role), ('active', '=', True)]
            partners = self.sudo().search(
                domain + [('name', operator, name)], limit=limit
            )
            return [(p.id, p.name) for p in partners]
        return super().name_search(name=name, args=args, operator=operator, limit=limit)

    def get_formview_id(self, access_uid=None):
        if self.partner_role in _CUSTOMER_ROLES:
            return self.env.ref('dl_partner.view_dl_customer_form').id
        elif self.partner_role == 'supplier':
            return self.env.ref('dl_partner.view_dl_supplier_form').id
        return super().get_formview_id(access_uid=access_uid)

    def get_formview_action(self, access_uid=None):
        """Mở bản ghi qua mũi tên bằng action ĐÃ LƯU (có id) thay vì action tạm.
        res.partner dùng chung 1 model cho 2 vai trò nên không thể đặt 1 form làm
        mặc định; action tạm không mang view_id trong URL nên F5/deep-link rơi về
        form gốc Odoo. Trả về action form-only theo vai trò để URL mang action id
        -> F5/back giữ đúng form KH/NCC. Chỉ đổi điều hướng, không đổi nghiệp vụ."""
        xmlid = None
        if self.partner_role in _CUSTOMER_ROLES:
            xmlid = 'dl_partner.action_dl_customer_form'
        elif self.partner_role == 'supplier':
            xmlid = 'dl_partner.action_dl_supplier_form'
        if not xmlid:
            return super().get_formview_action(access_uid=access_uid)
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['res_id'] = self.id
        return action

    def _process_pending_link(self):
        for rec in self:
            if not rec.pending_link_partner_id:
                continue
            target = rec.pending_link_partner_id.sudo()
            if target.partner_role != 'both':
                vals = {'partner_role': 'both'}
                if target.partner_role == 'supplier' and not target.partner_type:
                    vals['partner_type'] = 'company'
                target.write(vals)
                target.message_post(body=_(
                    "Được gộp vai trò 'Khách hàng & NCC' — liên kết từ '%s' (bởi %s)"
                ) % (rec.name, self.env.user.name))
            rec.message_post(body=_(
                "Đã liên kết với đối tác trùng tên: %s → partner_role đã chuyển 'both'."
            ) % target.name)
            rec.pending_link_partner_id = False
