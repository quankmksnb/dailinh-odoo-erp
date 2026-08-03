import difflib
import re

from markupsafe import Markup

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare
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

# Mã SP/vật tư TỰ SINH theo loại (không bắt người dùng nhập tay — đồng nhất với
# Mã KH, Mã BOM, Mã RFQ...). Prefix theo nhãn loại SP: GC- gia công,
# TM- thương mại, VT- vật tư, BTP- bán thành phẩm (xem data/dl_product_data.xml).
_KIND_CODE_SEQUENCE = {
    "manufactured": "dl.product.manufactured",
    "trading": "dl.product.trading",
    "material": "dl.product.material",
    "material_processed": "dl.product.material_processed",
}


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

    # Nhánh danh mục KỲ VỌNG theo Loại SP — output (gia công/thương mại) chỉ
    # nhận nhóm nhánh Thành phẩm, input (vật tư/BTP) chỉ nhận nhánh Vật tư.
    # Dùng làm domain động của categ_id trên form + validate cứng bên dưới.
    dl_categ_branch = fields.Selection(
        [("finished", "Thành phẩm"), ("material", "Vật tư")],
        compute="_compute_dl_categ_branch",
        string="Nhánh nhóm kỳ vọng",
    )

    @api.depends("product_kind")
    def _compute_dl_categ_branch(self):
        for rec in self:
            rec.dl_categ_branch = (
                "finished" if rec.product_kind in ("manufactured", "trading")
                else "material"
            )

    @api.constrains("categ_id", "product_kind")
    def _check_categ_branch(self):
        """Chặn cứng: Nhóm phải cùng nhánh với Loại SP. Nhóm ngoài 2 nhánh
        chuẩn (dl_branch='other', VD 'All' mặc định của core) không chặn —
        coi là 'chưa phân nhóm', tránh vỡ các luồng core tạo product ngầm."""
        for rec in self:
            branch = rec.categ_id.dl_branch
            if branch not in ("finished", "material"):
                continue
            if branch != rec.dl_categ_branch:
                kind_label = dict(
                    rec._fields["product_kind"].get_description(rec.env)["selection"]
                ).get(rec.product_kind, rec.product_kind)
                raise ValidationError(_(
                    "Nhóm '%s' thuộc nhánh %s — không dùng được cho sản phẩm "
                    "loại '%s'. Chọn nhóm thuộc nhánh %s."
                ) % (
                    rec.categ_id.display_name,
                    "Thành phẩm" if branch == "finished" else "Vật tư",
                    kind_label,
                    "Thành phẩm" if rec.dl_categ_branch == "finished" else "Vật tư",
                ))

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
            ("obsolete", "Ngừng sử dụng"),
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
             "• Ngừng sử dụng: không còn nhận làm/bán nữa, vẫn giữ trong danh mục "
             "để tra lịch sử (khác với Lưu trữ/ẩn hẳn).",
    )

    # GIÁ BÁN (list_price) do Sales đặt — "sales view" chuẩn ERP. Kế toán đã
    # rút khỏi việc đặt giá; dùng để readonly ô Giá bán trên form theo role.
    dlm_is_price_editor = fields.Boolean(
        compute="_compute_dlm_is_price_editor", compute_sudo=True)

    def _compute_dlm_is_price_editor(self):
        user = self.env.user
        editor = (user.has_group("dl_base.dl_group_ba")
                  or user.has_group("dl_base.dl_group_admin"))
        for rec in self:
            rec.dlm_is_price_editor = editor

    # MỞ NHẬP GIÁ BÁN đúng lúc (mua trước → bán sau): với SP thương mại, ô Giá bán
    # chỉ mở khi ĐÃ có Giá vốn tham chiếu (Mua hàng đã áp giá NCC). Lúc mới tạo
    # (chưa có giá NCC) Sales không phải/không được nhập giá bán vội. Loại SP khác
    # giữ nguyên (chỉ theo vai trò).
    dlm_can_edit_sale_price = fields.Boolean(
        compute="_compute_dlm_can_edit_sale_price", compute_sudo=True)

    @api.depends("product_kind", "standard_price")
    def _compute_dlm_can_edit_sale_price(self):
        user = self.env.user
        editor = (user.has_group("dl_base.dl_group_ba")
                  or user.has_group("dl_base.dl_group_admin"))
        for rec in self:
            rec.dlm_can_edit_sale_price = editor and (
                rec.product_kind != "trading" or rec.standard_price > 0)

    # GIÁ VỐN THAM CHIẾU (standard_price) — mục 4: KHÔNG nhập tay. Hệ thống tự đặt
    # theo giá NCC đang áp dụng (quy về ĐVT & tiền tệ SP). Chỉ đọc với mọi vai trò
    # nghiệp vụ (ghi chặn ở write()).
    def _dlm_recompute_reference_cost(self):
        """standard_price = giá NCC đang áp dụng của SP (đã quy đổi). Không có bảng
        giá áp dụng → 0. Ghi qua sudo; log chatter khi đổi."""
        prec = self.env["decimal.precision"].precision_get("Product Price")
        for prod in self:
            applied = prod.sudo().seller_ids.filtered(lambda s: s.is_applied)[:1]
            new_cost = applied._dlm_reference_unit_cost(prod) if applied else 0.0
            old_cost = prod.standard_price
            if float_compare(old_cost, new_cost, precision_digits=prec) != 0:
                prod.sudo().standard_price = new_cost
                prod.sudo().message_post(body=_(
                    "Giá vốn tham chiếu: %.0f → %.0f (theo giá NCC đang áp dụng).")
                    % (old_cost, new_cost))
        return True

    # LOẠI SP chỉ Admin/Kỹ thuật được đặt/đổi. Sales tạo SP thương mại nên Loại
    # SP khoá sẵn = 'trading' (default action) — dùng để readonly ô Loại SP trên
    # form, tránh Sales nhầm tạo SP gia công (gia công đi luồng RFQ/Kỹ thuật).
    dlm_can_change_kind = fields.Boolean(
        compute="_compute_dlm_can_change_kind", compute_sudo=True)

    def _compute_dlm_can_change_kind(self):
        user = self.env.user
        can = (user.has_group("dl_base.dl_group_admin")
               or user.has_group("dl_base.dl_group_tech"))
        for rec in self:
            rec.dlm_can_change_kind = can

    # Biên LN (%) = (giá bán − giá vốn) / giá bán × 100. CHỈ để HIỂN THỊ trên
    # màn Bảng giá SP thương mại (không lưu, không tham gia tính giá nghiệp vụ —
    # engine báo giá có luồng markup/floor riêng). compute_sudo để mọi role xem
    # bảng giá (kể cả CEO/Trưởng KD chỉ xem) đọc được standard_price không vướng ACL.
    dlm_sale_margin = fields.Float(
        string="Biên LN (%)", digits=(5, 1),
        compute="_compute_dlm_sale_margin", compute_sudo=True,
        help="Biên lợi nhuận của Giá bán so với Giá vốn (standard_price). "
             "Chỉ mang tính tham khảo trên màn Bảng giá; giá vốn 0 ⇒ hiển thị 100%.",
    )

    @api.depends("list_price", "standard_price")
    def _compute_dlm_sale_margin(self):
        for rec in self:
            rec.dlm_sale_margin = (
                (rec.list_price - rec.standard_price) / rec.list_price * 100.0
                if rec.list_price else 0.0
            )

    # UX màn Bảng giá: banner hướng dẫn trên tab "Nhà cung cấp & Bảng giá" —
    # chỉ hiện khi còn dòng giá ở Nháp (nhắc người mới bước tiếp theo là Duyệt).
    dlm_has_draft_seller = fields.Boolean(
        compute="_compute_dlm_has_draft_seller", compute_sudo=True)

    @api.depends("seller_ids.approval_state")
    def _compute_dlm_has_draft_seller(self):
        for rec in self:
            rec.dlm_has_draft_seller = any(
                s.approval_state == "draft" for s in rec.seller_ids)

    # Trạng thái GIÁ NCC của SP — để Mua hàng CHỦ ĐỘNG thấy SP nào còn thiếu giá
    # (cột + bộ lọc "Chưa có giá NCC" trên màn Bảng giá SP thương mại). Stored để
    # lọc/nhóm nhanh. Đối xứng ý nghĩa với display_state của từng dòng giá.
    dlm_supplier_price_state = fields.Selection(
        [
            ("none", "Chưa có giá NCC"),
            ("pending", "Có giá — chưa áp dụng"),
            ("applied", "Đã áp dụng"),
        ],
        string="Giá NCC",
        compute="_compute_dlm_supplier_price_state",
        store=True,
    )

    @api.depends("seller_ids", "seller_ids.is_applied")
    def _compute_dlm_supplier_price_state(self):
        for rec in self:
            if any(s.is_applied for s in rec.seller_ids):
                rec.dlm_supplier_price_state = "applied"
            elif rec.seller_ids:
                rec.dlm_supplier_price_state = "pending"
            else:
                rec.dlm_supplier_price_state = "none"

    # ── Readiness kích hoạt SP thương mại (mục 3) — dùng cho UI, KHÔNG chặn ────
    # Nút "Duyệt" của Sales chỉ hiện khi ĐỦ điều kiện (gồm giá NCC do Mua hàng
    # áp dụng). Trước đây nút luôn hiện ngay sau khi Sales nhập giá bán → bấm vào
    # chỉ báo lỗi (dead-end). Nay banner liệt kê việc còn thiếu, nút ẩn tới khi
    # thực sự kích hoạt được. Guard cứng vẫn ở _dlm_check_trading_activation.
    dlm_trading_ready = fields.Boolean(
        compute="_compute_dlm_trading_status", compute_sudo=True)
    dlm_trading_blockers_html = fields.Html(
        compute="_compute_dlm_trading_status", compute_sudo=True, sanitize=False)

    @api.depends(
        "product_kind", "dlm_lifecycle_state", "list_price", "standard_price",
        "seller_ids.is_applied", "seller_ids.approval_state", "seller_ids.price",
        "seller_ids.date_start", "seller_ids.date_end", "seller_ids.partner_id.active",
    )
    def _compute_dlm_trading_status(self):
        for rec in self:
            pending = (rec.product_kind == "trading"
                       and rec.dlm_lifecycle_state == "draft")
            blockers = rec._dlm_trading_blockers() if pending else []
            rec.dlm_trading_ready = pending and not blockers
            if blockers:
                rec.dlm_trading_blockers_html = Markup(
                    "<ul class='mb-0'>%s</ul>") % Markup("").join(
                    Markup("<li>%s</li>") % b for b in blockers)
            else:
                rec.dlm_trading_blockers_html = False

    def _dlm_trading_blockers(self):
        """Danh sách điều kiện CÒN THIẾU để kích hoạt SP thương mại (rỗng = đủ).
        Dùng chung cho compute (UI) và _dlm_check_trading_activation (guard).

        Thứ tự MUA TRƯỚC → BÁN SAU: khi chưa có giá vốn (Mua hàng chưa áp giá
        NCC) thì CHỈ nhắc "chờ Mua hàng", KHÔNG nhắc Giá bán — vì ô Giá bán lúc
        đó còn khóa (giá bán mở sau khi có giá vốn, xem dlm_can_edit_sale_price).
        seller/partner đọc qua sudo vì Sales không có quyền supplierinfo/res.partner."""
        self.ensure_one()
        prod = self.sudo()
        reasons = []
        applied = prod.seller_ids.filtered(lambda s: s.is_applied)[:1]
        cost_ready = False
        if not applied:
            reasons.append(_(
                "Chờ Mua hàng thiết lập & áp dụng giá NCC (ở màn Bảng giá SP "
                "thương mại) — cần có giá mua trước khi định giá bán."))
        else:
            today = fields.Date.context_today(self)
            if applied.approval_state != "approved":
                reasons.append(_("Bảng giá NCC đang áp dụng chưa được Mua hàng duyệt."))
            elif not applied._is_valid_on(today):
                reasons.append(_(
                    "Bảng giá NCC đang áp dụng đã hết hạn hoặc chưa tới ngày hiệu lực."))
            elif applied.price <= 0:
                reasons.append(_("Giá NCC của bảng giá đang áp dụng phải > 0."))
            elif not applied.partner_id.active:
                reasons.append(_(
                    "Nhà cung cấp '%s' của bảng giá đang áp dụng đã bị vô hiệu hóa."
                ) % applied.partner_id.display_name)
            elif prod.standard_price <= 0:
                reasons.append(_(
                    "Chưa xác định được Giá vốn tham chiếu (kiểm tra tiền tệ / đơn "
                    "vị của bảng giá NCC đang áp dụng)."))
            else:
                cost_ready = True
        # Chỉ nhắc Giá bán KHI đã có giá vốn (đúng luồng mua trước → bán sau).
        if cost_ready:
            if prod.list_price <= 0:
                reasons.append(_(
                    "Nhập Giá bán (> 0) — Sales nhập sau khi đã có giá vốn."))
            else:
                prec = self.env["decimal.precision"].precision_get("Product Price")
                if float_compare(prod.list_price, prod.standard_price,
                                 precision_digits=prec) < 0:
                    reasons.append(_(
                        "Giá bán (%.0f) đang THẤP HƠN Giá vốn tham chiếu (%.0f) — "
                        "nếu thực sự cần bán lỗ, xử lý ở duyệt báo giá (CEO/Trưởng "
                        "KD), không hạ giá niêm yết sản phẩm."
                    ) % (prod.list_price, prod.standard_price))
        return reasons

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
        """Duyệt SP lên 'active'. SP thương mại phải qua ĐỦ điều kiện kích hoạt
        (mục 3) — kiểm tra chặt ở server, KHÔNG cho override."""
        for rec in self:
            rec._check_lifecycle_manager()
            if rec.product_kind == "trading":
                rec._dlm_check_trading_activation()
            rec.sudo().write({"dlm_lifecycle_state": "active"})
        return True

    def _dlm_check_trading_activation(self):
        """Guard cứng kích hoạt SP thương mại (mục 3) — dựng lại từ danh sách
        điều kiện thiếu (_dlm_trading_blockers), báo hết một lần cho rõ. UI đã ẩn
        nút Duyệt khi chưa đủ; đây là lớp chặn cuối cùng ở server."""
        self.ensure_one()
        blockers = self._dlm_trading_blockers()
        if blockers:
            raise UserError(_(
                "Chưa đủ điều kiện kích hoạt Sản phẩm thương mại:\n• %s"
            ) % "\n• ".join(blockers))

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

    # ── Mã SP/vật tư tự sinh theo loại ───────────────────────────────────
    @api.model
    def _dlm_next_code_for_kind(self, product_kind):
        """Mã kế tiếp theo loại SP (False nếu loại không có sequence)."""
        seq_code = _KIND_CODE_SEQUENCE.get(product_kind)
        return self.env["ir.sequence"].next_by_code(seq_code) if seq_code else False

    # ── Chuẩn hóa khi promote (đơn chốt tự duyệt SP gia công từ Nháp) ────────
    def _dlm_standardize_on_promote(self):
        """Chuẩn hóa SP khi được nâng Nháp→Đã duyệt (gọi từ luồng chốt đơn ở
        dl_sale): sinh Mã SP chính thức nếu còn trống + gọn tên. sudo an toàn —
        người chốt đơn (Sales) không có quyền write SP gia công."""
        for rec in self:
            vals = {}
            # Gọn tên: bỏ khoảng trắng thừa (đầu/cuối + gộp liên tiếp).
            name = rec.name and " ".join(rec.name.split())
            if name and name != rec.name:
                vals["name"] = name
            # Mã chính thức: SP tạm từ RFQ để trống mã cho tới lúc này (tránh đốt
            # số cho bản nháp có thể bị dọn) — giờ mới sinh theo loại.
            if not rec.default_code:
                code = rec._dlm_next_code_for_kind(rec.product_kind)
                if code:
                    vals["default_code"] = code
            if vals:
                rec.sudo().write(vals)
        return True

    # ── Nháp mồ côi: SP gia công còn Nháp nhưng RFQ không chốt thành đơn ──────
    @api.model
    def _dlm_orphan_draft_domain(self, older_than_days=None):
        """Domain SP gia công/BTP còn Nháp, KHÔNG dòng đơn bán nào tham chiếu.
        older_than_days: chỉ lấy SP tạo trước mốc đó (rác đã 'nguội')."""
        # dl_product không depends dl_sale — model đơn bán chỉ có khi dl_sale
        # đã cài; nếu chưa thì coi như không SP nào đang được dùng.
        used_product_ids = []
        if "dl.sale.order.line" in self.env:
            used_product_ids = self.env["dl.sale.order.line"].sudo().search([
                ("order_id.state", "!=", "cancelled"),
            ]).mapped("product_id").ids
        domain = [
            ("dlm_lifecycle_state", "=", "draft"),
            ("product_kind", "in", ("manufactured", "material_processed")),
            ("id", "not in", used_product_ids),
        ]
        if older_than_days:
            cutoff = fields.Datetime.subtract(
                fields.Datetime.now(), days=older_than_days)
            domain.append(("create_date", "<", cutoff))
        return domain

    @api.model
    def _cron_obsolete_orphan_drafts(self):
        """Cron: rà nháp mồ côi quá hạn → chuyển 'obsolete' (giữ lịch sử, reset
        lại được). Ngưỡng ngày lấy từ ir.config_parameter (mặc định 30)."""
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "dl_product.orphan_draft_days", 30))
        orphans = self.sudo().search(self._dlm_orphan_draft_domain(days))
        if orphans:
            orphans.write({"dlm_lifecycle_state": "obsolete"})
            for rec in orphans:
                rec.message_post(body=_(
                    "Tự động chuyển 'Ngừng' — SP còn Nháp quá %s ngày và không "
                    "có đơn bán nào sử dụng (nháp mồ côi).") % days)
        return True

    @api.model
    def action_dlm_review_orphan_drafts(self):
        """Nút/menu 'Rà soát nháp mồ côi' — mở danh sách SP nháp mồ côi (mọi
        tuổi) để Kỹ thuật xem và tự chuyển 'Ngừng' (nút Ngừng có sẵn)."""
        orphan_ids = self.sudo().search(self._dlm_orphan_draft_domain()).ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Nháp mồ côi (rà soát)"),
            "res_model": "product.product",
            "view_mode": "tree,form",
            "domain": [("id", "in", orphan_ids)],
            "target": "current",
        }

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

    # ── Chống trùng tên sản phẩm (dùng chung wizard RFQ + form SP) ────────
    @api.model
    def _dlm_normalize_name(self, name):
        """Chuẩn hoá tên để so trùng: gộp/khử khoảng trắng thừa + hạ chữ thường.
        GIỮ NGUYÊN dấu tiếng Việt (chốt thiết kế) — vì vậy 'Khung máy ABC' và
        'khung  máy   abc ' tính TRÙNG HỆT, còn 'Khung may ABC' (thiếu dấu) chỉ
        tính GẦN GIỐNG."""
        if not name:
            return ""
        return " ".join(name.split()).lower()

    @api.model
    def _dlm_find_name_matches(self, name, kinds=None, exclude_ids=None,
                               extra_domain=None, similar_threshold=0.82):
        """Tìm SP trùng/gần giống theo TÊN đã chuẩn hoá.

        Trả về dict ``{'exact': recordset, 'similar': recordset}``:
        • exact  — tên chuẩn hoá bằng nhau (khác hoa/thường hay thừa khoảng
          trắng vẫn tính trùng).
        • similar — một tên chứa TRỌN các token của tên kia, HOẶC độ tương đồng
          difflib ≥ ngưỡng (bắt cả trường hợp thiếu dấu / thêm hậu tố năm...).

        Chỉ soi SP đang hoạt động (active) thuộc ``kinds``. ``exclude_ids`` bỏ
        chính bản ghi đang kiểm; ``extra_domain`` để thu hẹp (VD loại SP tạm RFQ).
        """
        Product = self.env["product.product"]
        empty = Product.browse()
        norm = self._dlm_normalize_name(name)
        if not norm:
            return {"exact": empty, "similar": empty}
        domain = [("product_kind", "in", list(
            kinds or [k for k, _label in _PRODUCT_KIND_SELECTION]))]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        if extra_domain:
            domain += list(extra_domain)
        candidates = Product.search(domain)
        norm_tokens = set(norm.split())
        exact = empty
        similar_ids = []
        for prod in candidates:
            cnorm = self._dlm_normalize_name(prod.name)
            if not cnorm:
                continue
            if cnorm == norm:
                exact |= prod
                continue
            ctokens = set(cnorm.split())
            token_subset = bool(norm_tokens) and bool(ctokens) and (
                norm_tokens <= ctokens or ctokens <= norm_tokens)
            ratio = difflib.SequenceMatcher(None, norm, cnorm).ratio()
            if token_subset or ratio >= similar_threshold:
                similar_ids.append(prod.id)
        return {"exact": exact, "similar": Product.browse(similar_ids)}

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

    # ── Chặn ghi trực tiếp field nhạy cảm (mục 9 — readonly UI là chưa đủ) ────
    # Không đủ vai trò / không qua action nghiệp vụ (sudo) ⇒ chặn ở tầng ORM.
    #   • standard_price / dlm_lifecycle_state: CHỈ hệ thống (sudo) — giá vốn tự
    #     theo giá NCC áp dụng; vòng đời chỉ đổi qua action_lifecycle_*.
    #   • list_price: chỉ Sales(BA)/Admin.  • product_kind: chỉ Kỹ thuật/Admin.
    _DLM_PROTECTED_FIELDS = {
        "standard_price": (),
        "dlm_lifecycle_state": (),
        "list_price": ("dl_base.dl_group_ba", "dl_base.dl_group_admin"),
        "product_kind": ("dl_base.dl_group_tech", "dl_base.dl_group_admin"),
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Mã SP/vật tư TỰ SINH — không bắt người dùng nhập tay. Bỏ qua khi đã
            # có mã (seed/demo/import tự đặt) hoặc là SP tạm từ RFQ
            # (is_rfq_provisional): loại này để trống mã tới khi chốt đơn mới sinh
            # (_dlm_standardize_on_promote), tránh đốt số cho nháp có thể bị dọn.
            if vals.get("default_code") or vals.get("is_rfq_provisional"):
                continue
            kind = (vals.get("product_kind")
                    or self.env.context.get("default_product_kind")
                    or "manufactured")
            code = self._dlm_next_code_for_kind(kind)
            if code:
                vals["default_code"] = code
        records = super().create(vals_list)
        # Chủ động báo Mua hàng khi Sales tạo SP thương mại mới (nháp) — để họ
        # biết mà thiết lập giá NCC, thay vì phải tự dò. Bỏ qua luồng hệ thống
        # (sudo / SUPERUSER: seed/demo/migration) để không sinh nhắc rác.
        if not self.env.su and self.env.uid != SUPERUSER_ID:
            for rec in records:
                if (rec.product_kind == "trading"
                        and rec.dlm_lifecycle_state == "draft"):
                    rec._dlm_notify_purchasing_new_trading()
        return records

    def _dlm_notify_purchasing_new_trading(self):
        """Giao việc 'Thiết lập giá NCC' cho từng người nhóm Mua hàng (activity
        To-Do). sudo vì Sales không có quyền tạo activity cho user khác."""
        self.ensure_one()
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        if not group:
            return
        users = group.users.filtered(lambda u: u.active and not u.share)
        for user in users:
            self.sudo().activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                summary=_("Thiết lập giá NCC cho SP thương mại mới"),
                note=_(
                    "Sản phẩm thương mại '%s' vừa được tạo — cần nhập nhà cung cấp "
                    "và giá mua ở màn Bảng giá SP thương mại, rồi Duyệt/Áp dụng để "
                    "Sales định giá bán và kích hoạt."
                ) % self.display_name,
                user_id=user.id,
            )

    def write(self, vals):
        if not self.env.su:
            user = self.env.user
            for fname, groups in self._DLM_PROTECTED_FIELDS.items():
                if fname not in vals:
                    continue
                if not groups:
                    raise AccessError(_(
                        "Trường '%s' chỉ được hệ thống cập nhật tự động (qua giá "
                        "NCC áp dụng / action nghiệp vụ), không sửa trực tiếp."
                    ) % self._fields[fname].get_description(self.env)["string"])
                if not any(user.has_group(g) for g in groups):
                    raise AccessError(_(
                        "Bạn không có quyền sửa '%s'."
                    ) % self._fields[fname].get_description(self.env)["string"])
        return super().write(vals)

    def get_formview_id(self, access_uid=None):
        return self.env.ref('dl_product.view_dl_product_form').id
