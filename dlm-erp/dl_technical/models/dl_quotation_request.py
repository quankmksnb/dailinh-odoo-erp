from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

# Field-level RBAC (giống dl.material): chỉ Kỹ thuật/Admin được quyết định
# "sản phẩm xác định" / "không khả thi" — đây là đánh giá kỹ thuật, Sales chỉ
# được nhập yêu cầu (product_name/product_category_id/quantity/dimension_note).
_TECH_ONLY_LINE_FIELDS = {'resolved_product_id', 'is_infeasible', 'infeasible_reason'}


class DlQuotationRequest(models.Model):
    _name = "dl.quotation.request"
    _description = "Yêu cầu báo giá"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    _sql_constraints = [
        (
            "name_uniq",
            "unique(name)",
            "Mã yêu cầu báo giá đã tồn tại.",
        ),
    ]

    name = fields.Char(
        string="Mã yêu cầu",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
        default=lambda self: _("New"),
    )

    customer_id = fields.Many2one(
        "res.partner",
        string="Khách hàng",
        required=True,
        tracking=True,
        domain=[("partner_role", "in", ("customer", "both"))],
    )

    description = fields.Text(
        string="Mô tả",
    )

    requested_date = fields.Datetime(
        string="Ngày nhận yêu cầu",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )

    deadline = fields.Date(
        string="Hạn yêu cầu",
    )

    status = fields.Selection(
        [
            ("new", "Mới"),
            ("processing", "Đang xử lý"),
            ("confirmed", "Đã xử lý xong"),
            ("quoted", "Đã tạo báo giá"),
            ("cancelled", "Đã hủy"),
        ],
        string="Trạng thái",
        default="new",
        readonly=True,
        copy=False,
        tracking=True,
    )

    created_by = fields.Many2one(
        "res.users",
        string="Người tạo",
        readonly=True,
        default=lambda self: self.env.user,
    )

    note = fields.Text(
        string="Ghi chú",
    )

    line_ids = fields.One2many(
        "dl.quotation.request.line",
        "quotation_request_id",
        string="Danh sách sản phẩm",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("dl.quotation.request")
                    or _("New")
                )
        return super().create(vals_list)

    def _recompute_status_from_lines(self):
        for rec in self:

            if rec.status in ("quoted", "cancelled"):
                continue

            if not rec.line_ids:
                status = "new"

            elif all(
                line.resolved_product_id or line.is_infeasible
                for line in rec.line_ids
            ):
                status = "confirmed"

            elif any(
                line.resolved_product_id or line.is_infeasible
                for line in rec.line_ids
            ):
                status = "processing"

            else:
                status = "new"

            if rec.status != status:
                rec.status = status

    def action_cancel(self):
        self.write({
            "status": "cancelled",
        })

    def action_mark_quoted(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(
                    _("Chỉ yêu cầu báo giá đã xử lý xong mới được đánh dấu đã tạo báo giá.")
                )

        self.write({
            "status": "quoted",
        })


class DlQuotationRequestLine(models.Model):
    _name = "dl.quotation.request.line"
    _description = "Dòng yêu cầu báo giá"
    _order = "id"

    quotation_request_id = fields.Many2one(
        "dl.quotation.request",
        string="Yêu cầu báo giá",
        required=True,
        ondelete="cascade",
    )

    product_name = fields.Char(
        string="Tên sản phẩm",
        required=True,
    )

    product_category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm",
    )

    quantity = fields.Float(
        string="Số lượng",
        required=True,
        default=1.0,
    )

    dimension_note = fields.Text(
        string="Kích thước / Yêu cầu",
    )

    resolved_product_id = fields.Many2one(
        "dl.product",
        string="Sản phẩm xác định",
    )

    is_infeasible = fields.Boolean(
        string="Không khả thi",
        default=False,
    )

    infeasible_reason = fields.Text(
        string="Lý do không khả thi",
    )

    # dùng để readonly field trên view theo nhóm quyền — compute_sudo=True vì
    # user không thuộc dl_group_tech vẫn phải đọc được field này để tính readonly.
    is_technician = fields.Boolean(
        compute='_compute_is_technician', compute_sudo=True,
        default=lambda self: (
            self.env.user.has_group('dl_base.dl_group_tech')
            or self.env.user.has_group('dl_base.dl_group_admin')))

    def _compute_is_technician(self):
        is_tech = (self.env.user.has_group('dl_base.dl_group_tech')
                   or self.env.user.has_group('dl_base.dl_group_admin'))
        for rec in self:
            rec.is_technician = is_tech

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(
                    _("Số lượng phải lớn hơn 0.")
                )

    @api.constrains("resolved_product_id", "is_infeasible")
    def _check_resolution(self):
        for rec in self:
            if rec.resolved_product_id and rec.is_infeasible:
                raise ValidationError(
                    _("Không được vừa chọn sản phẩm vừa đánh dấu không khả thi.")
                )

    @api.constrains("is_infeasible", "infeasible_reason")
    def _check_infeasible_reason(self):
        for rec in self:
            if rec.is_infeasible and not rec.infeasible_reason:
                raise ValidationError(
                    _("Vui lòng nhập lý do không khả thi.")
                )

    @api.constrains("resolved_product_id")
    def _check_product_has_bom(self):
        for rec in self:
            if rec.resolved_product_id:
                bom_count = self.env["dl.bom"].search_count([
                    ("product_id", "=", rec.resolved_product_id.id),
                    ("status", "in", ("confirmed", "locked")),
                ])

                if not bom_count:
                    raise ValidationError(
                        _("Sản phẩm phải có BOM ở trạng thái Đã xác nhận hoặc Đã khóa.")
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("quotation_request_id")._recompute_status_from_lines()
        return records

    def write(self, vals):
        if not self.env.su and _TECH_ONLY_LINE_FIELDS & vals.keys():
            user = self.env.user
            if not (user.has_group('dl_base.dl_group_tech')
                     or user.has_group('dl_base.dl_group_admin')):
                raise AccessError(_(
                    'Chỉ Kỹ thuật hoặc Admin được quyết định "Sản phẩm xác định" '
                    '/ "Không khả thi" — đây là đánh giá kỹ thuật.'))

        res = super().write(vals)

        if {"resolved_product_id", "is_infeasible"} & set(vals.keys()):
            self.mapped("quotation_request_id")._recompute_status_from_lines()

        return res

    def unlink(self):
        requests = self.mapped("quotation_request_id")
        res = super().unlink()
        requests._recompute_status_from_lines()
        return res