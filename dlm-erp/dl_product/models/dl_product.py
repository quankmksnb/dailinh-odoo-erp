from odoo import api, fields, models


class DlProduct(models.Model):
    _name = "dl.product"
    _inherits = {"product.product": "product_id"}
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Thành phẩm"
    _order = "default_code"

    _sql_constraints = [
        (
            "product_id_uniq",
            "unique(product_id)",
            "Sản phẩm Odoo này được liên kết với một thành phẩm khác.",
        )
    ]

    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Phân loại
    # category_id / categ_id: dùng categ_id native proxy qua product_id.
    # Không khai lại ở đây — view XML dùng tên 'categ_id'

    supply_type = fields.Selection(
        [
            ("manufactured", "Gia công"),
            ("trading", "Thương mại"),
        ],
        string="Loại cung ứng",
        required=True,
        default="manufactured",
        tracking=True,
    )

    purchase_cost = fields.Monetary(
        string="Giá vốn nhập", help="Chỉ điền khi loại cung ứng là Thương mại."
    )

    default_supplier_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp mặc định",
        domain="[('partner_role', 'in', ['supplier', 'both'])]",
    )

    # ── Thuộc tính kỹ thuật
    dim_length = fields.Float(string="Dài (mm)")
    dim_width = fields.Float(string="Rộng (mm)")
    dim_height = fields.Float(string="Cao (mm)")
    dim_display = fields.Char(
        string="Kích thước", compute="_compute_dim_display", store=True
    )
    main_material = fields.Char(
        string="Vật liệu chính", help="VD: Thép CT3, Inox 304, Nhôm..."
    )
    thickness = fields.Float(string="Độ dày (mm)")
    finish = fields.Selection(
        [
            ("powder", "Sơn tĩnh điện"),
            ("galv", "Mạ kẽm"),
            ("raw", "Để nguyên"),
        ],
        string="Lớp hoàn thiện",
    )
    est_weight = fields.Float(string="Khối lượng ước tính (kg)")
    tech_note = fields.Text(string="Ghi chú kỹ thuật")

    status_display = fields.Char(string="Trạng thái", compute="_compute_status_display")

    @api.depends("active")
    def _compute_status_display(self):
        for rec in self:
            rec.status_display = "Đang sản xuất" if rec.active else "Ngừng sản xuất"

    @api.depends("dim_length", "dim_width", "dim_height")
    def _compute_dim_display(self):
        for rec in self:
            if rec.dim_length or rec.dim_width or rec.dim_height:
                rec.dim_display = "%g × %g × %g mm" % (
                    rec.dim_length or 0,
                    rec.dim_width or 0,
                    rec.dim_height or 0,
                )
            else:
                rec.dim_display = ""

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("default_code"):
                vals["default_code"] = (
                    self.env["ir.sequence"].next_by_code("dlm.product") or "/"
                )
            vals.setdefault("type", "product")
        return super().create(vals_list)
