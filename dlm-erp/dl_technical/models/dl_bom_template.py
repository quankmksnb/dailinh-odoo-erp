from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DlBomTemplate(models.Model):
    """BOM mẫu — model này gánh HAI loại mẫu khác hẳn nhau, đọc kỹ trước khi sửa.

    ① **Mẫu chép tay** (không tham số, `generic_product_id` trống)
       "Hàng loại này thường gồm những vật tư gì". KTV mở BOM mới rồi bấm
       *Tạo từ BOM mẫu* để chép dòng. Neo theo **NHÓM sản phẩm** — đúng bản
       chất, vì nó chỉ là gợi ý vật tư cho cả một nhóm.

    ② **Mẫu tham số** (có `param_ids` + `generic_product_id`)
       Nhập D/R/C → ánh xạ tuyến tính tự sinh kích thước cắt từng thanh.
       Neo theo **SẢN PHẨM DÙNG CHUNG**.

    🔴 Loại ② TỪNG neo theo nhóm và đó là lỗi kiến trúc (sửa 2026-08-19): nhóm
    sản phẩm là trục THƯƠNG MẠI (Sales sở hữu, để tính doanh số và áp chính
    sách giá), còn mẫu tham số là trục KẾT CẤU. Ép hai trục làm một thì ràng
    buộc "một nhóm một mẫu" chặn mất các kết cấu còn lại: nhóm "Bàn ghế học
    sinh" ngoài đời có ít nhất 5 kết cấu (bàn liền ghế có tựa / không tựa /
    bàn ghế rời / bàn giáo viên có hộc tủ / bàn vi tính), chỉ một cái khai được
    mẫu. Nay mỗi kết cấu một sản phẩm dùng chung, mỗi sản phẩm một dòng dõi mẫu.
    """

    _name = "dl.bom.template"
    _description = "BOM mẫu"
    _inherit = ["mail.thread", "mail.activity.mixin", "dl.bom.header.mixin"]
    _order = "name"

    # Không dùng _sql_constraints: hai loại mẫu đánh số phiên bản trên hai trục
    # khác nhau, mà UNIQUE thường không kèm được điều kiện. Hai index BỘ PHẬN ở
    # `init()` bên dưới làm đúng việc đó, vẫn giữ được chốt chặn ở tầng DB.

    def init(self):
        """Hai dòng dõi phiên bản tách biệt, chốt bằng unique index bộ phận."""
        super().init()
        self._cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dl_bom_template_generic_version_uniq
                ON dl_bom_template (generic_product_id, version)
             WHERE generic_product_id IS NOT NULL
        """)
        self._cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dl_bom_template_categ_version_uniq
                ON dl_bom_template (product_category_id, version)
             WHERE generic_product_id IS NULL
        """)

    name = fields.Char(string="Tên BOM mẫu", required=True, tracking=True)
    # Chỉ nhóm thuộc 2 nhánh chuẩn (Thành phẩm cho SP gia công, Vật tư cho
    # nhóm Bán thành phẩm — BTP cũng có BOM); loại nhóm hệ thống/mồ côi.
    product_category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm",
        required=True,
        ondelete="restrict",
        tracking=True,
        domain=[("dl_branch", "in", ("finished", "material"))],
    )
    line_ids = fields.One2many(
        "dl.bom.template.line", "bom_template_id", string="Dòng mẫu",
        # Odoo mặc định không copy o2m khi duplicate — bật để "Tạo phiên bản
        # mới" của BOM mẫu mang theo dòng (đồng bộ với dl.bom.line_ids).
        copy=True,
    )

    # ── Đợt 4 — tham số cấp sản phẩm (D/R/C) ────────────────────────────────
    param_ids = fields.One2many(
        "dl.bom.template.param", "bom_template_id", string="Tham số", copy=True)
    is_parametric = fields.Boolean(
        string="Có tham số (sinh định mức)", compute="_compute_is_parametric",
        store=True)

    @api.depends("param_ids")
    def _compute_is_parametric(self):
        for rec in self:
            rec.is_parametric = bool(rec.param_ids)

    # Sản phẩm GENERIC của mẫu — SP dùng chung cho MỌI kích thước sinh ra từ mẫu
    # này. Không có field này thì workspace RFQ không có cách nào dẫn Kỹ thuật về
    # sản phẩm dùng chung, và mỗi cỡ lại đẻ một mã SP mới.
    generic_product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm dùng chung",
        domain=[("product_kind", "=", "manufactured")],
        ondelete="restrict",
        tracking=True,
        help="Sản phẩm đại diện cho MỌI kích thước sinh từ mẫu này. Mỗi đơn chỉ "
             "sinh thêm một định mức (instance), KHÔNG đẻ sản phẩm mới.",
    )
    generic_missing = fields.Boolean(
        string="Chưa gán sản phẩm dùng chung", compute="_compute_generic_missing")

    @api.depends("is_parametric", "status", "generic_product_id")
    def _compute_generic_missing(self):
        for rec in self:
            rec.generic_missing = bool(
                rec.is_parametric
                and rec.status in ("confirmed", "locked")
                and not rec.generic_product_id)

    # ── 🔴 SP dùng chung KHÔNG được tồn kho (Kho §3.5) ───────────────────────
    # Odoo giữ hàng (reserve) theo product_id, KHÔNG theo kích thước. Nếu SP dùng
    # chung là storable và trong kho có 5 "Bàn thép" gồm nhiều cỡ, một đơn đặt
    # 1200×800 sẽ được giữ nhầm một cái 1000×600 rồi báo "đủ hàng" — tới lúc giao
    # mới lộ. Không chặn được bằng cấu hình; phải đè cơ chế reservation của Odoo.
    # ⇒ Ép 'consu' ngay tại nơi TÍNH GENERIC được khai. Cấu hình nào cần tồn kho
    # thì thăng hạng thành SKU riêng — lúc đó reserve theo product_id lại ĐÚNG.
    #
    # Ép ở đây (dl_technical) chứ không ở dl_product vì dl_product KHÔNG depends
    # dl_technical ⇒ không thấy được model này.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._dlm_enforce_generic_not_stocked()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "generic_product_id" in vals:
            self._dlm_enforce_generic_not_stocked()
        return res

    def _dlm_enforce_generic_not_stocked(self):
        """SP dùng chung ⇒ detailed_type='consu'. sudo vì Kỹ thuật không có
        quyền ghi loại lưu kho của sản phẩm."""
        products = self.mapped("generic_product_id").filtered(
            lambda p: p.detailed_type == "product")
        if products:
            products.sudo().product_tmpl_id.write({"detailed_type": "consu"})

    @api.constrains("generic_product_id", "product_category_id")
    def _check_generic_product_category(self):
        """Nhóm của mẫu phải bằng nhóm của sản phẩm dùng chung.

        Nhóm nay là thông tin SUY RA từ sản phẩm (xem `_onchange_category_version`);
        ràng buộc này giữ cho hai chỗ không trôi khỏi nhau khi ghi qua
        import/RPC — Sales lọc kiểu hàng theo nhóm, lệch là mất mẫu khỏi danh
        sách mà không có lỗi nào nổ."""
        for rec in self:
            product = rec.generic_product_id
            if product and product.categ_id != rec.product_category_id:
                raise ValidationError(_(
                    "Sản phẩm dùng chung “%(p)s” thuộc nhóm “%(pc)s”, không "
                    "khớp nhóm “%(c)s” của mẫu.",
                    p=product.display_name,
                    pc=product.categ_id.display_name or _("chưa phân nhóm"),
                    c=rec.product_category_id.display_name))

    @api.constrains("is_parametric", "generic_product_id", "status")
    def _check_parametric_needs_generic(self):
        """Mẫu THAM SỐ đã duyệt bắt buộc có sản phẩm dùng chung.

        Từ 2026-08-19 sản phẩm dùng chung là NEO của mẫu tham số, không còn là
        tuỳ chọn: nó vừa là đích của mọi kích thước sinh ra, vừa là thứ Sales
        chọn ở ô "Kiểu hàng". Mẫu tham số không có neo thì không ai tới được
        nó — duyệt xong nằm im, và `_version_domain` cũng không biết đánh số
        theo trục nào."""
        for rec in self:
            if (rec.is_parametric and not rec.generic_product_id
                    and rec.status in ("confirmed", "locked")):
                raise ValidationError(_(
                    "BOM mẫu “%s” có tham số nhưng chưa gán Sản phẩm dùng chung. "
                    "Gán sản phẩm đại diện cho họ này rồi xác nhận lại — đó là "
                    "thứ Sales chọn ở ô Kiểu hàng."
                ) % rec.name)

    def _version_domain(self):
        """Đánh số phiên bản theo ĐÚNG trục mà mẫu này neo vào.

        Mẫu tham số nối tiếp nhau theo SẢN PHẨM dùng chung; mẫu chép tay nối
        tiếp theo NHÓM. Dùng chung một trục thì hai kết cấu trong cùng nhóm sẽ
        tranh số phiên bản của nhau."""
        self.ensure_one()
        if self.generic_product_id:
            return [("generic_product_id", "=", self.generic_product_id.id)]
        return [
            ("product_category_id", "=", self.product_category_id.id),
            ("generic_product_id", "=", False),
        ]

    @api.onchange("product_category_id", "generic_product_id")
    def _onchange_category_version(self):
        # Sản phẩm dùng chung quyết định luôn nhóm — một nguồn sự thật, và khớp
        # sẵn ràng buộc _check_generic_product_category.
        if self.generic_product_id:
            self.product_category_id = self.generic_product_id.categ_id
        if self.product_category_id:
            self.version = self._compute_next_version()

    # ── Đợt 4 — bộ sinh định mức tham số (thiết kế §7.4d) ────────────────────
    def _dlm_validate_param_values(self, param_values):
        """Kiểm bộ tham số KTV nhập: đủ tham số bắt buộc + trong miền hợp lệ
        (RES-018/019 · EX-27 — KHÔNG tự kẹp về biên, nêu rõ giới hạn nào vượt)."""
        self.ensure_one()
        param_values = param_values or {}
        for p in self.param_ids:
            raw = param_values.get(p.code)
            if raw in (None, False, ""):
                if p.required:
                    raise UserError(_(
                        "Thiếu tham số bắt buộc: %(name)s (%(code)s).",
                        name=p.name, code=p.code))
                continue
            value = float(raw)
            if p.value_min and value < p.value_min:
                raise UserError(_(
                    "Tham số %(name)s = %(val)s nhỏ hơn giá trị tối thiểu "
                    "%(min)s của mẫu.",
                    name=p.name, val=value, min=p.value_min))
            if p.value_max and value > p.value_max:
                raise UserError(_(
                    "Tham số %(name)s = %(val)s vượt giá trị tối đa %(max)s "
                    "của mẫu.",
                    name=p.name, val=value, max=p.value_max))

    def generate_instance(self, product, param_values, rfq_line=None):
        """Sinh một BOM báo giá (INSTANCE) cho MỘT đơn từ mẫu tham số này.

        Trình tự (§7.4d): validate tham số → mỗi dòng mẫu copy field dùng chung
        rồi ÁP ánh xạ tuyến tính (target = factor × tham số + offset) → tạo
        dl.bom kiểu 'quotation' (is_rfq_provisional) → tính lại định mức từ hình
        dạng có sẵn. Instance KHÔNG BAO GIỜ là phiên bản hiện hành (§3/§7.4c).

        Trả về định mức ĐÃ CÓ nếu cấu hình này từng được chốt (RES-028) — caller
        phải kiểm ``is_rfq_provisional``/``status`` nếu cần biết là bản mới hay
        bản tái dùng."""
        self.ensure_one()
        if not self.param_ids:
            raise UserError(_(
                "BOM mẫu \"%s\" chưa khai tham số nào — không sinh được định "
                "mức tự động.") % self.display_name)
        if self.status not in ("confirmed", "locked"):
            raise UserError(_(
                "Chỉ BOM mẫu đã xác nhận mới dùng để sinh định mức. \"%s\" đang "
                "ở trạng thái Nháp.") % self.display_name)
        self._dlm_validate_param_values(param_values)

        Bom = self.env["dl.bom"]
        Line = self.env["dl.bom.line"]
        signature = Bom._dlm_param_signature(param_values)

        # RES-028 — cùng sản phẩm + cùng bộ tham số nghĩa là ĐÃ có định mức cho
        # cấu hình này: tái dùng thay vì đẻ bản trùng nội dung. BOM chỉ lưu KẾT
        # CẤU (giá được snapshot ở báo giá) nên nhiều đơn dùng chung một định mức
        # là đúng. Chỉ nhận bản đã chốt và KHÔNG còn tạm — bản nháp đang gắn dòng
        # RFQ khác có thể bị sửa/dọn bất cứ lúc nào, tái dùng sẽ hỏng chéo hai đơn.
        reusable = Bom.search([
            ("product_id", "=", product.id),
            ("bom_type", "=", "quotation"),
            ("param_signature", "=", signature),
            ("status", "in", ("confirmed", "locked")),
            ("is_rfq_provisional", "=", False),
        ], limit=1)
        if reusable:
            return reusable

        existing = Bom.search([
            ("product_id", "=", product.id), ("bom_type", "=", "quotation")])
        version = (max(existing.mapped("version")) + 1) if existing else 1

        bom = Bom.create({
            "product_id": product.id,
            "category_id": product.categ_id.id or False,
            "bom_type": "quotation",
            "status": "draft",
            "version": version,
            "product_qty": self.product_qty or 1.0,
            "is_rfq_provisional": True,
            "rfq_source_line_id": rfq_line.id if rfq_line else False,
            "source_template_id": self.id,
            "source_template_version": self.version,
            "param_values": dict(param_values or {}),
            "param_signature": signature,
        })

        for tline in self.line_ids:
            vals = tline._mixin_copy_vals()
            vals["bom_id"] = bom.id
            for m in tline.param_map_ids:
                base = (param_values or {}).get(m.param_id.code)
                if base in (None, False, ""):
                    continue
                value = m.factor * float(base) + m.offset
                # piece_count là Integer — ánh xạ tuyến tính trả float, ép về int
                # để không ghi 3.9999 rồi bị cắt cụt âm thầm.
                vals[m.target_field] = (
                    int(round(value)) if m.target_field == "piece_count" else value)
            line = Line.create(vals)
            # onchange KHÔNG chạy khi tạo qua ORM — tự tính định mức từ kích
            # thước cắt vừa áp, rồi ghi vào quantity (số thực dùng).
            if not line.is_override:
                qty = line._dlm_auto_quantity()
                if qty is not None and qty > 0:
                    line.quantity = qty
        return bom


class DlBomTemplateLine(models.Model):
    _name = "dl.bom.template.line"
    _description = "Dòng BOM mẫu"
    _inherit = ["dl.bom.line.mixin"]
    _order = "id"

    bom_template_id = fields.Many2one(
        "dl.bom.template",
        string="BOM mẫu",
        required=True,
        ondelete="cascade",
    )

    # Đợt 4 — ánh xạ tham số sản phẩm vào các ô kích thước của dòng này.
    param_map_ids = fields.One2many(
        "dl.bom.template.line.param.map", "template_line_id",
        string="Ánh xạ tham số", copy=True)

    note = fields.Char(string="Ghi chú")
