from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class DlBom(models.Model):
    _name = "dl.bom"
    _description = "BOM"
    _inherit = ["mail.thread", "mail.activity.mixin", "dl.bom.header.mixin"]
    _order = "id desc"

    _sql_constraints = [
        (
            "product_version_type_uniq",
            "unique(product_id,version,bom_type)",
            "Phiên bản BOM của sản phẩm đã tồn tại.",
        ),
    ]

    name = fields.Char(
        string="Mã BOM",
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    # Nhóm sản phẩm — CHỈ để lọc nhanh Sản phẩm bên dưới, không phải chủ sở
    # hữu BOM (BOM theo nhóm sản phẩm dùng model riêng dl.bom.template).
    category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm (lọc)",
        ondelete="set null",
    )

    # Data Model refactor: dl.product/dl.semi.product đã hợp nhất vào
    # product.product (phân biệt bằng product_kind). Trước đây tách 2 field
    # product_id (manufactured)/semi_product_id (material_processed) — gộp
    # lại thành 1 field duy nhất vì đều là product.product, domain bao cả 2.
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        tracking=True,
        ondelete="restrict",
        domain="[('product_kind', 'in', ('manufactured', 'material_processed'))]"
               " + ([('categ_id', '=', category_id)] if category_id else [])",
    )

    bom_type = fields.Selection(
        [
            ("template", "BOM mẫu"),
            ("quotation", "BOM báo giá"),
        ],
        string="Loại BOM",
        default="template",
        required=True,
        tracking=True,
    )

    line_ids = fields.One2many(
        "dl.bom.line",
        "bom_id",
        string="Danh sách vật tư",
    )

    total_material_cost = fields.Float(
        string="Tổng chi phí vật tư",
        compute="_compute_total_material_cost",
        store=True,
        digits="Product Price",
    )

    note = fields.Text(
        string="Ghi chú",
    )

    # ── Bản vẽ kỹ thuật của sản phẩm ─────────────────────────────────────
    # Tra theo product_id để KTV vừa xem bản vẽ vừa nhập vật tư vào BOM ngay
    # trên cùng màn (cả màn tạo BOM sản phẩm lẫn wizard tạo BOM khi nhận RFQ).
    # Chỉ đọc, không đụng dữ liệu bản vẽ — ưu tiên bản vẽ đã xác nhận, mới nhất.
    drawing_attachment_id = fields.Many2one(
        "ir.attachment",
        string="File bản vẽ",
        compute="_compute_drawing_ref",
    )
    drawing_mimetype = fields.Char(compute="_compute_drawing_ref")
    drawing_filename = fields.Char(compute="_compute_drawing_ref")

    @api.depends("product_id")
    def _compute_drawing_ref(self):
        Drawing = self.env["dl.drawing"]
        for rec in self:
            drawing = Drawing.browse()
            if rec.product_id:
                domain = [
                    ("product_id", "=", rec.product_id.id),
                    ("attachment_id", "!=", False),
                ]
                drawing = Drawing.search(
                    domain + [("status", "=", "confirmed")],
                    order="version desc", limit=1,
                ) or Drawing.search(domain, order="version desc", limit=1)
            att = drawing.attachment_id
            rec.drawing_attachment_id = att
            rec.drawing_mimetype = att.mimetype if att else False
            rec.drawing_filename = att.name if att else False

    @api.depends("line_ids.subtotal")
    def _compute_total_material_cost(self):
        for rec in self:
            rec.total_material_cost = sum(rec.line_ids.mapped("subtotal"))

    @api.constrains("product_qty")
    def _check_product_qty(self):
        for rec in self:
            if rec.product_qty <= 0:
                raise ValidationError(_("Số lượng đầu ra phải lớn hơn 0."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("dl.bom") or _("New")
        return super().create(vals_list)

    def _version_domain(self):
        self.ensure_one()
        return [("bom_type", "=", self.bom_type), ("product_id", "=", self.product_id.id)]

    @api.onchange("product_id", "bom_type")
    def _onchange_product_version(self):
        if self.product_id:
            self.version = self._compute_next_version()

    def action_create_from_template(self):
        """Product BOM — nút "Create From BOM Template": mở wizard chọn 1
        BOM mẫu (dl.bom.template) rồi copy toàn bộ dòng sang BOM này."""
        self.ensure_one()
        if self.status != "draft":
            raise UserError(_("Chỉ BOM ở trạng thái Nháp mới copy được từ BOM mẫu."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Tạo từ BOM mẫu"),
            "res_model": "dl.bom.from.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bom_id": self.id},
        }
