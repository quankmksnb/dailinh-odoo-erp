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
        help="Mua hàng duyệt giá nhà cung cấp trước khi áp dụng cho báo giá / BOM.",
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

    # ── Audit giá NCC (mục 10) — người tạo/ngày tạo dùng create_uid/create_date ─
    dlm_approved_uid = fields.Many2one(
        "res.users", string="Người duyệt", readonly=True, copy=False)
    dlm_approved_date = fields.Datetime(
        string="Ngày duyệt", readonly=True, copy=False)
    dlm_applied_uid = fields.Many2one(
        "res.users", string="Người áp dụng", readonly=True, copy=False)
    dlm_applied_date = fields.Datetime(
        string="Ngày áp dụng", readonly=True, copy=False)
    dlm_unapplied_uid = fields.Many2one(
        "res.users", string="Người bỏ áp dụng gần nhất", readonly=True, copy=False)
    dlm_unapplied_date = fields.Datetime(
        string="Ngày bỏ áp dụng gần nhất", readonly=True, copy=False)

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

    # Trên list Bảng giá, dòng của NCC "phương án khác" được thụt vào làm dòng
    # phụ dưới giá đang dùng. Điều kiện nói theo BẢN GHI (không phụ thuộc thứ tự
    # sắp xếp của list) nên giá trị ổn định dù người dùng đổi cách sắp/lọc.
    dlm_is_alternative = fields.Boolean(
        string="Giá NCC phương án khác",
        compute="_compute_dlm_is_alternative",
        help="Vật tư này đã có một bảng giá đang áp dụng, và dòng này không phải "
        "bảng giá đó.",
    )

    def _dlm_applied_partner_by_tmpl(self):
        """{vật tư: nhà cung cấp} của dòng giá ĐANG áp dụng, cho các vật tư trong
        recordset — dùng để biết một dòng phụ là của CHÍNH nhà cung cấp đó hay
        của nhà cung cấp khác."""
        tmpl_ids = self.product_tmpl_id.ids
        if not tmpl_ids:
            return {}
        rows = self.env["product.supplierinfo"].sudo().search(
            [("product_tmpl_id", "in", tmpl_ids), ("is_applied", "=", True)])
        return {r.product_tmpl_id.id: r.partner_id.id for r in rows}

    @api.depends("is_applied", "product_tmpl_id")
    def _compute_dlm_is_alternative(self):
        applied = self._dlm_applied_partner_by_tmpl()
        for rec in self:
            rec.dlm_is_alternative = (
                not rec.is_applied and rec.product_tmpl_id.id in applied
            )

    # Chữ in ở cột Vật tư của dòng phụ. Trước đây JS in cứng "Nhà cung cấp khác"
    # cho MỌI dòng phụ — mà `dlm_is_alternative` chưa bao giờ so `partner_id`,
    # nên giá mới của CHÍNH nhà cung cấp đang dùng cũng bị gọi là "NCC khác".
    # Nhãn phải nói đúng dòng đó là gì, vì đó là thứ người dùng đọc để quyết định.
    dlm_alt_label = fields.Char(
        string="Vai trò dòng",
        compute="_compute_dlm_alt_label",
        help="Dòng phụ này là gì so với giá đang áp dụng ở dòng trên: giá của "
        "nhà cung cấp khác, giá mới của chính họ, hay giá cũ đã bị thay.",
    )

    @api.depends("dlm_is_alternative", "dlm_superseded", "partner_id",
                 "product_tmpl_id")
    def _compute_dlm_alt_label(self):
        applied = self._dlm_applied_partner_by_tmpl()
        for rec in self:
            if not rec.dlm_is_alternative:
                rec.dlm_alt_label = False
            elif rec.dlm_superseded:
                rec.dlm_alt_label = _("Giá cũ — đã thay")
            elif applied.get(rec.product_tmpl_id.id) == rec.partner_id.id:
                rec.dlm_alt_label = _("Giá mới chờ áp dụng")
            else:
                rec.dlm_alt_label = _("Nhà cung cấp khác")

    # `date_end` KHÔNG nói nổi "bị thay ngay trong ngày": nó không được nhỏ hơn
    # `date_start`, nên giá hỏi lại lần hai trong cùng một ngày chỉ đóng được về
    # đúng hôm nay ⇒ bộ lọc "Còn hiệu lực" vẫn cho lọt, và người dùng thấy hai
    # dòng của cùng một nhà cung cấp. Cờ này mới là thứ giữ cho màn hình nói
    # HIỆN TRẠNG. Nó không đụng gì tới giá vốn: giá đã đóng lên LÔ lúc nhận hàng
    # (`stock.lot.dlm_unit_cost`, bất biến), nên lô cũ vẫn tính bằng giá cũ.
    dlm_superseded = fields.Boolean(
        string="Đã bị thay thế",
        default=False,
        copy=False,
        help="Giá này đã bị một giá mới hơn của CHÍNH nhà cung cấp đó thay chỗ. "
        "Chỉ còn giá trị tra cứu lịch sử, không dùng để tính giá nữa.",
    )

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
                raise ValidationError(_("Đơn giá nhà cung cấp phải lớn hơn 0."))

    @api.constrains("date_start", "date_end")
    def _check_date_range(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError(
                    _("Ngày hết hiệu lực phải sau hoặc bằng ngày hiệu lực.")
                )

    def _check_price_manager(self):
        """Ai được duyệt/áp dụng/hủy giá NCC: Mua hàng hoặc Admin. Kế toán đã
        chuyển sang chỉ-xem (giá MUA thuộc Mua hàng). su (luồng tự động) bỏ qua."""
        if self.env.su:
            return
        if not (self.env.user.has_group("dl_base.dl_group_purchasing")
                or self.env.user.has_group("dl_base.dl_group_admin")):
            raise UserError(_("Chỉ Mua hàng hoặc Admin mới được thao tác giá nhà cung cấp."))

    # ── Giá vốn tham chiếu (mục 4) ───────────────────────────────────────────
    def _dlm_product(self):
        """product.product gắn với dòng giá NCC (biến thể cụ thể hoặc biến thể
        đầu tiên của template)."""
        self.ensure_one()
        return self.product_id or self.product_tmpl_id.product_variant_ids[:1]

    def _dlm_reference_unit_cost(self, product):
        """Đơn giá NCC quy về ĐVT sản phẩm & tiền tệ công ty — dùng làm giá vốn
        tham chiếu. RAISE (chặn áp dụng) nếu khác tiền tệ chuẩn hoặc không quy đổi
        được đơn vị, để không sinh giá vốn sai (mục 4)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        company_currency = company.currency_id
        if self.currency_id and company_currency and self.currency_id != company_currency:
            raise UserError(_(
                "Chỉ áp dụng được bảng giá cùng tiền tệ công ty (%s); bảng giá này "
                "đang dùng %s. Hãy nhập lại giá theo %s trước khi áp dụng."
            ) % (company_currency.name, self.currency_id.name, company_currency.name))
        price = self.price
        src_uom, dst_uom = self.product_uom, product.uom_id
        if src_uom and dst_uom and src_uom != dst_uom:
            if src_uom.category_id != dst_uom.category_id:
                raise UserError(_(
                    "Không quy đổi được đơn vị mua '%s' về đơn vị sản phẩm '%s'. "
                    "Kiểm tra lại đơn vị trước khi áp dụng bảng giá này."
                ) % (src_uom.name, dst_uom.name))
            price = src_uom._compute_price(price, dst_uom)
        return price

    def _dlm_apply(self, when=None):
        """Đánh dấu 1 dòng giá đang áp dụng + ghi audit, rồi đồng bộ giá vốn tham
        chiếu của sản phẩm. Validate tiền tệ/đơn vị nằm trong _recompute → lỗi thì
        cả giao dịch rollback (không để is_applied treo)."""
        self.ensure_one()
        when = when or fields.Datetime.now()
        self.write({
            "is_applied": True,
            "dlm_superseded": False,
            "dlm_applied_uid": self.env.uid,
            "dlm_applied_date": when,
        })
        product = self._dlm_product()
        if product:
            product._dlm_recompute_reference_cost()
            # Đóng vòng lặp EX-13: vật tư đã có giá áp dụng ⇒ đóng việc Kỹ thuật
            # đã giao cho Mua hàng (dọn hòm việc; cờ pricing_blocked phía RFQ tự
            # hết vì dlm_supplier_price_state chuyển 'applied').
            product._dlm_close_price_requests()
            # Khép vòng SP thương mại: đã có Giá vốn tham chiếu ⇒ đóng việc của
            # Mua hàng và báo Trưởng phòng KD vào chốt Giá bán (tự lọc loại SP/
            # trạng thái trong hàm).
            product._dlm_on_supplier_cost_applied()

    def _dlm_unapply(self, when=None):
        when = when or fields.Datetime.now()
        for rec in self:
            rec.write({
                "is_applied": False,
                "dlm_unapplied_uid": self.env.uid,
                "dlm_unapplied_date": when,
            })
            product = rec._dlm_product()
            if product:
                product._dlm_recompute_reference_cost()

    def action_approve(self):
        """Mua hàng/Admin duyệt bảng giá NCC.

        UX: duyệt xong TỰ ĐỘNG áp dụng nếu sản phẩm chưa có bảng giá nào đang áp
        dụng — ca phổ biến nhất (1 NCC) rút còn 1 nút bấm là dùng được ngay.
        """
        self._check_price_manager()
        now = fields.Datetime.now()
        self.write({
            "approval_state": "approved",
            "dlm_approved_uid": self.env.uid,
            "dlm_approved_date": now,
        })
        for rec in self:
            has_applied = self.search_count([
                ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                ("is_applied", "=", True),
            ])
            if not has_applied and rec._is_valid_on(fields.Date.context_today(rec)):
                rec._dlm_apply(now)

    def action_reset_draft(self):
        self._check_price_manager()
        for rec in self:
            rec.write({"approval_state": "draft", "is_applied": False})
            product = rec._dlm_product()
            if product:
                product._dlm_recompute_reference_cost()

    def action_set_applied(self):
        """Đánh dấu bảng giá này đang áp dụng cho sản phẩm — tự bỏ áp dụng bảng
        giá khác và cập nhật lại giá vốn tham chiếu."""
        self._check_price_manager()
        for rec in self:
            if rec.approval_state != "approved":
                raise UserError(_("Chỉ có thể áp dụng bảng giá đã duyệt."))
            rec._ensure_currently_valid()
            others = self.search([
                ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                ("is_applied", "=", True),
                ("id", "!=", rec.id),
            ])
            others._dlm_unapply()
            rec._dlm_apply()
            rec._dlm_close_superseded()

    # Nguồn gốc của một dòng giá. Khai lỏng (Char + Integer) vì `dl_product`
    # đứng TRƯỚC `dl_purchase` trong đồ thị phụ thuộc nên không trỏ Many2one
    # sang `dl.purchase.order` được. `dl_purchase` sẽ thêm Many2one thật.
    dlm_source_note = fields.Char(
        string="Nguồn giá", readonly=True, copy=False,
        help="Giá này ở đâu ra: nhập tay, hay chốt từ một đơn mua cụ thể. "
             "Không có nó thì bảng giá là một danh sách con số vô chủ.")

    def _dlm_close_superseded(self):
        """Đóng `Đến ngày` cho các bảng giá CŨ của cùng vật tư + cùng nhà cung cấp.

        Giá cũ bị thay thế thì đúng nghĩa là ĐÃ HẾT HIỆU LỰC — cột "Đến ngày" bỏ
        trống chính là chỗ nói dối: màn hình ghi "Còn hiệu lực / Đã duyệt" cho một
        dòng đã chết 8 tháng, và người dùng bỏ áp dụng dòng hiện hành rồi áp nhầm
        dòng đó là mọi báo giá mới tính theo giá cũ, không một cảnh báo nào.

        Đóng ngày xong thì `_ensure_currently_valid` sẵn có TỰ chặn ca áp nhầm —
        không phải viết thêm lá chắn nào.

        🔴 Chỉ đụng CÙNG nhà cung cấp. Giá của NCC khác là chào giá song song
        (Hoà Phát 215.000 đang áp dụng vs Phú Thịnh 275.000 chờ) — đóng nó là
        xoá mất lựa chọn thay thế."""
        for rec in self:
            moc = rec.date_start or fields.Date.context_today(rec)
            cu = self.sudo().search([
                ("product_tmpl_id", "=", rec.product_tmpl_id.id),
                ("partner_id", "=", rec.partner_id.id),
                ("id", "!=", rec.id),
                ("date_end", "=", False),
                ("date_start", "<=", moc),
            ])
            for dong in cu:
                # max(...) để không bao giờ đẻ ra date_end < date_start — thép
                # đổi giá hai lần trong một ngày là chuyện có thật. Chính ca đó
                # làm `date_end` đóng về đúng HÔM NAY và dòng cũ vẫn lọt bộ lọc
                # "Còn hiệu lực", nên phải đánh dấu thêm bằng cờ.
                dong.write({
                    "date_end": max(dong.date_start, moc - relativedelta(days=1)),
                    "dlm_superseded": True,
                })
        return True

    def action_unset_applied(self):
        self._check_price_manager()
        self._dlm_unapply()
