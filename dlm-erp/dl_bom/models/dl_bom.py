from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class DlBom(models.Model):
    _name = "dl.bom"
    _description = "BOM"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    _sql_constraints = [
        (
            "product_version_type_uniq",
            "unique(product_id,version,bom_type)",
            "Phiên bản BOM của thành phẩm đã tồn tại.",
        ),
        (
            "semi_version_type_uniq",
            "unique(semi_product_id,version,bom_type)",
            "Phiên bản BOM của bán thành phẩm đã tồn tại.",
        ),
        (
            "category_version_type_uniq",
            "unique(category_id,version,bom_type)",
            "Phiên bản BOM mẫu của nhóm sản phẩm đã tồn tại.",
        ),
    ]

    name = fields.Char(
        string="Mã BOM",
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )

    product_id = fields.Many2one(
        "dl.product",
        string="Thành phẩm",
        tracking=True,
        ondelete="restrict",
    )

    semi_product_id = fields.Many2one(
        "dl.semi.product",
        string="Bán thành phẩm",
        tracking=True,
        ondelete="restrict",
    )

    category_id = fields.Many2one(
        "dl.product.category",
        string="Nhóm sản phẩm",
        tracking=True,
        ondelete="restrict",
    )

    version = fields.Integer(
        string="Phiên bản",
        default=1,
        required=True,
        tracking=True,
    )

    product_qty = fields.Float(
        string="Số lượng đầu ra",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
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

    status = fields.Selection(
        [
            ("draft", "Nháp"),
            ("confirmed", "Đã xác nhận"),
            ("locked", "Đã khóa"),
            ("archived", "Lưu trữ"),
        ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        copy=False,
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

    @api.depends("line_ids.subtotal")
    def _compute_total_material_cost(self):
        for rec in self:
            rec.total_material_cost = sum(rec.line_ids.mapped("subtotal"))

    @api.constrains("product_id", "semi_product_id", "category_id")
    def _check_owner_xor(self):
        for rec in self:
            count = sum(
                bool(x)
                for x in [
                    rec.product_id,
                    rec.semi_product_id,
                    rec.category_id,
                ]
            )
            if count != 1:
                raise ValidationError(
                    _("BOM chỉ được phép gắn với một trong ba đối tượng: Thành phẩm, Bán thành phẩm hoặc Nhóm sản phẩm.")
                )

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

    def action_confirm(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError(_("Chỉ BOM ở trạng thái Nháp mới được xác nhận."))
            if not rec.line_ids:
                raise UserError(_("BOM phải có ít nhất một dòng vật tư."))
            rec.status = "confirmed"

    def action_lock(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ BOM đã xác nhận mới được khóa."))
            rec.status = "locked"

    def action_archive(self):
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("Không thể lưu trữ BOM đã khóa."))
            rec.status = "archived"

    def action_reset_draft(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ BOM đã xác nhận mới được chuyển về Nháp."))
            rec.status = "draft"

    def action_create_new_version(self):
        self.ensure_one()

        domain = [
            ("bom_type", "=", self.bom_type),
        ]

        if self.product_id:
            domain.append(("product_id", "=", self.product_id.id))

        if self.semi_product_id:
            domain.append(("semi_product_id", "=", self.semi_product_id.id))

        if self.category_id:
            domain.append(("category_id", "=", self.category_id.id))

        max_version = max(
            self.search(domain).mapped("version") or [0]
        )

        new_bom = self.copy({
            "version": max_version + 1,
            "status": "draft",
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "dl.bom",
            "view_mode": "form",
            "res_id": new_bom.id,
            "target": "current",
        }

    def write(self, vals):
        # TDS §3.3 dl.bom.status: "locked chặn UPDATE/DELETE — sửa phải tạo
        # version mới". Cho phép đổi status (action_archive) và các field nội
        # bộ của chatter (mail.thread) đi qua bình thường.
        allowed = {"status", "message_main_attachment_id", "message_follower_ids"}
        for rec in self:
            if rec.status == "locked" and set(vals.keys()) - allowed:
                raise UserError(_(
                    "BOM đã khóa không thể sửa — hãy tạo phiên bản mới."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.status == "locked":
                raise UserError(_("BOM đã khóa không thể xóa."))
        return super().unlink()