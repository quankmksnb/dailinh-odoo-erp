from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DlBomTemplate(models.Model):
    """BOM Template — dùng cho Product Group (product_category_id). Một
    Product Group có thể có nhiều BOM Template (nhiều version). Cấu trúc đầu
    BOM giống Product BOM (dl.bom): version/status/Output Quantity, cùng
    workflow xác nhận/khóa/lưu trữ/tạo phiên bản mới — dùng chung qua
    dl.bom.header.mixin. Độc lập với BOM thật, KHÔNG gắn 1 product cụ thể."""

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

    @api.depends("param_ids")
    def _compute_is_parametric(self):
        for rec in self:
            rec.is_parametric = bool(rec.param_ids)

    def _version_domain(self):
        self.ensure_one()
        return [("product_category_id", "=", self.product_category_id.id)]

    @api.onchange("product_category_id")
    def _onchange_category_version(self):
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
        dạng có sẵn. Instance KHÔNG BAO GIỜ là phiên bản hiện hành (§3/§7.4c)."""
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
            "param_signature": Bom._dlm_param_signature(param_values),
        })

        for tline in self.line_ids:
            vals = tline._mixin_copy_vals()
            vals["bom_id"] = bom.id
            for m in tline.param_map_ids:
                base = (param_values or {}).get(m.param_id.code)
                if base in (None, False, ""):
                    continue
                vals[m.target_field] = m.factor * float(base) + m.offset
            line = Line.create(vals)
            # onchange KHÔNG chạy khi tạo qua ORM — tự tính định mức từ hình
            # dạng + kích thước vừa áp, rồi ghi vào quantity (số thực dùng).
            if not line.is_override:
                qty = line._measurement_quantity()
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
