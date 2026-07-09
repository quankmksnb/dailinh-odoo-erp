from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlDrawing(models.Model):
    _name = "dl.drawing"
    _description = "Bản vẽ kỹ thuật"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "drawing_code"

    _sql_constraints = [
        (
            "drawing_code_uniq",
            "unique(drawing_code)",
            "Mã bản vẽ đã tồn tại.",
        ),
        (
            "product_version_uniq",
            "unique(product_id, version)",
            "Phiên bản bản vẽ của sản phẩm đã tồn tại.",
        ),
    ]

    name = fields.Char(
        string="Tên bản vẽ",
        required=True,
        tracking=True,
    )

    product_id = fields.Many2one(
        "dl.product",
        string="Sản phẩm",
        required=True,
        tracking=True,
    )

    drawing_code = fields.Char(
        string="Mã bản vẽ",
        required=True,
        copy=False,
        tracking=True,
        default=lambda self: _("New"),
    )

    version = fields.Integer(
        string="Phiên bản",
        default=1,
        required=True,
        tracking=True,
    )

    status = fields.Selection(
        [
            ("draft", "Nháp"),
            ("confirmed", "Đã xác nhận"),
            ("archived", "Lưu trữ"),
        ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        copy=False,
    )

    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Bản vẽ đính kèm",
    )

    confirmed_date = fields.Date(
        string="Ngày xác nhận",
        readonly=True,
    )

    created_by = fields.Many2one(
        "res.users",
        string="Người tạo",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("drawing_code", _("New")) == _("New"):
                vals["drawing_code"] = (
                    self.env["ir.sequence"].next_by_code("dl.drawing")
                    or _("New")
                )
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError(_("Chỉ bản vẽ ở trạng thái Nháp mới được xác nhận."))

            if not rec.attachment_id:
                raise UserError(_("Vui lòng đính kèm file bản vẽ trước khi xác nhận."))

            rec.write({
                "status": "confirmed",
                "confirmed_date": fields.Date.today(),
            })

    def action_archive(self):
        for rec in self:
            if rec.status == "draft":
                raise UserError(_("Không thể lưu trữ bản vẽ khi đang ở trạng thái Nháp."))

            rec.write({
                "status": "archived",
            })

    def action_reset_draft(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ bản vẽ đã xác nhận mới được chuyển về Nháp."))

            rec.write({
                "status": "draft",
                "confirmed_date": False,
            })