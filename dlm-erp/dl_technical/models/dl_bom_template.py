from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DlBomTemplate(models.Model):
    # BOM mẫu dùng chung cho 1 Nhóm sản phẩm (không gắn 1 sản phẩm cụ thể) — màn "BOM mẫu".

    _name = "dl.bom.template"
    _description = "BOM mẫu"
    _inherit = ["mail.thread", "mail.activity.mixin", "dl.bom.header.mixin"]
    _order = "name"

    _sql_constraints = [
        (
            "category_version_uniq",
            "unique(product_category_id,version)",
            "Phiên bản BOM mẫu của nhóm sản phẩm đã tồn tại.",
        ),
    ]

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

    # Cờ "Có tham số (sinh định mức)" trên form BOM mẫu — bật khi mẫu có khai tham số.
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

    # Bật banner cảnh báo trên form BOM mẫu: mẫu tham số đã duyệt nhưng chưa gán Sản phẩm dùng chung.
    @api.depends("is_parametric", "status", "generic_product_id")
    def _compute_generic_missing(self):
        for rec in self:
            rec.generic_missing = bool(
                rec.is_parametric
                and rec.status in ("confirmed", "locked")
                and not rec.generic_product_id)

    # Khi tạo BOM mẫu, ép luôn Sản phẩm dùng chung về loại "không tồn kho" (xem _dlm_enforce_generic_not_stocked).
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._dlm_enforce_generic_not_stocked()
        return records

    # Khi đổi Sản phẩm dùng chung trên form BOM mẫu, ép lại về loại "không tồn kho".
    def write(self, vals):
        res = super().write(vals)
        if "generic_product_id" in vals:
            self._dlm_enforce_generic_not_stocked()
        return res

    # Ép Sản phẩm dùng chung thành "Vật tư tiêu hao" (không quản lý tồn kho) — Odoo giữ hàng theo mã sản phẩm chứ không theo size, để tồn kho sẽ giữ nhầm hàng sai size.
    def _dlm_enforce_generic_not_stocked(self):
        products = self.mapped("generic_product_id").filtered(
            lambda p: p.detailed_type == "product")
        if products:
            products.sudo().product_tmpl_id.write({"detailed_type": "consu"})

    # Validate lúc lưu BOM mẫu: Sản phẩm dùng chung phải cùng Nhóm sản phẩm với mẫu.
    @api.constrains("generic_product_id", "product_category_id")
    def _check_generic_product_category(self):
        for rec in self:
            product = rec.generic_product_id
            if product and product.categ_id != rec.product_category_id:
                raise ValidationError(_(
                    "Sản phẩm dùng chung “%(p)s” thuộc nhóm “%(pc)s”, không "
                    "khớp nhóm “%(c)s” của mẫu.",
                    p=product.display_name,
                    pc=product.categ_id.display_name or _("chưa phân nhóm"),
                    c=rec.product_category_id.display_name))

    # Phạm vi tìm phiên bản cùng BOM mẫu = cùng Nhóm sản phẩm (dùng bởi mixin vòng đời).
    def _version_domain(self):
        self.ensure_one()
        return [("product_category_id", "=", self.product_category_id.id)]

    # Khi đổi Nhóm sản phẩm trên form BOM mẫu mới, tự gợi ý số phiên bản kế tiếp.
    @api.onchange("product_category_id")
    def _onchange_category_version(self):
        if self.product_category_id:
            self.version = self._compute_next_version()

    # Validate bộ tham số KTV nhập ở panel "Sinh định mức": đủ tham số bắt buộc + nằm trong khoảng min/max.
    def _dlm_validate_param_values(self, param_values):
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

    # Nút "Sinh định mức" ở panel tham số trong wizard xử lý RFQ — sinh (hoặc tái dùng nếu đã có) 1 BOM thật từ bộ kích thước KTV vừa nhập.
    def generate_instance(self, product, param_values, rfq_line=None):
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

        # Cùng sản phẩm + cùng bộ tham số = đã có sẵn định mức này rồi, tái dùng thay vì tạo trùng.
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
