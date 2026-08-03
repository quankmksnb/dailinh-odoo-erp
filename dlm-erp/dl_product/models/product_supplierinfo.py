from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProductSupplierinfo(models.Model):
    """PROD-03 — dl.product.supplierinfo [kế thừa product.supplierinfo].

    Bảng giá vật tư / SP thương mại theo NHÀ CUNG CẤP + THỜI ĐIỂM. Dùng native
    ``product.supplierinfo`` (đã có sẵn partner_id, price, date_start, date_end,
    min_qty, currency_id, product_tmpl_id) thay vì bảng tự chế — thay thế hoàn
    toàn model cũ ``dl.material.price``.

    Field mở rộng theo Data Model: ``approval_state`` — Kế toán duyệt giá NCC
    (draft → approved) trước khi dùng để tính price_snapshot trong BOM
    (TECH-03).

    Field ``is_applied`` KHÔNG có trong Data Model gốc — bổ sung để giải quyết
    trường hợp 1 vật tư có nhiều bảng giá đã duyệt từ nhiều NCC khác nhau: cần
    đánh dấu RÕ 1 bảng giá đang dùng để tính price_snapshot, thay vì suy đoán
    "mới nhất theo ngày hiệu lực" (không tường minh khi nhiều NCC cùng còn
    hiệu lực).
    """

    _inherit = "product.supplierinfo"

    # Data Model PROD-03: price NUMERIC(14,2) NOT NULL CHECK > 0; date_start
    # DATE NOT NULL — native product.supplierinfo có price required nhưng
    # không chặn <= 0, và date_start không required.
    date_start = fields.Date(required=True)

    dl_product_kind = fields.Selection(
        [
            ("manufactured", "Sản phẩm gia công"),
            ("trading", "Sản phẩm thương mại"),
            ("material", "Vật tư"),
            ("material_processed", "Bán thành phẩm"),
        ],
        string="Loại sản phẩm",
        compute="_compute_dl_product_kind",
        store=True,
        index=True,
    )

    validity_state = fields.Selection(
        [
            ("upcoming", "Chưa hiệu lực"),
            ("active", "Còn hiệu lực"),
            ("expiring", "Sắp hết hạn"),
            ("expired", "Đã hết hạn"),
        ],
        string="Hiệu lực",
        compute="_compute_validity_state",
    )

    product_image_128 = fields.Image(
        related="product_tmpl_id.image_128",
        string="Ảnh sản phẩm",
        readonly=True,
    )

    @api.depends(
        "product_id.product_kind",
        "product_tmpl_id.product_variant_ids.product_kind",
    )
    def _compute_dl_product_kind(self):
        for rec in self:
            product = rec.product_id or rec.product_tmpl_id.product_variant_ids[:1]
            rec.dl_product_kind = product.product_kind if product else False

    @api.depends("date_start", "date_end")
    def _compute_validity_state(self):
        today = fields.Date.context_today(self)
        expiring_limit = today + relativedelta(days=30)
        for rec in self:
            if rec.date_start and rec.date_start > today:
                rec.validity_state = "upcoming"
            elif rec.date_end and rec.date_end < today:
                rec.validity_state = "expired"
            elif rec.date_end and rec.date_end <= expiring_limit:
                rec.validity_state = "expiring"
            else:
                rec.validity_state = "active"

    approval_state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("approved", "Đã duyệt"),
        ],
        string="Trạng thái duyệt",
        default="draft",
        required=True,
        copy=False,
        help="Kế toán duyệt giá NCC trước khi áp dụng cho báo giá / BOM.",
    )

    # Một vật tư/SP thương mại có thể có nhiều bảng giá (nhiều NCC) đã duyệt
    # cùng lúc — is_applied đánh dấu RÕ 1 bảng giá đang được dùng để tạo báo
    # giá/BOM (TECH-03 price_snapshot), thay vì suy đoán "mới nhất theo ngày".
    is_applied = fields.Boolean(
        string="Đang áp dụng",
        default=False,
        copy=False,
        help="Bảng giá đang được dùng để tính giá vật tư khi tạo báo giá/BOM. "
        "Mỗi vật tư chỉ có tối đa 1 bảng giá đang áp dụng tại một thời điểm.",
    )

    # UX: gộp approval_state + is_applied thành 1 pipeline duy nhất để hiển thị
    # (statusbar/badge) — người dùng nhìn 1 chỗ là biết dòng giá đang ở bước nào
    # và còn thiếu gì, thay vì phải tự ghép 2 cột trạng thái rời.
    display_state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("approved", "Đã duyệt"),
            ("applied", "Đang áp dụng"),
        ],
        string="Trạng thái",
        compute="_compute_display_state",
        store=True,
        help="Pipeline trạng thái bảng giá: Nháp → Đã duyệt → Đang áp dụng. "
        "Chỉ bảng giá Đang áp dụng mới được dùng để tính giá trong BOM/báo giá.",
    )

    @api.depends("approval_state", "is_applied")
    def _compute_display_state(self):
        for rec in self:
            if rec.is_applied:
                rec.display_state = "applied"
            elif rec.approval_state == "approved":
                rec.display_state = "approved"
            else:
                rec.display_state = "draft"

    def _is_valid_on(self, target_date):
        self.ensure_one()
        return bool(
            self.date_start
            and self.date_start <= target_date
            and (not self.date_end or self.date_end >= target_date)
        )

    def _ensure_currently_valid(self):
        today = fields.Date.context_today(self)
        invalid = self.filtered(lambda rec: not rec._is_valid_on(today))
        if invalid:
            raise UserError(_(
                "Không thể áp dụng bảng giá của '%s' vì chưa đến ngày hiệu lực "
                "hoặc đã hết hạn. Hãy kiểm tra lại Từ ngày/Đến ngày."
            ) % invalid[0].product_tmpl_id.display_name)

    @api.constrains("is_applied", "approval_state", "date_start", "date_end")
    def _check_is_applied(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.is_applied and rec.approval_state != "approved":
                raise ValidationError(
                    _("Chỉ bảng giá đã duyệt mới được đánh dấu đang áp dụng.")
                )
            if rec.is_applied and not rec._is_valid_on(today):
                raise ValidationError(_(
                    "Chỉ bảng giá đang trong thời gian hiệu lực mới được đánh dấu "
                    "Đang áp dụng. Hãy kiểm tra lại Từ ngày/Đến ngày."
                ))
            if rec.is_applied:
                other = self.search(
                    [
                        ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                        ("is_applied", "=", True),
                        ("id", "!=", rec.id),
                    ]
                )
                if other:
                    raise ValidationError(
                        _(
                            "Vật tư '%s' đã có bảng giá khác đang áp dụng (%s). "
                            "Bỏ áp dụng bảng giá đó trước."
                        )
                        % (rec.product_tmpl_id.display_name, other[0].partner_id.display_name)
                    )

    @api.constrains("price")
    def _check_price_positive(self):
        """Data Model PROD-03: price NUMERIC(14,2) NOT NULL CHECK > 0."""
        for rec in self:
            if rec.price <= 0:
                raise ValidationError(_("Đơn giá NCC phải lớn hơn 0."))

    @api.constrains("date_start", "date_end")
    def _check_date_range(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("Ngày hết hiệu lực phải sau hoặc bằng ngày hiệu lực.")
                )

    def action_approve(self):
        """Kế toán/Admin duyệt bảng giá NCC.

        UX: duyệt xong TỰ ĐỘNG áp dụng nếu vật tư chưa có bảng giá nào đang
        áp dụng — ca phổ biến nhất (vật tư chỉ có 1 bảng giá) rút còn 1 nút
        bấm là dùng được ngay trong BOM/báo giá. Nút "Áp dụng" riêng chỉ còn
        cần khi muốn CHUYỂN áp dụng giữa nhiều bảng giá đã duyệt.
        """
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được duyệt giá NCC."))
        self.write({"approval_state": "approved"})
        for rec in self:
            has_applied = self.search_count(
                [
                    ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                    ("is_applied", "=", True),
                ]
            )
            if not has_applied and rec._is_valid_on(fields.Date.context_today(rec)):
                rec.write({"is_applied": True})

    def action_reset_draft(self):
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được đổi trạng thái giá NCC."))
        self.write({"approval_state": "draft", "is_applied": False})

    def action_set_applied(self):
        """Đánh dấu bảng giá này đang áp dụng cho vật tư — tự bỏ áp dụng bảng giá khác."""
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được chọn bảng giá áp dụng."))
        for rec in self:
            if rec.approval_state != "approved":
                raise UserError(_("Chỉ có thể áp dụng bảng giá đã duyệt."))
            rec._ensure_currently_valid()
            others = self.search(
                [
                    ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                    ("is_applied", "=", True),
                    ("id", "!=", rec.id),
                ]
            )
            others.write({"is_applied": False})
            rec.write({"is_applied": True})

    def action_unset_applied(self):
        if not (
            self.env.user.has_group("dl_base.dl_group_accountant")
            or self.env.user.has_group("dl_base.dl_group_admin")
        ):
            raise UserError(_("Chỉ Kế toán hoặc Admin mới được bỏ áp dụng bảng giá."))
        self.write({"is_applied": False})
