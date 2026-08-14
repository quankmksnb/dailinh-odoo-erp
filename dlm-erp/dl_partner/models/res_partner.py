import re
import unicodedata

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

# SĐT Việt Nam: số di động / cố định bắt đầu bằng 0 hoặc +84, HOẶC tổng đài
# 1800/1900 (4–6 chữ số sau đầu số). Nhánh tổng đài là bắt buộc kể từ khi mở
# validate cho màn NCC: doanh nghiệp lớn thường chỉ công bố hotline (Hòa Phát
# 1800 1755), chặn nó là ép người dùng nhập số sai để lách.
_PHONE_RE = re.compile(r'^(?:(?:0|\+84)\d{9,10}|(?:1800|1900)\d{4,6})$')
_EMAIL_RE = re.compile(r'^[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}$')
# MST: 10 chữ số, hoặc 10 chữ số-3 chữ số (mã chi nhánh). Chỉ số và dấu '-'.
# Đồng bộ với widget frontend dl_partner/static/src/fields/tax_code_field.js.
_TAX_CODE_RE = re.compile(r'^\d{10}(-\d{3})?$')
_CUSTOMER_ROLES = ('customer', 'both')

# Độ dài tối thiểu của Tên khách hàng — chặn các giá trị rác kiểu 'a', '..'
# lọt qua khi import hàng loạt.
_MIN_NAME_LEN = 2
# Loại khách hàng có tư cách pháp nhân: bắt buộc địa chỉ vì địa chỉ được in lên
# báo giá / hợp đồng gửi ra ngoài.
_LEGAL_ENTITY_TYPES = ('company', 'dealer')

# Field mà luồng "gộp hồ sơ" (pending_link_partner_id) quản lý. Onchange chép
# giá trị của đối tác đích vào form để người dùng soát rồi sửa, và khi lưu thì
# ghi ĐÚNG bấy nhiêu field đó ngược lại.
#
# Phải dùng CHUNG một danh sách cho cả hai chiều. Trước đây onchange chép 11
# field còn lúc lưu thì ghi MỌI field có trong vals — nên `partner_type` (không
# nằm trong danh sách chép, vẫn mang giá trị mặc định của form đang mở) bị đẩy
# đè lên đối tác đích. Gộp từ màn NCC làm khách Doanh nghiệp tụt xuống Cá nhân.
_MERGE_FIELDS = (
    'name', 'phone', 'mobile', 'email', 'website', 'vat',
    'street', 'street2', 'city', 'country_id', 'comment',
)

# ── Chuẩn hóa dữ liệu trước khi lưu ────────────────────────────────────────
# Lý do tồn tại: các ràng buộc định dạng phía dưới chỉ BÓC dấu phân cách để
# *kiểm tra*, còn giá trị lưu xuống DB vẫn là chuỗi thô người dùng gõ. Hệ quả:
# '0912 345 678', '0912.345.678' và '+84912345678' nằm trong DB thành ba chuỗi
# khác nhau ⇒ mọi phép chống trùng đều vô hiệu. Chuẩn hóa tại điểm ghi để DB
# chỉ có đúng MỘT dạng biểu diễn cho mỗi giá trị.
_PHONE_SEP_RE = re.compile(r'[\s.\-()]')
_MULTI_SPACE_RE = re.compile(r'\s+')
# Ký tự bỏ đi khi dựng "khóa tên" dùng để dò trùng: giữ lại chữ và số.
_NAME_KEY_STRIP_RE = re.compile(r'[^a-z0-9]+')


def _normalize_phone(value):
    """'0912 345 678' / '0912.345.678' / '+84912345678' → '0912345678'.

    Quy '+84' về '0' để hai cách viết cùng một số không thành hai bản ghi.
    KHÔNG kiểm tính hợp lệ ở đây — đó là việc của _check_phone_format."""
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


# Tiền tố pháp nhân bỏ qua khi lấy chữ cái avatar. Gần như MỌI pháp nhân Việt
# Nam mở đầu bằng "Công ty", nên lấy thẳng ký tự đầu cho ra cả danh sách avatar
# chữ 'C' giống hệt nhau — mất sạch tác dụng phân biệt dòng. Xếp dài trước ngắn
# để "Công ty Cổ phần" được cắt trọn thay vì dừng ở "Cổ".
# Bản JS song song: dl_base/static/src/js/avatar_letter.js — sửa thì sửa cả hai.
_NAME_PREFIXES = (
    'công ty cổ phần', 'công ty tnhh mtv', 'công ty tnhh', 'công ty cp',
    'công ty', 'tổng công ty', 'doanh nghiệp tư nhân', 'hộ kinh doanh',
    'cửa hàng', 'cty tnhh', 'cty cp', 'cty', 'tnhh mtv', 'tnhh', 'cp',
    'dntn', 'hkd', 'xưởng', 'nhà máy', 'tập đoàn', 'chi nhánh',
)
_PREFIX_TRIM_RE = re.compile(r'^[\s.,\-–—]+')


