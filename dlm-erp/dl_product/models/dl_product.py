import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

# Data Model PROD-02: default_code validate ^[A-Z0-9\-]+$ (chữ hoa, số, gạch ngang)
_CODE_RE = re.compile(r"^[A-Z0-9\-]+$")

# Data Model PROD-02: 4 loại nghiệp vụ. Danh sách đầy đủ; từng màn giới hạn
# dropdown qua context 'dl_kind_scope' (xem _dl_product_kind_selection).
_PRODUCT_KIND_SELECTION = [
    ("manufactured", "Sản phẩm gia công"),
    ("trading", "Sản phẩm thương mại"),
    ("material", "Vật tư"),
    ("material_processed", "Bán thành phẩm"),
]


class ProductProduct(models.Model):
    """PROD-02 — dl.product.

    Theo Data Model (TDS Report 4, §4.2): SẢN PHẨM là bảng HỢP NHẤT cho cả 4
    loại nghiệp vụ, phân biệt qua ``product_kind``. Kế thừa MỞ RỘNG THUẦN
    ``product.product`` (``_inherit`` — KHÔNG tạo bảng mới): mọi bản ghi nằm
    trực tiếp trong ``product_product``, giữ nguyên vẹn search/report/tồn kho.

    Thiết kế cũ (dl.product/dl.semi.product/dl.material là 3 bảng delegation
    riêng qua ``_inherits``) đã bị BỎ — semi → material_processed, material giữ
    nguyên; đổi loại sản phẩm nay chỉ là đổi 1 field ``product_kind``.

    Pattern: để MỞ RỘNG product.product ĐỒNG THỜI thêm mixin mail.thread, phải
    khai cả ``_name`` (= 'product.product') LẪN ``_inherit`` dạng list chứa chính
    nó + mixin. Thiếu ``_name`` khi ``_inherit`` là list ⇒ Odoo báo
    "The _name attribute ... is not valid".
    """

    _name = "product.product"
    _inherit = ["product.product", "mail.thread", "mail.activity.mixin"]

    product_kind = fields.Selection(
        selection=lambda self: self._dl_product_kind_selection(),
        string="Loại sản phẩm",
        required=True,
        default="manufactured",
        tracking=True,
        help="Phân loại nghiệp vụ (Data Model PROD-02):\n"
        "• Gia công (manufactured): tự sản xuất theo BOM\n"
        "• Thương mại (trading): nhập về bán thẳng, tra giá NCC\n"
        "• Vật tư (material): NVL thô, tra giá NCC\n"
        "• Bán thành phẩm (material_processed): cắt/gia công từ vật tư gốc, có BOM riêng",
    )

    @api.model
    def _dl_product_kind_selection(self):
        """Dropdown Loại sản phẩm theo từng màn: action đặt context
        ``dl_kind_scope`` = list các kind được phép (VD màn Sản phẩm
        ['manufactured', 'trading'], màn Vật tư ['material',
        'material_processed']). Không đặt (BOM, RFQ, import, shell…) → đủ 4.

        Lưu ý: selection callable được đánh giá lại theo context cả khi GHI —
        ghi một kind ngoài scope của màn hiện tại sẽ bị ORM chặn (ValueError),
        đúng chủ đích chặn tạo chéo loại giữa các màn.
        """
        scope = self.env.context.get("dl_kind_scope")
        if scope:
            return [(k, v) for k, v in _PRODUCT_KIND_SELECTION if k in scope]
        return list(_PRODUCT_KIND_SELECTION)

    @api.model
    def get_views(self, views, options=None):
        """Web client (view_service.loadViews) LỌC context trước khi gọi
        get_views — chỉ giữ 'lang' và '*_view_ref' — nên ``dl_kind_scope``
        đặt trong context action KHÔNG tới được fields_get, dropdown Loại SP
        vẫn đủ 4 loại. Bù lại get_views nhận ``options['action_id']``: đọc
        lại context của chính action đó rồi bơm scope trước khi dựng fields.
        (Các RPC ghi/onchange không bị lọc context nên validation theo scope
        ở _dl_product_kind_selection vốn đã hoạt động.)"""
        action_id = (options or {}).get("action_id")
        if action_id and "dl_kind_scope" not in self.env.context:
            action = self.env["ir.actions.act_window"].sudo().browse(action_id).exists()
            try:
                action_ctx = safe_eval(action.context) if action and action.context else {}
            except Exception:
                action_ctx = {}
            scope = action_ctx.get("dl_kind_scope") if isinstance(action_ctx, dict) else None
            if scope:
                self = self.with_context(dl_kind_scope=scope)
        return super().get_views(views, options)

    # ── Trạng thái vòng đời (dùng chung mọi loại SP) ─────────────────────
    # Tránh "rác" danh mục: SP mới do Kỹ thuật (RFQ) / Sales (thương mại) tạo
    # nằm ở 'draft' — CHƯA tái sử dụng được. Chỉ lên 'active' khi được duyệt
    # (đơn hàng chốt tự promote — dl_sale; hoặc bấm tay). 'obsolete' = ngừng
    # nhận nhưng vẫn giữ lịch sử. default='active' để dữ liệu cũ khi nâng cấp
    # tự thành SP chính thức; luồng tạo mới sẽ set 'draft' tường minh.
    dlm_lifecycle_state = fields.Selection(
        [
            ("draft", "Nháp / Kỹ thuật"),
            ("active", "Đã duyệt"),
            ("obsolete", "Ngừng"),
        ],
        string="Trạng thái vòng đời",
        default="active",
        required=True,
        tracking=True,
        copy=False,
        help="• Nháp: vừa tạo khi xử lý RFQ / khai báo SP thương mại — chưa tái "
             "sử dụng được.\n"
             "• Đã duyệt: đã chốt (đơn hàng xác nhận hoặc duyệt tay) — nằm trong "
             "danh mục để tái sử dụng.\n"
             "• Ngừng: không còn nhận làm/bán nữa, vẫn giữ lịch sử.",
    )

    # Chỉ Kế toán/Admin được nhập Giá bán SP thương mại (Sales tạo SP nhưng
    # KHÔNG tự đặt giá) — dùng để readonly ô giá trên form theo role.
    dlm_is_price_editor = fields.Boolean(
        compute="_compute_dlm_is_price_editor", compute_sudo=True)

    def _compute_dlm_is_price_editor(self):
        user = self.env.user
        editor = (user.has_group("dl_base.dl_group_accountant")
                  or user.has_group("dl_base.dl_group_admin"))
        for rec in self:
            rec.dlm_is_price_editor = editor

    def _check_lifecycle_manager(self):
        """Ai được đổi trạng thái vòng đời: SP gia công/BTP → Kỹ thuật/Admin;
        SP thương mại → Sales(BA)/Admin. sudo (auto-promote từ đơn hàng) bỏ qua."""
        self.ensure_one()
        if self.env.su:
            return
        user = self.env.user
        if user.has_group("dl_base.dl_group_admin"):
            return
        if self.product_kind == "trading":
            if not user.has_group("dl_base.dl_group_ba"):
                raise AccessError(
                    _("Chỉ Sales/Admin được đổi trạng thái Sản phẩm thương mại."))
        else:
            if not user.has_group("dl_base.dl_group_tech"):
                raise AccessError(
                    _("Chỉ Kỹ thuật/Admin được đổi trạng thái Sản phẩm gia công."))

    def action_lifecycle_activate(self):
        """Duyệt SP lên 'active' (tái sử dụng được). SP thương mại phải có giá
        bán (do Kế toán nhập) trước khi Sales kích hoạt."""
        for rec in self:
            rec._check_lifecycle_manager()
            if rec.product_kind == "trading" and rec.list_price <= 0:
                raise UserError(_(
                    "Sản phẩm thương mại phải có Giá bán > 0 (Kế toán nhập) "
                    "trước khi kích hoạt."))
            rec.sudo().write({"dlm_lifecycle_state": "active"})
        return True

    def action_lifecycle_obsolete(self):
        for rec in self:
            rec._check_lifecycle_manager()
            rec.sudo().write({"dlm_lifecycle_state": "obsolete"})
        return True

    def action_lifecycle_reset_draft(self):
        for rec in self:
            rec._check_lifecycle_manager()
            rec.sudo().write({"dlm_lifecycle_state": "draft"})
        return True

    # ── Hao hụt & thu hồi (chỉ vật tư) ───────────────────────────────────
    # NGUỒN DUY NHẤT của hao hụt: đặt ngay trên vật tư, kỹ thuật điền khi tạo.
    # Tự điền mặc định theo NHÓM sản phẩm từ cấu hình (dl.pricing.waste.rule
    # target_type=category) — xem _onchange_dlm_waste_default; vẫn sửa tay được.
    # BOM/báo giá đọc thẳng các field này (bỏ model hao hụt cũ dl.pricing.waste).
    dlm_waste_rate = fields.Float(
        string="Hao hụt cơ sở (%)", digits=(6, 2),
        help="Tỷ lệ hao hụt của vật tư này. Hệ số phức tạp chọn theo từng dòng "
             "BOM sẽ nhân thêm vào tỷ lệ này khi tính giá.",
    )
    dlm_has_recovery = fields.Boolean(string="Có thu hồi phế liệu")
    dlm_recovery_rate = fields.Float(
        string="Tỷ lệ thu hồi (%)", digits=(6, 2),
        help="Tính trên LƯỢNG hao hụt (không tính trên lượng vật tư thuần).",
    )
    dlm_scrap_product_id = fields.Many2one(
        "product.product", string="Sản phẩm phế liệu",
        help="Đơn giá thu hồi lấy từ giá bán (list_price) của sản phẩm phế này.",
    )
    # Onchange tự điền mặc định theo nhóm (đọc dl.pricing.waste.rule) nằm ở
    # dl_technical — module đó mới phụ thuộc dl_config; dl_product KHÔNG được
    # tham chiếu ngược cấu hình.

    def _dlm_scrap_unit_price(self):
        """Đơn giá thu hồi/đv (giá bán sản phẩm phế). 0 nếu không cấu hình."""
        self.ensure_one()
        return self.dlm_scrap_product_id.list_price if self.dlm_scrap_product_id else 0.0

    def set_dlm_waste(self, vals):
        """Cập nhật hao hụt vật tư từ màn Cấu hình (sửa inline). Guard quyền
        (Kỹ thuật/Kế toán/Admin) rồi sudo-ghi để không phụ thuộc quyền write
        product.product của từng role."""
        user = self.env.user
        if not self.env.su and not (
                user.has_group("dl_base.dl_group_tech")
                or user.has_group("dl_base.dl_group_accountant")
                or user.has_group("dl_base.dl_group_admin")):
            raise AccessError(_("Chỉ Kỹ thuật/Kế toán/Admin được sửa hao hụt vật tư."))
        allowed = {"dlm_waste_rate", "dlm_has_recovery", "dlm_recovery_rate",
                   "dlm_scrap_product_id"}
        self.sudo().write({k: v for k, v in vals.items() if k in allowed})
        return True

    # ── Constraints ──────────────────────────────────────────────────────
    @api.constrains("default_code")
    def _check_default_code(self):
        """Data Model §6 Indexing: default_code UNIQUE + validate ^[A-Z0-9\\-]+$."""
        for rec in self:
            code = rec.default_code
            if not code:
                continue
            if not _CODE_RE.match(code):
                raise ValidationError(
                    _(
                        "Mã sản phẩm '%s' không hợp lệ — chỉ cho phép chữ IN HOA, "
                        "số và dấu gạch ngang (VD: CT-200, VT-001)."
                    )
                    % code
                )
            dup = self.with_context(active_test=False).search(
                [("default_code", "=", code), ("id", "!=", rec.id)], limit=1
            )
            if dup:
                raise ValidationError(
                    _("Mã sản phẩm '%s' đã tồn tại (%s).") % (code, dup.display_name)
                )

    def get_formview_id(self, access_uid=None):
        return self.env.ref('dl_product.view_dl_product_form').id
