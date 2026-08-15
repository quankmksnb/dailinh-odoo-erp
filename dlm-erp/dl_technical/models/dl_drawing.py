from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# LK-05 (§3.2-D3) — bản vẽ chỉ có nghĩa với SP có kết cấu (gia công / bán thành
# phẩm). Gắn cho vật tư thô / SP thương mại là vô nghĩa.
DRAWING_ELIGIBLE_KINDS = ("manufactured", "material_processed")


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
        "product.product",
        string="Sản phẩm",
        required=True,
        tracking=True,
        # LK-05 — chỉ SP gia công / bán thành phẩm mới có bản vẽ kỹ thuật.
        domain=[("product_kind", "in", DRAWING_ELIGIBLE_KINDS)],
    )

    # D4 (§3.2-D4) — "bản vẽ hiện hành" tường minh thay vì suy "confirmed mới
    # nhất". Confirm bản mới tự bỏ cờ ở bản cũ cùng sản phẩm (auto-supersede).
    is_current = fields.Boolean(
        string="Bản vẽ hiện hành", readonly=True, copy=False, default=False)

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

    # Validate lúc lưu bản vẽ: chặn gắn bản vẽ cho vật tư thô / sản phẩm thương mại.
    @api.constrains("product_id")
    def _check_product_kind(self):
        for rec in self:
            if rec.product_id and rec.product_id.product_kind not in DRAWING_ELIGIBLE_KINDS:
                raise ValidationError(_(
                    "Sản phẩm “%s” không phải sản phẩm gia công / bán thành phẩm — "
                    "không gắn bản vẽ kỹ thuật cho loại này."
                ) % rec.product_id.display_name)

    # Nút "Xác nhận" trên form Bản vẽ — bắt buộc đã đính kèm file, xong thì đặt làm bản vẽ hiện hành và nhắc Kỹ thuật rà lại BOM.
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
            rec._set_current_drawing()
            rec._notify_boms_drawing_updated()

    # Đặt bản ghi này làm bản vẽ hiện hành của sản phẩm, tự bỏ cờ hiện hành ở bản vẽ khác cùng sản phẩm.
    def _set_current_drawing(self):
        for rec in self:
            others = self.search([
                ("product_id", "=", rec.product_id.id),
                ("id", "!=", rec.id),
                ("is_current", "=", True),
            ])
            if others:
                others.write({"is_current": False})
            if not rec.is_current:
                rec.is_current = True

    # Đăng thông báo + tạo việc nhắc trên các BOM chưa khóa của sản phẩm để Kỹ thuật rà lại định mức khi bản vẽ đổi.
    def _notify_boms_drawing_updated(self):
        Bom = self.env["dl.bom"].sudo()
        for rec in self:
            boms = Bom.search([
                ("product_id", "=", rec.product_id.id),
                ("status", "in", ("draft", "confirmed")),
            ])
            for bom in boms:
                bom.message_post(body=_(
                    "Bản vẽ kỹ thuật đã cập nhật phiên bản v%(v)s — rà lại định "
                    "mức nếu kích thước thay đổi.", v=rec.version))
                if self.env.user and not self.env.user.share:
                    bom.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=_("Rà định mức theo bản vẽ mới v%s") % rec.version,
                        user_id=self.env.uid)

    # Nút "Lưu trữ" trên form Bản vẽ.
    def action_archive(self):
        for rec in self:
            if rec.status == "draft":
                raise UserError(_("Không thể lưu trữ bản vẽ khi đang ở trạng thái Nháp."))

            rec.write({
                "status": "archived",
                "is_current": False,
            })

    # Nút "Về nháp" trên form Bản vẽ.
    def action_reset_draft(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(_("Chỉ bản vẽ đã xác nhận mới được chuyển về Nháp."))

            rec.write({
                "status": "draft",
                "confirmed_date": False,
                "is_current": False,
            })