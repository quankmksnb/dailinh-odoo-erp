import re
import unicodedata

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

# SĐT VN hợp lệ: 0/+84 + 9-10 số, hoặc tổng đài 1800/1900.
_PHONE_RE = re.compile(r'^(?:(?:0|\+84)\d{9,10}|(?:1800|1900)\d{4,6})$')
_EMAIL_RE = re.compile(r'^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$')
# MST hợp lệ: 10 số, hoặc 10 số-3 số chi nhánh (khớp widget tax_code_field.js).
_TAX_CODE_RE = re.compile(r'^\d{10}(-\d{3})?$')
_CUSTOMER_ROLES = ('customer', 'both')

# Độ dài tối thiểu của Họ tên người liên hệ.
_MIN_NAME_LEN = 2
# Loại khách hàng là pháp nhân: bắt buộc địa chỉ và MST.
_LEGAL_ENTITY_TYPES = ('company', 'dealer')

# Các field được chép qua lại khi gộp hồ sơ KH - NCC (pending_link_partner_id).
_MERGE_FIELDS = (
    'name', 'phone', 'mobile', 'email', 'website', 'vat',
    'street', 'street2', 'city', 'country_id', 'comment',
)

# ── Chuẩn hóa dữ liệu trước khi lưu (để dò trùng hoạt động đúng) ───────────
_PHONE_SEP_RE = re.compile(r'[\s.\-()]')
_MULTI_SPACE_RE = re.compile(r'\s+')
_NAME_KEY_STRIP_RE = re.compile(r'[^a-z0-9]+')


def _normalize_phone(value):
    """Bỏ dấu phân cách và quy '+84' về '0': '+84 912.345.678' -> '0912345678'."""
    if not value:
        return value
    cleaned = _PHONE_SEP_RE.sub('', value)
    if cleaned.startswith('+84'):
        cleaned = '0' + cleaned[3:]
    return cleaned


def _normalize_email(value):
    return value.strip().lower() if value else value


def _normalize_name(value):
    """Bỏ khoảng trắng thừa hai đầu và gộp khoảng trắng lặp ở giữa."""
    return _MULTI_SPACE_RE.sub(' ', value).strip() if value else value


# Tiền tố pháp nhân bỏ qua khi lấy chữ cái avatar (xếp dài trước ngắn).
# Bản JS song song: dl_base/static/src/js/avatar_letter.js - sửa thì sửa cả hai.
_NAME_PREFIXES = (
    'công ty cổ phần', 'công ty tnhh mtv', 'công ty tnhh', 'công ty cp',
    'công ty', 'tổng công ty', 'doanh nghiệp tư nhân', 'hộ kinh doanh',
    'cửa hàng', 'cty tnhh', 'cty cp', 'cty', 'tnhh mtv', 'tnhh', 'cp',
    'dntn', 'hkd', 'xưởng', 'nhà máy', 'tập đoàn', 'chi nhánh',
)
_PREFIX_TRIM_RE = re.compile(r'^[\s.,\-–—]+')


def _significant_name(value):
    """Cắt tiền tố pháp nhân ở đầu tên: 'Công ty TNHH Việt Hưng' -> 'Việt Hưng'."""
    rest = (value or '').strip()
    changed = True
    while changed and rest:
        changed = False
        lower = rest.lower()
        for prefix in _NAME_PREFIXES:
            if lower.startswith(prefix):
                after = _PREFIX_TRIM_RE.sub('', rest[len(prefix):])
                if after:
                    rest = after
                    changed = True
                break
    return rest or (value or '').strip()


def _name_key(value):
    """Khóa dò trùng tên: bỏ dấu, hạ thường, bỏ ký tự không phải chữ/số."""
    if not value:
        return False
    text = unicodedata.normalize('NFD', value)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    # 'đ'/'Đ' không tách được bằng NFD nên xử riêng.
    text = text.replace('đ', 'd').replace('Đ', 'D')  # NFD không tách được 'đ'
    key = _NAME_KEY_STRIP_RE.sub('', text.lower())
    return key or False


