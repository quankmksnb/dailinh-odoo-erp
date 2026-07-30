import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .rfq_provisional_utils import has_stored_many2one_reference


_logger = logging.getLogger(__name__)


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

    is_rfq_provisional = fields.Boolean(
        string="Dữ liệu tạm từ RFQ",
        default=False,
        copy=False,
        index=True,
        tracking=True,
        help="BOM được tạo/copy trong workspace RFQ nhưng dòng RFQ chưa hoàn tất.",
    )
    rfq_source_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ nguồn",
        ondelete="set null",
        copy=False,
        index=True,
        tracking=True,
    )

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
        # SP trên BOM là manufactured (nhánh Thành phẩm) hoặc BTP (nhánh Vật
        # tư) — filter chỉ hiện nhóm 2 nhánh chuẩn, khỏi lẫn nhóm hệ thống.
        domain=[("dl_branch", "in", ("finished", "material"))],
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
        # Odoo mặc định KHÔNG copy one2many khi duplicate record — bật lên để
        # "Tạo phiên bản mới"/"Copy BOM" (action_create_new_version → copy())
        # mang theo toàn bộ dòng vật tư sang version mới.
        copy=True,
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
    drawing_id = fields.Many2one(
        "dl.drawing",
        string="Bản vẽ kỹ thuật",
        compute="_compute_drawing_ref",
    )
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
            rec.drawing_id = drawing
            rec.drawing_attachment_id = att
            rec.drawing_mimetype = att.mimetype if att else False
            rec.drawing_filename = att.name if att else False

    def action_view_drawing(self):
        """§4a — XEM trực tiếp file bản vẽ (mở PDF/ảnh trong tab mới), không mở
        form thêm bản vẽ. download=false để trình duyệt render xem tại chỗ."""
        self.ensure_one()
        if not self.drawing_attachment_id:
            raise UserError(_("Sản phẩm chưa có bản vẽ kỹ thuật."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=false" % self.drawing_attachment_id.id,
            "target": "new",
        }

    def action_upload_drawing(self):
        """§4b — tải lên bản vẽ ngay từ màn BOM (mở form Bản vẽ trong dialog, tự
        gắn Sản phẩm hiện tại). Dùng chung cho cả màn Tạo BOM & Nhận RFQ."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Vui lòng chọn Sản phẩm trước khi tải bản vẽ."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Tải lên bản vẽ"),
            "res_model": "dl.drawing",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_id": self.product_id.id,
                "default_name": self.product_id.display_name,
            },
        }

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

    def _should_set_current_version(self):
        self.ensure_one()
        return not self.is_rfq_provisional

    def action_lock(self):
        if self.filtered("is_rfq_provisional"):
            raise UserError(_(
                "BOM tạm từ RFQ chưa thể khóa. Hãy quay lại workspace và bấm "
                "'Hoàn tất dòng' trước."))
        return super().action_lock()

    def action_archive(self):
        if self.filtered("is_rfq_provisional"):
            raise UserError(_(
                "Không thể lưu trữ BOM tạm từ RFQ. Hãy hoàn tất hoặc bỏ phương án "
                "trên dòng RFQ nguồn."))
        return super().action_archive()

    def action_create_new_version(self):
        self.ensure_one()
        result = super().action_create_new_version()
        if self.is_rfq_provisional:
            self.browse(result["res_id"]).write({
                "is_rfq_provisional": True,
                "rfq_source_line_id": self.rfq_source_line_id.id,
            })
        return result

    def _cleanup_unused_rfq_provisional(self):
        """Delete unused RFQ BOMs without touching locked/current/history data."""
        deleted = 0
        ignored = {("dl.bom.line", "bom_id")}
        for bom in self.sudo().exists():
            if (not bom.is_rfq_provisional
                    or bom.status not in ("draft", "confirmed")
                    or bom.is_current):
                continue
            if has_stored_many2one_reference(bom, ignored=ignored):
                continue
            try:
                with self.env.cr.savepoint():
                    bom.unlink()
                deleted += 1
            except Exception:
                _logger.exception(
                    "Không thể dọn BOM tạm RFQ %s; giữ lại để an toàn.", bom.id)
        return deleted

    @api.onchange("product_id", "bom_type")
    def _onchange_product_version(self):
        if self.product_id:
            self.version = self._compute_next_version()

    def action_open_form(self):
        """Mở BOM trên trang đầy đủ.

        Khi gọi từ workspace RFQ, web client tự giữ workspace trong breadcrumb;
        không cần context dò ngược hay nút quay lại riêng trên form BOM.
        """
        self.ensure_one()
        view = self.env.ref("dl_technical.view_dl_bom_form")
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "dl.bom",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }

    def action_create_from_template(self):
        """Product BOM — nút "Create From BOM Template": mở wizard chọn 1
        BOM mẫu (dl.bom.template) rồi copy toàn bộ dòng sang BOM này."""
        self.ensure_one()
        if self.status != "draft":
            raise UserError(_("Chỉ BOM ở trạng thái Nháp mới copy được từ BOM mẫu."))
        category = self.product_id.categ_id
        if not category:
            raise UserError(_(
                'Sản phẩm "%s" chưa được gán Nhóm sản phẩm — hãy gán nhóm cho '
                'sản phẩm trước khi tạo BOM từ BOM mẫu.'
            ) % self.product_id.display_name)
        has_template = self.env["dl.bom.template"].search(
            [
                ("product_category_id", "=", category.id),
                ("status", "!=", "archived"),
            ],
            limit=1,
        )
        if not has_template:
            raise UserError(_(
                'Nhóm sản phẩm "%s" chưa có BOM mẫu nào. Hãy tạo BOM mẫu cho '
                'nhóm này trước (menu BOM mẫu), hoặc nhập dòng vật tư trực tiếp '
                'vào BOM.'
            ) % category.display_name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Tạo từ BOM mẫu"),
            "res_model": "dl.bom.from.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bom_id": self.id},
        }

    def action_create_bom_template(self):
        """Chiều ngược của "Create From BOM Template": lấy chính BOM này làm
        BOM mẫu cho NHÓM sản phẩm mà sản phẩm của BOM đang thuộc về. Điều kiện:
        sản phẩm đã được gán 1 nhóm sản phẩm (categ_id). Copy toàn bộ dòng vật
        tư sang 1 BOM mẫu mới (nháp) để Kỹ thuật rà soát/điều chỉnh."""
        self.ensure_one()
        if self.is_rfq_provisional:
            raise UserError(_(
                "BOM này vẫn là dữ liệu tạm của RFQ. Hãy hoàn tất dòng RFQ trước "
                "khi dùng nó để tạo BOM mẫu."))
        category = self.product_id.categ_id
        if not category:
            raise UserError(_(
                'Sản phẩm "%s" chưa được gán Nhóm sản phẩm — hãy gán nhóm cho '
                'sản phẩm trước khi lấy BOM này làm BOM mẫu cho nhóm.'
            ) % self.product_id.display_name)
        if not self.line_ids:
            raise UserError(_("BOM này chưa có dòng vật tư nào để tạo BOM mẫu."))

        Template = self.env["dl.bom.template"]
        existing = Template.search([("product_category_id", "=", category.id)])
        version = (max(existing.mapped("version")) + 1) if existing else 1

        template = Template.create({
            "name": _("BOM mẫu - %s (từ %s)") % (category.name, self.name),
            "product_category_id": category.id,
            "product_qty": self.product_qty,
            "version": version,
            "status": "draft",
            "line_ids": [(0, 0, line._mixin_copy_vals()) for line in self.line_ids],
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("BOM mẫu"),
            "res_model": "dl.bom.template",
            "res_id": template.id,
            "view_mode": "form",
            "target": "current",
        }