def _significant_name(value):
    """Phần tên còn lại sau khi bỏ hết tiền tố pháp nhân ở đầu.

    'Công ty TNHH Việt Hưng' → 'Việt Hưng'. Lặp vì tên có thể chồng nhiều tầng
    tiền tố. Không cắt khi phần còn lại rỗng — tên chỉ gồm mỗi tiền tố thì thà
    giữ nguyên còn hơn trả về chuỗi trống."""
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
    """Khóa so khớp tên: bỏ dấu tiếng Việt, hạ chữ thường, bỏ mọi ký tự không
    phải chữ/số. 'Công ty  TNHH  A.B.C' và 'CONG TY TNHH ABC' ra cùng một khóa.

    Dùng để CẢNH BÁO trùng tên, không dùng để chặn — tên doanh nghiệp trùng
    nhau là chuyện có thật."""
    if not value:
        return False
    text = unicodedata.normalize('NFD', value)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    # 'đ'/'Đ' không tách được bằng NFD nên xử riêng.
    text = text.replace('đ', 'd').replace('Đ', 'D')
    key = _NAME_KEY_STRIP_RE.sub('', text.lower())
    return key or False


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

    # ── Mã NCC tự sinh NCC-0001 ───────────────────────────────────────
    # Field RIÊNG chứ không dùng chung dlm_code: đối tác vai trò 'Khách hàng &
    # NCC' tham gia hai quan hệ nên có hai mã, và mỗi màn hiện đúng mã của mình.
    # Gộp một field sẽ khiến màn NCC hiển thị 'KH-0008' cho đối tác từng được
    # tạo ở màn khách hàng.
    dlm_supplier_code = fields.Char(
        string='Mã NCC',
        readonly=True,
        copy=False,
        index=True,
        help='Mã nhà cung cấp tự sinh, duy nhất (VD: NCC-0001)',
    )

    # Bảng giá NCC cung cấp — cho form NCC trả lời được câu hỏi thường trực của
    # Mua hàng: "đơn vị này cung cấp gì, giá bao nhiêu". Trước đây phải sang màn
    # Bảng giá Vật tư rồi tự lọc theo tên.
    dlm_supplierinfo_ids = fields.One2many(
        'product.supplierinfo', 'partner_id',
        string='Bảng giá cung cấp', readonly=True,
    )
    dlm_supplierinfo_count = fields.Integer(
        string='Số dòng bảng giá', compute='_compute_dlm_supplierinfo_count',
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

    # Chống trùng kênh liên lạc — song song với dlm_allow_dup_tax. Cần cửa
    # thoát vì có thật: nhóm công ty dùng chung tổng đài, hoặc hai chi nhánh
    # cùng một hộp thư đặt hàng.
    dlm_allow_dup_contact = fields.Boolean(
        string='Cho phép trùng SĐT / Email',
        default=False,
        help='Tích khi khách này dùng chung tổng đài hoặc hộp thư với một khách '
             'đã có — bỏ qua kiểm tra trùng SĐT/Email.',
    )

    # Cửa thoát trùng dữ liệu phải để lại dấu vết. Trước đây tích
    # dlm_allow_dup_tax là bỏ qua toàn bộ kiểm tra trùng MST mà không ai phải
    # giải thích gì — chính thông báo lỗi có câu "và ghi chú lý do" nhưng hệ
    # thống không hề bắt buộc.
    dlm_dup_override_reason = fields.Text(
        string='Lý do cho phép trùng',
        help='Bắt buộc khi tích cho phép trùng MST hoặc trùng SĐT/Email. '
             'Ghi rõ vì sao đây không phải hồ sơ trùng lặp.',
    )

    # Khóa tên đã bỏ dấu — LƯU và đánh index để dò trùng bằng một phép so bằng
    # trên index, thay vì quét ilike toàn bảng khách hàng.
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
        # sudo: Mua hàng đọc được bảng giá, nhưng CEO/Trưởng KD mở form NCC ở
        # chế độ xem cũng cần thấy con số thay vì lỗi quyền.
        for rec in self:
            rec.dlm_supplierinfo_count = self.env['product.supplierinfo'].sudo(
            ).search_count([('partner_id', '=', rec.id)])

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
            # Bỏ tiền tố pháp nhân trước khi lấy chữ cái — xem _significant_name.
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
        for rec in self:
            rec.dlm_name_key = _name_key(rec.name)

    @api.depends('dlm_name_key', 'partner_role')
    def _compute_dlm_duplicate_name_warning(self):
        """Cảnh báo MỀM khi tên trùng một khách hàng đã có (bỏ dấu, bỏ hoa
        thường, bỏ dấu câu). Không chặn: hai doanh nghiệp trùng tên là chuyện
        có thật, và người nhập là người biết rõ nhất."""
        for rec in self:
            rec.dlm_duplicate_name_warning = False
            if not rec.dlm_name_key or rec.parent_id or not rec.partner_role:
                continue
            # Chỉ soi trong CÙNG vai trò: một pháp nhân vừa bán vừa mua là
            # chuyện bình thường, cảnh báo chéo hai màn chỉ gây nhiễu. Trùng
            # MST giữa hai vai trò đã có ràng buộc riêng bắt gộp hồ sơ.
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
        mapping = dict(self._fields['partner_type'].selection)
        for rec in self:
            rec.partner_type_label = mapping.get(rec.partner_type, '')

    @api.onchange('pending_link_partner_id')
    def _onchange_pending_link_partner(self):
        if self.pending_link_partner_id:
            target = self.pending_link_partner_id.sudo()
            for f in _MERGE_FIELDS:
                self[f] = target[f]

    # ── Chuẩn hóa tại điểm ghi ────────────────────────────────────────
    # Hàm chuẩn hóa theo field. Để trong dict (không phải method) nên KHÔNG bị
    # bind vào instance — gọi thẳng như hàm thường.
    _DLM_NORMALIZERS = {
        'name': _normalize_name,
        'phone': _normalize_phone,
        'mobile': _normalize_phone,
        'email': _normalize_email,
    }

    def _dlm_normalize_vals(self, vals):
        """Chuẩn hóa tại chỗ các field trong vals. Chỉ đụng vào field có mặt
        trong vals và đang là chuỗi — không tự điền, không xóa dữ liệu."""
        for fname, normalize in self._DLM_NORMALIZERS.items():
            if isinstance(vals.get(fname), str):
                vals[fname] = normalize(vals[fname])
        return vals

    @api.model
    def _dlm_vals_in_customer_scope(self, vals):
        """vals này đang tạo một KH DLM, hay một người liên hệ của KH DLM?

        Chỉ chuẩn hóa trong phạm vi khách hàng — không tự ý viết lại dữ liệu
        NCC hay các partner do module khác của Odoo tạo."""
        if vals.get('partner_role'):
            return True
        parent_id = vals.get('parent_id')
        if parent_id:
            parent = self.browse(parent_id).sudo()
            return parent.commercial_partner_id.partner_role in _CUSTOMER_ROLES
        return False

    @api.model_create_multi
    def create(self, vals_list):
        to_create = []
        linked_records = self.browse()
        for vals in vals_list:
            # Chuẩn hóa TRƯỚC mọi thứ: nhánh gộp hồ sơ bên dưới chép thẳng vals
            # sang partner đích, phải chép giá trị đã chuẩn hóa.
            if self._dlm_vals_in_customer_scope(vals):
                self._dlm_normalize_vals(vals)
            if not self.env.su and (vals.get('dlm_allow_dup_tax')
                                    or vals.get('dlm_allow_dup_contact')):
                self._dlm_check_dup_override_right()
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
                # CHỈ ghi các field thuộc luồng gộp — xem chú thích _MERGE_FIELDS.
                write_vals = {k: v for k, v in vals.items() if k in _MERGE_FIELDS}
                write_vals['partner_role'] = 'both'
                # partner_type KHÔNG nằm trong _MERGE_FIELDS nên không bao giờ bị
                # đè; chỉ điền khi đối tác đích còn trống (NCC cũ chưa phân loại).
                if not target.partner_type:
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
                if rec.dlm_supplier_code:
                    fix['dlm_supplier_code'] = False
                if fix:
                    rec.write(fix)
                continue
        created._dlm_assign_codes()
        return created + linked_records

    # ── Mã đối tác tự sinh ────────────────────────────────────────────
    # Mỗi vai trò một dãy mã riêng; đối tác 'both' nhận cả hai.
    _DLM_CODE_SEQUENCES = (
        ('dlm_code', _CUSTOMER_ROLES, 'dlm.customer'),
        ('dlm_supplier_code', ('supplier', 'both'), 'dlm.supplier'),
    )

    def _dlm_assign_codes(self):
        """Cấp mã còn thiếu cho các đối tác trong recordset.

        Gọi cả ở create lẫn write nên tự vá được hai trường hợp mà cấp mã lúc
        tạo không phủ: đối tác đổi vai trò về sau (NCC được gộp thành 'Khách
        hàng & NCC' thì cần thêm mã KH), và bản ghi cũ có từ trước khi dãy mã
        tương ứng ra đời — lần lưu kế tiếp là có mã, không cần script vá dữ liệu.

        Ghi đè lên write() sẽ gọi lại chính hàm này, nhưng vòng thứ hai thấy mã
        đã có nên dừng — không đệ quy vô hạn."""
        sequences = self.env['ir.sequence'].sudo()
        for rec in self:
            if rec.parent_id or not rec.partner_role:
                continue
            for fname, roles, seq_code in self._DLM_CODE_SEQUENCES:
                if rec.partner_role in roles and not rec[fname]:
                    rec[fname] = sequences.next_by_code(seq_code) or '/'

    def _dlm_display_code(self):
        """Mã để nhắc tới đối tác này trong thông báo — ưu tiên mã đúng vai trò
        của bản ghi, để lỗi trên màn NCC không hiện mã KH."""
        self.ensure_one()
        if self.partner_role == 'supplier':
            return self.dlm_supplier_code or ''
        return self.dlm_code or self.dlm_supplier_code or ''

    def write(self, vals):
        # Chuẩn hóa nếu recordset có dính KH DLM hoặc người liên hệ của KH.
        # Dùng any(): write áp CÙNG một vals cho cả recordset nên không thể
        # chuẩn hóa riêng từng bản ghi; trong thực tế các đường ghi hỗn hợp
        # KH + NCC là không có (mỗi màn chỉ thao tác một vai trò).
        if any(rec._dl_is_dlm_partner() or rec._dl_is_customer_contact()
               for rec in self):
            self._dlm_normalize_vals(vals)
        if 'active' in vals and not vals['active'] and not self.env.su:
            for rec in self:
                # Người liên hệ và partner do module khác của Odoo tạo không
                # thuộc phạm vi luật này.
                if not rec.partner_role or rec.parent_id:
                    continue
                rec._dlm_check_archive_right()
                # Kiểm ĐIỀU KIỆN: áp cho MỌI đối tác DLM, cả NCC. Quyền là một
                # chuyện, việc dở dang là chuyện khác — ngừng hợp tác khi còn
                # báo giá / đơn / phiếu nhập đang chạy sẽ làm chứng từ đó mắc
                # kẹt (đối tác biến khỏi mọi ô chọn). side=None để đối tác vai
                # trò 'both' bị soi cả hai phía.
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
        if 'partner_role' in vals and not self.env.su:
            self._dlm_check_role_downgrade(vals['partner_role'])
        res = super().write(vals)
        self._dlm_assign_codes()
        if 'pending_link_partner_id' in vals:
            self._process_pending_link()
        return res

    def _dlm_check_archive_right(self):
        """Ai được vô hiệu hóa (ngừng hợp tác với) đối tác này.

        Chia theo bộ phận SỞ HỮU quan hệ với đối tác:
          • Khách hàng  → Trưởng phòng Kinh doanh (Kế toán chỉ với đối tác vai
            trò 'both' — luật có sẵn từ trước, giữ nguyên).
          • Nhà cung cấp → Mua hàng, đúng bộ phận đang giữ giá mua và quan hệ
            NCC (xem comment nhóm dl_group_purchasing ở dl_base/security/groups.xml).
          • Admin/IT     → luôn được, như mọi luật quyền khác trong hệ thống.

        Đối tác vai trò 'both': đủ quyền MỘT phía là được, không bắt phải có cả
        hai. Giữ đúng tinh thần nới lỏng của luật cũ, vốn đã cho Kế toán vô hiệu
        hóa đối tác 'both' dù họ không phải Trưởng phòng Kinh doanh."""
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
        """Chặn bỏ bớt vai trò khi vai trò bị bỏ vẫn còn chứng từ tham chiếu.

        Đối tác 'both' hạ về 'customer' là BỎ vai trò NCC. Nếu vẫn còn bảng giá
        NCC hay phiếu nhập trỏ tới, những chứng từ đó lập tức rơi khỏi domain
        của mọi màn NCC — không xóa, không báo, chỉ là không ai thấy nữa."""
        # Vai trò bị bỏ đi khi chuyển từ vai trò cũ sang vai trò mới.
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
        """Không xóa đối tác đã phát sinh chứng từ — hướng sang Ngừng hợp tác.

        `dl.quotation.partner_id` và nhiều tham chiếu khác KHÔNG khai
        ondelete='restrict', nên xóa đối tác sẽ để lại chứng từ mồ côi trỏ vào
        khoảng không. Chặn ở đây thay vì rải ondelete lên từng field: chỉ cần
        một chỗ, và thông báo nói rõ vướng cái gì."""
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
        """Các model chứng từ có thể trỏ tới đối tác, kèm cách đếm.

        Khai bảng TẠI ĐÂY thay vì để mỗi module nghiệp vụ tự _inherit
        res.partner: mọi thứ liên quan tới đối tác nằm gọn trong dl_partner.

        dl_partner đứng đầu đồ thị phụ thuộc nên KHÔNG depends dl_sale /
        dl_technical / dl_inventory. Không sao: model chưa cài thì không có
        trong registry và bị bỏ qua — kiểm bằng `not in self.env`, không import.

        Khóa của mỗi dòng:
            model / field  — model chứng từ và field trỏ tới đối tác.
            side           — 'customer' hay 'supplier'; quyết định chứng từ này
                             thuộc vai trò nào khi hạ vai trò đối tác.
            label          — danh từ đếm được, ghép sau số lượng.
            open_domain    — điều kiện "chưa đóng"; [] nghĩa là luôn tính là mở.
            extra_domain   — điều kiện thu hẹp cố định (vd tách phiếu nhập/xuất).
            active_test    — False để đếm cả bản ghi đã lưu trữ.
        """
        sources = [
            {
                'model': 'dl.quotation', 'field': 'partner_id',
                'side': 'customer', 'label': 'báo giá',
                'open_label': 'báo giá chưa đóng',
                # Đóng = ordered / rejected / expired / superseded / cancelled.
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
                # Đóng = quoted (đã chuyển sang báo giá) / cancelled.
                'open_domain': [('status', 'in', (
                    'new', 'processing', 'returned', 'supplemented',
                    'confirmed'))],
            },
            {
                'model': 'product.supplierinfo', 'field': 'partner_id',
                'side': 'supplier', 'label': 'dòng bảng giá NCC',
                # Chỉ bảng giá ĐANG ÁP DỤNG mới cản: đó là giá đang được dùng
                # để tính báo giá và BOM. Nháp / Đã duyệt chưa áp dụng thì không.
                'open_label': 'bảng giá NCC đang áp dụng',
                'open_domain': [('is_applied', '=', True)],
                # Bảng giá đã lưu trữ vẫn là tham chiếu thật — xóa NCC đi thì nó
                # mồ côi y như bảng giá đang hoạt động.
                'active_test': False,
            },
            # Phiếu kho tách hai chiều theo `code` native của loại hoạt động,
            # KHÔNG theo sequence_code riêng của Đại Linh: code chỉ có 3 giá trị
            # và không đổi khi bố cục kho thêm loại hoạt động mới.
            {
                'model': 'stock.picking', 'field': 'partner_id',
                'side': 'customer', 'label': 'phiếu giao hàng',
                'open_label': 'phiếu giao hàng chưa hoàn tất',
                'extra_domain': [('picking_type_id.code', '=', 'outgoing')],
                'open_domain': [('state', 'not in', ('done', 'cancel'))],
            },
            {
                'model': 'stock.picking', 'field': 'partner_id',
                'side': 'supplier', 'label': 'phiếu nhập / trả NCC',
                'open_label': 'phiếu nhập / trả NCC chưa hoàn tất',
                'extra_domain': [('picking_type_id.code', '=', 'incoming')],
                'open_domain': [('state', 'not in', ('done', 'cancel'))],
            },
        ]
        for src in sources:
            if side and src['side'] != side:
                continue
            if src['model'] not in self.env:
                continue
            # sudo: người bấm xóa / đổi vai trò có thể không có quyền đọc chứng
            # từ (Kỹ thuật không đọc được báo giá, Sales không đọc được phiếu
            # kho) — nhưng vẫn phải bị chặn đúng.
            model = self.env[src['model']].sudo()
            if src.get('active_test') is False:
                model = model.with_context(active_test=False)
            yield src, model

    def _dlm_count_documents(self, side, only_open):
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
        """MỌI chứng từ đang trỏ tới đối tác này, kể cả đã đóng.

        :param side: 'customer' chỉ đếm chứng từ phía khách hàng, 'supplier'
            chỉ đếm phía nhà cung cấp, None đếm cả hai.
        :return: list mô tả ngắn, vd ['3 báo giá', '1 đơn bán hàng'].
        """
        return self._dlm_count_documents(side, only_open=False)

    def _dlm_open_document_summary(self, side=None):
        """Chứng từ CHƯA đóng — đang chờ xử lý tiếp.

        Khác _dlm_reference_summary ở chỗ chỉ tính việc còn dang dở: dùng cho
        Ngừng hợp tác (chứng từ cũ đã đóng thì ngừng hợp tác là hợp lệ)."""
        return self._dlm_count_documents(side, only_open=True)

    # ── Constraints ───────────────────────────────────────────────────
    def _dl_is_customer_record(self):
        """Bản ghi này có phải KH DLM (đối tượng của các ràng buộc KH) không?

        Chỉ đúng với KH cấp cao (top-level). Người liên hệ (child_ids) cũng là
        res.partner nhưng có `parent_id` — KHÔNG phải KH DLM, dù default
        'customer'/'company' của action có rò xuống. Nếu không loại chúng ra,
        contact rỗng MST sẽ dính ràng buộc 'Doanh nghiệp bắt buộc có MST'."""
        self.ensure_one()
        return self.partner_role in _CUSTOMER_ROLES and not self.parent_id

    def _dl_is_dlm_partner(self):
        """Bản ghi này có phải một ĐỐI TÁC DLM cấp cao (khách hàng HOẶC NCC)?

        Dùng cho các ràng buộc KHÔNG phụ thuộc vai trò — tên, định dạng SĐT /
        email / MST, chống trùng. Sai định dạng hay trùng MST thì phía NCC cũng
        hỏng y như phía khách hàng, thậm chí nặng hơn vì MST NCC dùng để đối
        chiếu hóa đơn đầu vào.

        Loại trừ người liên hệ (parent_id) và partner không mang vai trò DLM
        (res.users, res.company đều kế thừa res.partner với partner_role rỗng)."""
        self.ensure_one()
        return bool(self.partner_role) and not self.parent_id

    def _dl_is_supplier_record(self):
        self.ensure_one()
        return self.partner_role in ('supplier', 'both') and not self.parent_id

    def _dl_partner_kind_label(self):
        """'Khách hàng' / 'Nhà cung cấp' / 'Đối tác' — để thông báo lỗi gọi đúng
        tên thứ người dùng đang nhìn trên màn hình."""
        self.ensure_one()
        if self.partner_role == 'customer':
            return _('Khách hàng')
        if self.partner_role == 'supplier':
            return _('Nhà cung cấp')
        return _('Đối tác')

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

    @api.constrains('partner_role', 'name')
    def _check_partner_name(self):
        """Tên đối tác bắt buộc ở tầng MODEL, không chỉ ở form. Áp cho cả khách
        hàng lẫn NCC.

        `res.partner.name` của Odoo native KHÔNG khai required — form có
        required="1" nhưng import Excel, gọi RPC hay create() từ code vẫn tạo
        được đối tác tên rỗng / toàn khoảng trắng. Chặn ở đây để mọi đường ghi
        cùng đi qua một luật."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            kind = rec._dl_partner_kind_label()
            name = (rec.name or '').strip()
            if not name:
                raise ValidationError(_('%s bắt buộc phải có Tên.') % kind)
            if len(name) < _MIN_NAME_LEN:
                raise ValidationError(_(
                    "Tên '%s' quá ngắn — cần ít nhất %s ký tự."
                ) % (rec.name, _MIN_NAME_LEN))

    @api.constrains('partner_role', 'partner_type', 'phone', 'mobile', 'email')
    def _check_partner_contact_channel(self):
        """Đối tác phải có ít nhất một kênh liên lạc. Áp cho cả khách hàng lẫn
        NCC — một NCC không gọi được thì không đặt hàng được.

        Riêng đối tác Cá nhân bắt buộc Di động: cá nhân không có MST nên số di
        động là dữ liệu duy nhất định danh được họ (và cũng là căn cứ chống
        trùng hồ sơ). Doanh nghiệp / Đại lý thì linh hoạt hơn — điện thoại bàn
        hoặc email đều nhận."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            if rec.partner_type == 'individual':
                if not (rec.mobile and rec.mobile.strip()):
                    raise ValidationError(_(
                        '%s loại Cá nhân bắt buộc phải có số Di động.'
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
        """Khách Doanh nghiệp / Đại lý bắt buộc có địa chỉ (đường + tỉnh/TP).

        Địa chỉ được in lên PDF báo giá và hợp đồng. Trước đây chỉ có cảnh báo
        mềm lúc gửi báo giá (dl.quotation.customer_data_warning) — phát hiện quá
        muộn, khi Sales đã dựng xong báo giá. Chặn ngay từ màn khách hàng."""
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
        """MST bắt buộc với khách có tư cách pháp nhân — Doanh nghiệp và Đại lý.

        Dùng trên PDF báo giá S09. Đại lý cũng là pháp nhân xuất hóa đơn nên
        chịu cùng luật với Doanh nghiệp; chỉ khách Cá nhân được để trống MST
        (nhập vào thì vẫn phải đúng định dạng — xem _check_tax_code_format)."""
        for rec in self:
            if rec._dl_is_customer_record() \
                    and rec.partner_type in _LEGAL_ENTITY_TYPES \
                    and not (rec.vat and rec.vat.strip()):
                label = dict(self._fields['partner_type'].selection).get(
                    rec.partner_type, rec.partner_type)
                raise ValidationError(_(
                    'Khách hàng %s bắt buộc phải có Mã số thuế (MST).') % label)

    @api.constrains('partner_role', 'vat')
    def _check_tax_code_format(self):
        """Định dạng MST: chỉ chữ số và dấu '-', theo mẫu 10 số hoặc 10 số-3 số.
        Áp cho cả Doanh nghiệp lẫn Cá nhân — Cá nhân KHÔNG bắt buộc nhập, nhưng
        nếu đã nhập thì vẫn phải đúng định dạng."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
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
        for rec in self:
            if rec._dl_is_dlm_partner() and rec.email \
                    and not _EMAIL_RE.match(rec.email.strip()):
                raise ValidationError(_("Email '%s' không hợp lệ.") % rec.email)

    def _dl_is_customer_person_contact(self):
        """NGƯỜI liên hệ của KH — loại trừ bản ghi con dạng ĐỊA CHỈ.

        res.partner con còn được Odoo dùng làm địa chỉ giao hàng / xuất hóa đơn
        (`type` = delivery / invoice / other). Những bản ghi đó không có tên
        người và không cần SĐT, nên các ràng buộc 'bắt buộc họ tên', 'bắt buộc
        kênh liên lạc' chỉ áp cho `type = 'contact'`.

        Khác _dl_is_customer_contact (áp cho MỌI bản ghi con, dùng cho ràng
        buộc định dạng — địa chỉ có nhập SĐT thì cũng phải đúng định dạng)."""
        self.ensure_one()
        return self._dl_is_customer_contact() and self.type == 'contact'

    # ── Người liên hệ của KH: cùng chuẩn định dạng SĐT/email như KH ─────
    @api.constrains('parent_id', 'name')
    def _check_contact_name(self):
        """Người liên hệ bắt buộc có họ tên.

        Cùng lý do như _check_customer_name: `res.partner.name` của Odoo native
        không required, mà dòng người liên hệ lại nhập inline trong lưới nên rất
        dễ để trống rồi lưu — sinh ra dòng trắng không xóa ai dám xóa."""
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
        """Người liên hệ phải có ít nhất một kênh liên lạc.

        Một người liên hệ không có cách nào liên lạc thì không phục vụ được mục
        đích nào — chỉ làm rối danh sách khi Sales cần gọi cho khách."""
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
        """Không cho hai người liên hệ trùng tên trong cùng một khách hàng.

        So trên dlm_name_key (đã bỏ dấu, bỏ hoa thường, bỏ dấu câu) nên
        'Nguyễn Văn A' và 'NGUYEN VAN A' bị coi là một. Khác với trùng tên ở
        cấp khách hàng — chỗ đó chỉ cảnh báo mềm — ở đây chặn hẳn: trong cùng
        một công ty thì hai người liên hệ trùng tên gần như chắc chắn là nhập
        lặp, và Sales không có cách nào phân biệt khi chọn."""
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
                        'Việt Nam phải bắt đầu bằng 0 hoặc +84 và gồm 10–11 chữ '
                        'số, hoặc là tổng đài 1800/1900.'
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
            if not rec._dl_is_dlm_partner() or not rec.vat or rec.dlm_allow_dup_tax:
                continue
            # Tìm trên MỌI đối tác DLM, không riêng cùng vai trò: một MST chỉ
            # thuộc về một pháp nhân, nên khách hàng và NCC trùng MST nghĩa là
            # cùng một đơn vị và phải gộp thành vai trò 'Khách hàng & NCC'.
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
                    "MST '%s' đã tồn tại trong hệ thống (KH: %s%s).\n"
                    'Nếu đây là chi nhánh khác dùng chung MST, hãy tích '
                    "'Cho phép trùng MST (chi nhánh khác)' và ghi chú lý do."
                    % (rec.vat, dup.name, ref)
                )

    @api.constrains('partner_role', 'phone', 'mobile', 'email',
                    'dlm_allow_dup_contact')
    def _check_unique_contact_channel(self):
        """Chặn hai hồ sơ khách hàng dùng chung SĐT hoặc Email.

        Bổ khuyết cho _check_unique_tax_code: khách Cá nhân không có MST nên
        trước đây nhập trùng thoải mái. Hồ sơ trùng làm hỏng luôn phân loại
        khách (dlm_customer_group ở dl_sale) vì doanh số bị chia đôi giữa hai
        bản ghi nên không bao giờ lên nổi 'Khách thân thiết'.

        So sánh trên giá trị ĐÃ chuẩn hóa (_dlm_normalize_vals chạy ở create/
        write), nếu không thì '0912 345 678' và '0912345678' lọt lưới."""
        for rec in self:
            if not rec._dl_is_dlm_partner() or rec.dlm_allow_dup_contact:
                continue
            # SĐT: một số có thể nằm ở ô Điện thoại của người này và ô Di động
            # của người kia — vẫn là trùng, nên dò chéo cả hai ô.
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

    @api.constrains('dlm_allow_dup_tax', 'dlm_allow_dup_contact',
                    'dlm_dup_override_reason')
    def _check_dup_override_reason(self):
        """Tích cho phép trùng thì phải nói rõ vì sao."""
        for rec in self:
            if not rec._dl_is_dlm_partner():
                continue
            if (rec.dlm_allow_dup_tax or rec.dlm_allow_dup_contact) \
                    and not (rec.dlm_dup_override_reason or '').strip():
                raise ValidationError(_(
                    'Đã tích cho phép trùng dữ liệu thì bắt buộc ghi Lý do cho '
                    'phép trùng (vd: chi nhánh khác cùng MST, dùng chung tổng đài).'))

    @api.model
    def _dlm_check_dup_override_right(self):
        """Chỉ Trưởng phòng Kinh doanh / Admin được mở cửa thoát trùng.

        Cùng cấp quyền với việc vô hiệu hóa khách hàng: đều là quyết định làm
        sai lệch chất lượng dữ liệu danh mục, không để nhân viên nhập liệu tự
        quyết khi gặp thông báo chặn."""
        user = self.env.user
        if not (user.has_group('dl_base.dl_group_admin')
                or user.has_group('dl_base.dl_group_sales_manager')
                or user.has_group('dl_base.dl_group_purchasing')):
            raise AccessError(_(
                'Chỉ Trưởng phòng Kinh doanh, Mua hàng hoặc Admin mới được cho '
                'phép trùng MST / SĐT / Email. Hãy báo quản lý nếu đây thật sự '
                'không phải hồ sơ trùng.'))

    def _dlm_dup_contact_message(self, label, value, dup):
        code = dup._dlm_display_code()
        ref = (' — %s' % code) if code else ''
        return _(
            "%s '%s' đã được dùng bởi khách hàng khác (%s%s).\n"
            "Nếu đây đúng là hai khách dùng chung tổng đài / hộp thư, hãy tích "
            "'Cho phép trùng SĐT / Email'."
        ) % (label, value, dup.name, ref)

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