class ResPartner(models.Model):
    """Mở rộng res.partner cho màn Khách hàng và màn Nhà cung cấp.

    partner_role quyết định bản ghi thuộc màn nào: Khách hàng, NCC, hoặc cả hai.
    """
    _inherit = 'res.partner'

    # ── Phân loại DLM ─────────────────────────────────────────────────
    partner_role = fields.Selection([
        ('customer', 'Khách hàng'),
        ('supplier', 'Nhà cung cấp / Thầu phụ'),
        ('both', 'Khách hàng & Nhà cung cấp'),
    ], string='Vai trò')

    pending_link_partner_id = fields.Many2one(
        'res.partner',
        string='Liên kết với (gộp thành Khách hàng & Nhà cung cấp)',
        copy=False,
        store=True,
        help='Gõ tên để tìm Khách hàng ↔ Nhà cung cấp',
    )

    # Mã khách hàng tự sinh KH-0001, hiện trên màn Khách hàng.
    dlm_code = fields.Char(
        string='Mã khách hàng',
        readonly=True,
        copy=False,
        index=True,
        help='Mã khách hàng tự sinh, duy nhất (VD: KH-0001)',
    )

    # Mã NCC tự sinh NCC-0001; tách riêng dlm_code để đối tác 'both' có đủ 2 mã.
    dlm_supplier_code = fields.Char(
        string='Mã nhà cung cấp',
        readonly=True,
        copy=False,
        index=True,
        help='Mã nhà cung cấp tự sinh, duy nhất (VD: NCC-0001)',
    )

    # Tab "Bảng giá cung cấp" trên form NCC: NCC này bán gì, giá bao nhiêu.
    dlm_supplierinfo_ids = fields.One2many(
        'product.supplierinfo', 'partner_id',
        string='Bảng giá cung cấp', readonly=True,
    )
    dlm_supplierinfo_count = fields.Integer(
        string='Số dòng bảng giá', compute='_compute_dlm_supplierinfo_count',
    )

    # Loại khách hàng: quyết định các ràng buộc bắt buộc (MST, địa chỉ, SĐT).
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

    # MST dùng field native `vat`. Cờ này là cửa thoát khi chặn trùng MST.
    dlm_allow_dup_tax = fields.Boolean(
        string='Cho phép trùng mã số thuế (chi nhánh khác)',
        default=False,
        help='Tích khi đây là chi nhánh khác dùng chung mã số thuế — bỏ qua kiểm tra trùng (EX-05)',
    )

    # Cửa thoát khi chặn trùng SĐT / Email (dùng chung tổng đài, hộp thư).
    dlm_allow_dup_contact = fields.Boolean(
        string='Cho phép trùng Số điện thoại / Email',
        default=False,
        help='Tích khi khách này dùng chung tổng đài hoặc hộp thư với một khách '
             'đã có — bỏ qua kiểm tra trùng SĐT/Email.',
    )

    # Lý do bắt buộc nhập khi tích một trong hai cờ cho phép trùng ở trên.
    dlm_dup_override_reason = fields.Text(
        string='Lý do cho phép trùng',
        help='Bắt buộc khi tích cho phép trùng Mã số thuế hoặc trùng Số '
             'điện thoại/Email. '
             'Ghi rõ vì sao đây không phải hồ sơ trùng lặp.',
    )

    # Khóa tên đã bỏ dấu, store + index để dò trùng bằng so bằng thay vì ilike.
    dlm_name_key = fields.Char(
        string='Khóa tên (dò trùng)',
        compute='_compute_dlm_name_key', store=True, index=True, readonly=True,
    )
    dlm_duplicate_name_warning = fields.Char(
        string='Cảnh báo trùng tên',
        compute='_compute_dlm_duplicate_name_warning',
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

    @api.depends('dlm_supplierinfo_ids')
    def _compute_dlm_supplierinfo_count(self):
        """Đếm số dòng bảng giá của NCC, hiện trên nút thống kê form NCC."""
        # sudo: mọi vai trò xem được form NCC đều phải thấy con số, không lỗi quyền.
        for rec in self:
            rec.dlm_supplierinfo_count = self.env['product.supplierinfo'].sudo(
            ).search_count([('partner_id', '=', rec.id)])

    @api.depends('active')
    def _compute_dlm_status_label(self):
        """Đổi cờ active thành chữ 'Đang / Ngừng hợp tác' cho cột Trạng thái."""
        for rec in self:
            rec.dlm_status_label = 'Đang hợp tác' if rec.active else 'Ngừng hợp tác'

    @api.depends('image_128')
    def _compute_dlm_has_photo(self):
        """Cờ có ảnh đại diện chưa, để view chọn hiện ảnh hay avatar chữ cái."""
        for rec in self:
            rec.dlm_has_photo = bool(rec.image_128)

    @api.depends('name')
    def _compute_dlm_avatar_letter(self):
        """Chữ cái và màu avatar cho đối tác chưa có ảnh, dùng ở list và kanban."""
        palette = self._DLM_AVA_PALETTE
        for rec in self:
            name = _significant_name(rec.name)
            rec.dlm_initial = name[0].upper() if name else '?'
            h = 0
            for ch in name:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            bg, fg = palette[h % len(palette)]
            rec.dlm_avatar_bg = bg
            rec.dlm_avatar_fg = fg

    @api.depends('name')
    def _compute_dlm_name_key(self):
        """Sinh khóa dò trùng từ tên mỗi lần tên thay đổi."""
        for rec in self:
            rec.dlm_name_key = _name_key(rec.name)

    @api.depends('dlm_name_key', 'partner_role')
    def _compute_dlm_duplicate_name_warning(self):
        """Cảnh báo mềm trên form khi tên gần giống một đối tác đã có, không chặn lưu."""
        for rec in self:
            rec.dlm_duplicate_name_warning = False
            if not rec.dlm_name_key or rec.parent_id or not rec.partner_role:
                continue
            # Chỉ dò trong cùng vai trò để không cảnh báo chéo màn KH và màn NCC.
            same_role = _CUSTOMER_ROLES \
                if rec.partner_role in _CUSTOMER_ROLES else ('supplier', 'both')
            domain = [
                ('partner_role', 'in', same_role),
                ('parent_id', '=', False),
                ('dlm_name_key', '=', rec.dlm_name_key),
            ]
            if isinstance(rec.id, int):
                domain.append(('id', '!=', rec.id))
            dup = rec.with_context(active_test=False).search(domain, limit=1)
            if dup:
                code = dup._dlm_display_code()
                rec.dlm_duplicate_name_warning = _(
                    "Đã có đối tác tên gần giống: %s%s. Kiểm tra lại xem có "
                    "phải cùng một đơn vị không trước khi lưu."
                ) % (dup.name, (' — %s' % code) if code else '')

    @api.depends('partner_type')
    def _compute_partner_type_label(self):
        """Nhãn chữ của Loại khách hàng để hiện ở cột list và badge."""
        mapping = dict(self._fields['partner_type'].selection)
        for rec in self:
            rec.partner_type_label = mapping.get(rec.partner_type, '')

    @api.onchange('pending_link_partner_id')
    def _onchange_pending_link_partner(self):
        """Chọn đối tác để gộp thì chép dữ liệu của họ lên form cho người dùng soát."""
        if self.pending_link_partner_id:
            target = self.pending_link_partner_id.sudo()
            for f in _MERGE_FIELDS:
                self[f] = target[f]

    # Hàm chuẩn hóa áp cho từng field khi ghi.
    _DLM_NORMALIZERS = {
        'name': _normalize_name,
        'phone': _normalize_phone,
        'mobile': _normalize_phone,
        'email': _normalize_email,
    }

    def _dlm_normalize_vals(self, vals):
        """Chuẩn hóa tên / SĐT / email ngay trong vals trước khi ghi xuống DB."""
        for fname, normalize in self._DLM_NORMALIZERS.items():
            if isinstance(vals.get(fname), str):
                vals[fname] = normalize(vals[fname])
        return vals

    @api.model
    def _dlm_vals_in_customer_scope(self, vals):
        """vals này có thuộc màn Khách hàng không (KH hoặc người liên hệ của KH)."""
        if vals.get('partner_role'):
            return True
        parent_id = vals.get('parent_id')
        if parent_id:
            parent = self.browse(parent_id).sudo()
            return parent.commercial_partner_id.partner_role in _CUSTOMER_ROLES
        return False

    @api.model_create_multi
    def create(self, vals_list):
        """Tạo đối tác: chuẩn hóa dữ liệu, dọn field thừa ở contact con, cấp mã tự sinh."""
        to_create = []
        linked_records = self.browse()
        for vals in vals_list:
            # Chuẩn hóa trước, vì nhánh gộp hồ sơ bên dưới chép thẳng vals đi.
            if self._dlm_vals_in_customer_scope(vals):
                self._dlm_normalize_vals(vals)
            if not self.env.su and (vals.get('dlm_allow_dup_tax')
                                    or vals.get('dlm_allow_dup_contact')):
                self._dlm_check_dup_override_right()
                self.browse()._dlm_check_dup_override_reason(vals)
            # Contact con không phải KH: gỡ default vai trò / loại rò từ action KH.
            if vals.get('parent_id'):
                vals.pop('partner_role', None)
                vals.pop('partner_type', None)
            target_id = vals.pop('pending_link_partner_id', False)
            if target_id:
                target = self.browse(target_id).sudo()
                # Gộp vào đối tác đã có: chỉ ghi các field trong _MERGE_FIELDS.
                write_vals = {k: v for k, v in vals.items() if k in _MERGE_FIELDS}
                write_vals['partner_role'] = 'both'
                if not target.partner_type:
                    write_vals['partner_type'] = 'company'
                target.write(write_vals)
                target.message_post(body=_(
                    "Chuyển thành 'Khách hàng & Nhà cung cấp' — hợp nhất từ dữ liệu tạo mới."))
                linked_records |= target
            else:
                to_create.append(vals)
        created = super().create(to_create) if to_create else self.browse()
        for rec in created:
            # Chốt lần cuối: contact con không được mang vai trò hay mã đối tác.
            if rec.parent_id:
                fix = {}
                if rec.partner_role:
                    fix['partner_role'] = False
                if rec.dlm_code:
                    fix['dlm_code'] = False
                if rec.dlm_supplier_code:
                    fix['dlm_supplier_code'] = False
                if fix:
                    rec.write(fix)
                continue
        created._dlm_assign_codes()
        return created + linked_records

    # Mỗi vai trò một dãy mã riêng; đối tác 'both' nhận cả hai mã.
    _DLM_CODE_SEQUENCES = (
        ('dlm_code', _CUSTOMER_ROLES, 'dlm.customer'),
        ('dlm_supplier_code', ('supplier', 'both'), 'dlm.supplier'),
    )

    def _dlm_assign_codes(self):
        """Cấp mã KH / NCC còn thiếu, chạy ở cả create và write nên đổi vai trò là có mã."""
        sequences = self.env['ir.sequence'].sudo()
        for rec in self:
            if rec.parent_id or not rec.partner_role:
                continue
            for fname, roles, seq_code in self._DLM_CODE_SEQUENCES:
                if rec.partner_role in roles and not rec[fname]:
                    rec[fname] = sequences.next_by_code(seq_code) or '/'

    def _dlm_display_code(self):
        """Mã hiển thị trong thông báo lỗi, lấy đúng theo vai trò của bản ghi."""
        self.ensure_one()
        if self.partner_role == 'supplier':
            return self.dlm_supplier_code or ''
        return self.dlm_code or self.dlm_supplier_code or ''

    def write(self, vals):
        """Ghi đối tác: chuẩn hóa dữ liệu, chặn ngừng hợp tác / hạ vai trò sai, cấp mã."""
        if any(rec._dl_is_dlm_partner() or rec._dl_is_customer_contact()
               for rec in self):
            self._dlm_normalize_vals(vals)
        if 'active' in vals and not vals['active'] and not self.env.su:
            for rec in self:
                if not rec.partner_role or rec.parent_id:
                    continue
                rec._dlm_check_archive_right()
                # Còn chứng từ đang chạy thì không cho ngừng hợp tác.
                pending = rec._dlm_open_document_summary()
                if pending:
                    raise ValidationError(_(
                        "Không ngừng hợp tác được với '%s' vì còn chứng từ đang "
                        'xử lý: %s.\nHãy đóng (hoàn tất hoặc hủy) các chứng từ '
                        'này trước.'
                    ) % (rec.name or '', ', '.join(pending)))
        if not self.env.su and (vals.get('dlm_allow_dup_tax')
                                or vals.get('dlm_allow_dup_contact')):
            self._dlm_check_dup_override_right()
            self._dlm_check_dup_override_reason(vals)
        if 'partner_role' in vals and not self.env.su:
            self._dlm_check_role_downgrade(vals['partner_role'])
        res = super().write(vals)
        self._dlm_assign_codes()
        if 'pending_link_partner_id' in vals:
            self._process_pending_link()
        return res

    def _dlm_check_archive_right(self):
        """Chặn nút Ngừng hợp tác nếu người dùng không thuộc bộ phận quản lý đối tác đó."""
        self.ensure_one()
        user = self.env.user
        if user.has_group('dl_base.dl_group_admin'):
            return
        role = self.partner_role
        if role in _CUSTOMER_ROLES:
            if user.has_group('dl_base.dl_group_sales_manager'):
                return
            if role == 'both' and user.has_group('dl_base.dl_group_accountant'):
                return
        if role in ('supplier', 'both'):
            if user.has_group('dl_base.dl_group_purchasing'):
                return
        allowed_roles = {
            'customer': _('Trưởng phòng Kinh doanh'),
            'supplier': _('Mua hàng'),
            'both': _('Trưởng phòng Kinh doanh, Kế toán hoặc Mua hàng'),
        }.get(role, _('Admin'))
        raise AccessError(_(
            "Chỉ %s hoặc Admin mới được vô hiệu hóa đối tác '%s'."
        ) % (allowed_roles, self.name or ''))

    def _dlm_check_role_downgrade(self, new_role):
        """Chặn đổi vai trò nếu vai trò bị bỏ vẫn còn chứng từ trỏ tới (sẽ mất khỏi màn)."""
        # (vai trò cũ, vai trò mới) -> vai trò bị bỏ đi.
        dropped_by_transition = {
            ('both', 'customer'): 'supplier',
            ('both', 'supplier'): 'customer',
            ('customer', 'supplier'): 'customer',
            ('supplier', 'customer'): 'supplier',
        }
        labels = dict(self._fields['partner_role'].selection)
        for rec in self:
            dropped = dropped_by_transition.get((rec.partner_role, new_role))
            if not dropped:
                continue
            refs = rec._dlm_reference_summary(side=dropped)
            if refs:
                raise ValidationError(_(
                    "Không đổi vai trò của '%s' sang '%s' được: vai trò %s đang "
                    'còn chứng từ tham chiếu (%s).\nCác chứng từ đó sẽ biến mất '
                    'khỏi màn tương ứng nếu bỏ vai trò.'
                ) % (
                    rec.name or '',
                    labels.get(new_role, new_role),
                    labels.get(dropped, dropped),
                    ', '.join(refs),
                ))

    def unlink(self):
        """Chặn nút Xóa khi đối tác đã phát sinh chứng từ, hướng người dùng sang Ngừng hợp tác."""
        for rec in self:
            if not rec.partner_role or rec.parent_id:
                continue
            refs = rec._dlm_reference_summary()
            if refs:
                raise ValidationError(_(
                    "Không xóa được '%s' vì đã phát sinh chứng từ: %s.\n"
                    'Hãy dùng "Ngừng hợp tác" để ẩn đối tác này khỏi các danh '
                    'sách chọn thay vì xóa — chứng từ cũ vẫn cần truy vết được.'
                ) % (rec.name or '', ', '.join(refs)))
        return super().unlink()

    # ── Chứng từ đang tham chiếu tới đối tác ───────────────────────────
    def _dlm_document_sources(self, side=None):
        """Bảng khai các model chứng từ trỏ tới đối tác, dùng để đếm khi xóa / ngừng hợp tác.

        Mỗi dòng gồm: model + field trỏ tới đối tác, side (thuộc vai trò KH hay
        NCC), label để ghép vào câu thông báo, open_domain (điều kiện chưa đóng),
        extra_domain (lọc cố định), active_test=False để đếm cả bản ghi đã lưu trữ.
        Model chưa cài thì bỏ qua nên không cần depends sang module nghiệp vụ.
        """
        sources = [
            {
                'model': 'dl.quotation', 'field': 'partner_id',
                'side': 'customer', 'label': 'báo giá',
                'open_label': 'báo giá chưa đóng',
                'open_domain': [('state', 'in', (
                    'draft', 'approved', 'sent', 'revision_requested',
                    'accepted'))],
            },
            {
                'model': 'dl.sale.order', 'field': 'partner_id',
                'side': 'customer', 'label': 'đơn bán hàng',
                'open_label': 'đơn bán hàng chưa hoàn tất',
                'open_domain': [('state', 'in', ('draft', 'confirmed'))],
            },
            {
                'model': 'dl.quotation.request', 'field': 'customer_id',
                'side': 'customer', 'label': 'yêu cầu báo giá (RFQ)',
                'open_label': 'RFQ đang xử lý',
                'open_domain': [('status', 'in', (
                    'new', 'processing', 'returned', 'supplemented',
                    'confirmed'))],
            },
            {
                'model': 'product.supplierinfo', 'field': 'partner_id',
                'side': 'supplier', 'label': 'dòng bảng giá nhà cung cấp',
                # Chỉ bảng giá đang áp dụng mới cản, vì đó là giá đang dùng để tính.
                'open_label': 'bảng giá nhà cung cấp đang áp dụng',
                'open_domain': [('is_applied', '=', True)],
                'active_test': False,
            },
            # Phiếu kho tách chiều nhập / xuất theo `code` native của loại hoạt động.
            {
                'model': 'stock.picking', 'field': 'partner_id',
                'side': 'customer', 'label': 'phiếu giao hàng',
                'open_label': 'phiếu giao hàng chưa hoàn tất',
                'extra_domain': [('picking_type_id.code', '=', 'outgoing')],
                'open_domain': [('state', 'not in', ('done', 'cancel'))],
            },
            {
                'model': 'stock.picking', 'field': 'partner_id',
                'side': 'supplier', 'label': 'phiếu nhập / trả nhà cung cấp',
                'open_label': 'phiếu nhập / trả nhà cung cấp chưa hoàn tất',
                'extra_domain': [('picking_type_id.code', '=', 'incoming')],
                'open_domain': [('state', 'not in', ('done', 'cancel'))],
            },
        ]
        for src in sources:
            if side and src['side'] != side:
                continue
            if src['model'] not in self.env:
                continue
            # sudo: người bấm xóa có thể không có quyền đọc chứng từ, nhưng vẫn phải bị chặn.
            model = self.env[src['model']].sudo()
            if src.get('active_test') is False:
                model = model.with_context(active_test=False)
            yield src, model

    def _dlm_count_documents(self, side, only_open):
        """Đếm chứng từ theo từng loại, trả về list chuỗi kiểu '3 báo giá'."""
        self.ensure_one()
        summary = []
        for src, model in self._dlm_document_sources(side):
            domain = [(src['field'], '=', self.id)]
            domain += src.get('extra_domain', [])
            if only_open:
                domain += src.get('open_domain', [])
            count = model.search_count(domain)
            if count:
                label = src['open_label'] if only_open else src['label']
                summary.append('%s %s' % (count, label))
        return summary

    def _dlm_reference_summary(self, side=None):
        """Mọi chứng từ trỏ tới đối tác kể cả đã đóng, dùng khi chặn Xóa và đổi vai trò."""
        return self._dlm_count_documents(side, only_open=False)

    def _dlm_open_document_summary(self, side=None):
        """Chỉ các chứng từ còn dang dở, dùng khi chặn Ngừng hợp tác."""
        return self._dlm_count_documents(side, only_open=True)

    # ── Constraints ───────────────────────────────────────────────────
    def _dl_is_customer_record(self):
        """Có phải khách hàng cấp cao không (loại người liên hệ ra khỏi ràng buộc KH)."""
        self.ensure_one()
        return self.partner_role in _CUSTOMER_ROLES and not self.parent_id

    def _dl_is_dlm_partner(self):
        """Có phải đối tác cấp cao (KH hoặc NCC) không, dùng cho ràng buộc chung hai màn."""
        self.ensure_one()
        return bool(self.partner_role) and not self.parent_id

    def _dl_is_supplier_record(self):
        """Có phải nhà cung cấp cấp cao không."""
        self.ensure_one()
        return self.partner_role in ('supplier', 'both') and not self.parent_id

    def _dl_partner_kind_label(self):
        """Tên gọi đối tác theo vai trò, để thông báo lỗi khớp với màn đang mở."""
        self.ensure_one()
        if self.partner_role == 'customer':
            return _('Khách hàng')
        if self.partner_role == 'supplier':
            return _('Nhà cung cấp')
        return _('Đối tác')

    def _dl_is_customer_contact(self):
        """Có phải bản ghi con của một khách hàng không, dùng cho ràng buộc định dạng."""
        self.ensure_one()
        return bool(self.parent_id) \
            and self.commercial_partner_id.partner_role in _CUSTOMER_ROLES

    @api.constrains('partner_role', 'partner_type')
    def _check_partner_type(self):
        """Khách hàng bắt buộc chọn Loại khách hàng khi lưu form."""
        for rec in self:
            if rec._dl_is_customer_record() and not rec.partner_type:
                raise ValidationError('Khách hàng DLM phải có Loại khách hàng.')

    @api.constrains('partner_role', 'name')
    def _check_partner_name(self):
        """Đối tác bắt buộc có Tên, chặn cả đường import Excel và RPC chứ không chỉ form."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            kind = rec._dl_partner_kind_label()
            name = (rec.name or '').strip()
            if not name:
                raise ValidationError(_('%s bắt buộc phải có Tên.') % kind)

    @api.constrains('partner_role', 'partner_type', 'phone', 'mobile', 'email')
    def _check_partner_contact_channel(self):
        """Đối tác phải có ít nhất một kênh liên lạc; riêng Cá nhân bắt buộc có số điện thoại."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            if rec.partner_type == 'individual':
                if not any((value or '').strip()
                           for value in (rec.phone, rec.mobile)):
                    raise ValidationError(_(
                        '%s loại Cá nhân bắt buộc phải có số Điện thoại '
                        'hoặc Di động.'
                    ) % rec._dl_partner_kind_label())
                continue
            has_channel = any(
                (value or '').strip()
                for value in (rec.phone, rec.mobile, rec.email)
            )
            if not has_channel:
                raise ValidationError(_(
                    '%s phải có ít nhất một kênh liên lạc: Điện thoại, '
                    'Di động hoặc Email.') % rec._dl_partner_kind_label())

    @api.constrains('partner_role', 'partner_type', 'street', 'city')
    def _check_customer_address(self):
        """Khách Doanh nghiệp / Đại lý bắt buộc có Đường và Tỉnh TP vì địa chỉ in lên báo giá."""
        for rec in self:
            if not rec._dl_is_customer_record():
                continue
            if rec.partner_type not in _LEGAL_ENTITY_TYPES:
                continue
            missing = []
            if not (rec.street or '').strip():
                missing.append(_('Đường'))
            if not (rec.city or '').strip():
                missing.append(_('Tỉnh / TP'))
            if missing:
                label = dict(self._fields['partner_type'].selection).get(
                    rec.partner_type, rec.partner_type)
                raise ValidationError(_(
                    'Khách hàng %s bắt buộc phải có địa chỉ. Còn thiếu: %s.'
                ) % (label, ', '.join(missing)))

    @api.constrains('partner_role', 'partner_type', 'vat')
    def _check_company_tax_code(self):
        """Khách Doanh nghiệp / Đại lý bắt buộc có Mã số thuế; chỉ Cá nhân được để trống."""
        for rec in self:
            if rec._dl_is_customer_record() \
                    and rec.partner_type in _LEGAL_ENTITY_TYPES \
                    and not (rec.vat and rec.vat.strip()):
                label = dict(self._fields['partner_type'].selection).get(
                    rec.partner_type, rec.partner_type)
                raise ValidationError(_(
                    'Khách hàng %s bắt buộc phải có Mã số thuế.') % label)

    @api.constrains('partner_role', 'vat')
    def _check_tax_code_format(self):
        """Mã số thuế nếu có nhập thì phải đúng định dạng 10 số hoặc 10 số-3 số."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            vat = (rec.vat or '').strip()
            if not vat:
                continue
            if not _TAX_CODE_RE.match(vat):
                raise ValidationError(_(
                    "Mã số thuế '%s' không hợp lệ. Mã số thuế chỉ gồm chữ số và dấu "
                    "'-', theo định dạng 10 chữ số (VD: 0123456789) hoặc 10 chữ "
                    'số-3 chữ số cho chi nhánh (VD: 0123456789-001).'
                ) % rec.vat)

    @api.constrains('partner_role', 'phone', 'mobile')
    def _check_phone_format(self):
        """Điện thoại và Di động của đối tác phải đúng định dạng số Việt Nam."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            for label, value in (('Điện thoại', rec.phone), ('Di động', rec.mobile)):
                if not value:
                    continue
                cleaned = re.sub(r'[\s.\-]', '', value)
                if not _PHONE_RE.match(cleaned):
                    raise ValidationError(_(
                        "%s '%s' không hợp lệ. Số điện thoại Việt Nam phải bắt "
                        'đầu bằng 0 hoặc +84 và gồm 10–11 chữ số, hoặc là tổng '
                        'đài 1800/1900.'
                    ) % (label, value))

    @api.constrains('partner_role', 'email')
    def _check_email_format(self):
        """Email của đối tác phải đúng định dạng."""
        for rec in self:
            if rec._dl_is_dlm_partner() and rec.email \
                    and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_("Email '%s' không hợp lệ.") % rec.email)

    def _dl_is_customer_person_contact(self):
        """Có phải dòng người liên hệ thật không, loại các bản ghi con dạng địa chỉ."""
        self.ensure_one()
        return self._dl_is_customer_contact() and self.type == 'contact'

    # ── Ràng buộc cho tab Người liên hệ trên form Khách hàng ───────────
    @api.constrains('parent_id', 'name')
    def _check_contact_name(self):
        """Dòng người liên hệ bắt buộc có Họ tên và đủ dài, tránh dòng rác trong lưới."""
        for rec in self:
            if not rec._dl_is_customer_person_contact():
                continue
            name = (rec.name or '').strip()
            if not name:
                raise ValidationError(_(
                    'Người liên hệ bắt buộc phải có Họ tên.'))
            if len(name) < _MIN_NAME_LEN:
                raise ValidationError(_(
                    "Họ tên người liên hệ '%s' quá ngắn — cần ít nhất %s ký tự."
                ) % (rec.name, _MIN_NAME_LEN))

    @api.constrains('parent_id', 'phone', 'mobile', 'email')
    def _check_contact_channel(self):
        """Dòng người liên hệ phải có ít nhất một trong Điện thoại, Di động, Email."""
        for rec in self:
            if not rec._dl_is_customer_person_contact():
                continue
            if not any((value or '').strip()
                       for value in (rec.phone, rec.mobile, rec.email)):
                raise ValidationError(_(
                    "Người liên hệ '%s' phải có ít nhất một kênh liên lạc: "
                    'Điện thoại, Di động hoặc Email.'
                ) % (rec.name or ''))

    @api.constrains('parent_id', 'dlm_name_key')
    def _check_contact_unique_name(self):
        """Chặn hai người liên hệ trùng tên trong cùng một khách hàng."""
        for rec in self:
            if not rec._dl_is_customer_person_contact() or not rec.dlm_name_key:
                continue
            dup = rec.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('parent_id', '=', rec.parent_id.id),
                ('dlm_name_key', '=', rec.dlm_name_key),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    "Khách hàng '%s' đã có người liên hệ tên '%s'. Mỗi người "
                    'liên hệ chỉ được khai một lần.'
                ) % (rec.parent_id.name or '', dup.name or ''))

    @api.constrains('parent_id', 'phone', 'mobile')
    def _check_contact_phone_format(self):
        """SĐT của người liên hệ nếu có nhập thì phải đúng định dạng Việt Nam."""
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
                        'Việt Nam phải bắt đầu bằng 0 hoặc +84 và gồm 10–11 chữ '
                        'số, hoặc là tổng đài 1800/1900.'
                    ) % (rec.name or '', label, value))

    @api.constrains('parent_id', 'email')
    def _check_contact_email_format(self):
        """Email của người liên hệ nếu có nhập thì phải đúng định dạng."""
        for rec in self:
            if rec._dl_is_customer_contact() and rec.email \
                    and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_(
                    "Người liên hệ '%s': Email '%s' không hợp lệ."
                ) % (rec.name or '', rec.email))

    @api.constrains('vat', 'partner_role', 'dlm_allow_dup_tax')
    def _check_unique_tax_code(self):
        """Chặn lưu khi Mã số thuế đã có đối tác khác dùng, trừ khi tích cho phép trùng."""
        for rec in self:
            if not rec._dl_is_dlm_partner() or not rec.vat or rec.dlm_allow_dup_tax:
                continue
            # Dò trên cả KH lẫn NCC: một MST chỉ thuộc một pháp nhân.
            dup = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('partner_role', '!=', False),
                ('parent_id', '=', False),
                ('vat', '=', rec.vat),
            ], limit=1)
            if dup:
                code = dup._dlm_display_code()
                ref = (' — ' + code) if code else ''
                raise ValidationError(
                    "Mã số thuế '%s' đã tồn tại trong hệ thống (khách hàng: "
                    "%s%s).\n"
                    'Nếu đây là chi nhánh khác dùng chung mã số thuế, hãy tích '
                    "'Cho phép trùng mã số thuế (chi nhánh khác)' và ghi chú lý do."
                    % (rec.vat, dup.name, ref)
                )

    @api.constrains('partner_role', 'phone', 'mobile', 'email',
                    'dlm_allow_dup_contact')
    def _check_unique_contact_channel(self):
        """Chặn hai khách hàng dùng chung SĐT hoặc Email, trừ khi tích cho phép trùng."""
        for rec in self:
            if not rec._dl_is_dlm_partner() or rec.dlm_allow_dup_contact:
                continue
            # Dò chéo cả hai ô vì cùng một số có thể nằm ở Điện thoại hoặc Di động.
            phones = {p for p in (rec.phone, rec.mobile) if p}
            for phone in phones:
                dup = rec.with_context(active_test=False).search([
                    ('id', '!=', rec.id),
                    ('partner_role', 'in', _CUSTOMER_ROLES),
                    ('parent_id', '=', False),
                    '|', ('phone', '=', phone), ('mobile', '=', phone),
                ], limit=1)
                if dup:
                    raise ValidationError(rec._dlm_dup_contact_message(
                        _('Số điện thoại'), phone, dup))
            if rec.email:
                dup = rec.with_context(active_test=False).search([
                    ('id', '!=', rec.id),
                    ('partner_role', 'in', _CUSTOMER_ROLES),
                    ('parent_id', '=', False),
                    ('email', '=', rec.email),
                ], limit=1)
                if dup:
                    raise ValidationError(rec._dlm_dup_contact_message(
                        _('Email'), rec.email, dup))

    _DUP_OVERRIDE_FLAGS = ('dlm_allow_dup_tax', 'dlm_allow_dup_contact')

    def _dlm_check_dup_override_reason(self, vals):
        """Bắt nhập Lý do khi lần ghi này mới bật cờ cho phép trùng (bản ghi cũ không bị đòi)."""
        turning_on = [f for f in self._DUP_OVERRIDE_FLAGS if vals.get(f)]
        if not turning_on:
            return
        reason = vals.get('dlm_dup_override_reason')
        records = self or [None]
        for rec in records:
            newly_on = turning_on if rec is None else [
                f for f in turning_on if not rec[f]]
            if not newly_on:
                continue
            current = reason if reason is not None else (
                rec.dlm_dup_override_reason if rec is not None else None)
            if not (current or '').strip():
                raise ValidationError(_(
                    'Đã tích cho phép trùng dữ liệu thì bắt buộc ghi Lý do cho '
                    'phép trùng (vd: chi nhánh khác cùng Mã số thuế, dùng '
                    'chung tổng đài).'))

    @api.model
    def _dlm_check_dup_override_right(self):
        """Chỉ Trưởng phòng Kinh doanh, Mua hàng hoặc Admin được tích cờ cho phép trùng."""
        user = self.env.user
        if not (user.has_group('dl_base.dl_group_admin')
                or user.has_group('dl_base.dl_group_sales_manager')
                or user.has_group('dl_base.dl_group_purchasing')):
            raise AccessError(_(
                'Chỉ Trưởng phòng Kinh doanh, Mua hàng hoặc Admin mới được cho '
                'phép trùng Mã số thuế / Số điện thoại / Email. Hãy báo quản '
                'lý nếu đây thật sự '
                'không phải hồ sơ trùng.'))

    def _dlm_dup_contact_message(self, label, value, dup):
        """Dựng câu thông báo trùng SĐT / Email, kèm tên và mã đối tác đang giữ giá trị đó."""
        code = dup._dlm_display_code()
        ref = (' — %s' % code) if code else ''
        return _(
            "%s '%s' đã được dùng bởi khách hàng khác (%s%s).\n"
            "Nếu đây đúng là hai khách dùng chung tổng đài / hộp thư, hãy tích "
            "'Cho phép trùng SĐT / Email'."
        ) % (label, value, dup.name, ref)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Ô tìm đối tác để gộp chỉ gợi ý đúng vai trò cần liên kết."""
        role = self.env.context.get('dl_link_search_role')
        if role:
            domain = (args or []) + [('partner_role', '=', role), ('active', '=', True)]
            partners = self.sudo().search(
                domain + [('name', operator, name)], limit=limit
            )
            return [(p.id, p.name) for p in partners]
        return super().name_search(name=name, args=args, operator=operator, limit=limit)

    def get_formview_id(self, access_uid=None):
        """Bấm vào đối tác từ màn khác thì mở đúng form KH hay form NCC theo vai trò."""
        if self.partner_role in _CUSTOMER_ROLES:
            return self.env.ref('dl_partner.view_dl_customer_form').id
        elif self.partner_role == 'supplier':
            return self.env.ref('dl_partner.view_dl_supplier_form').id
        return super().get_formview_id(access_uid=access_uid)

    def get_formview_action(self, access_uid=None):
        """Mở đối tác bằng action có sẵn theo vai trò, để F5 hay back vẫn giữ đúng form."""
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
        """Sau khi lưu link gộp: đẩy đối tác đích lên vai trò 'both' và ghi log hai bên."""
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
                    "Được gộp vai trò 'Khách hàng & Nhà cung cấp' — liên kết từ '%s' (bởi %s)"
                ) % (rec.name, self.env.user.name))
            rec.message_post(body=_(
                "Đã liên kết với đối tác trùng tên: %s → partner_role đã chuyển 'both'."
            ) % target.name)
            rec.pending_link_partner_id = False
