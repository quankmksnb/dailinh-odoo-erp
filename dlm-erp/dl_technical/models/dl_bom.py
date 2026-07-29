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

    @api.onchange("product_id", "bom_type")
    def _onchange_product_version(self):
        if self.product_id:
            self.version = self._compute_next_version()

    # ── Liên kết ngược về màn "Xử lý RFQ" ────────────────────────────────
    # Khi form BOM được mở dạng modal TỪ wizard Xử lý RFQ (context có
    # rfq_resolve_wizard_id), hiện nút "Quay lại Xử lý RFQ" — vì dialog mới
    # THAY THẾ dialog wizard trong stack, đóng modal BOM sẽ rơi về form dòng
    # sản phẩm chứ không về wizard (UX khó chịu).
    show_back_to_rfq = fields.Boolean(compute="_compute_show_back_to_rfq")

    def _compute_show_back_to_rfq(self):
        # Chỉ hiện nút khi form được mở TỪ màn Xử lý RFQ: các entry point từ
        # wizard đều đánh dấu context (rfq_bom_modal — nút bút chì/copy;
        # rfq_resolve_wizard_id — nút Tạo BOM mới/Chỉnh sửa BOM;
        # default_rfq_line_id — action gốc của wizard). Mở BOM từ menu
        # "BOM sản phẩm / BTP" không có cờ nào → luôn ẩn.
        ctx = self.env.context
        from_wizard = bool(
            ctx.get("rfq_bom_modal")
            or ctx.get("rfq_resolve_wizard_id")
            or ctx.get("default_rfq_line_id")
        )
        for rec in self:
            rec.show_back_to_rfq = from_wizard and bool(rec._rfq_wizard())

    def _rfq_wizard(self):
        """Wizard Xử lý RFQ đã mở form BOM này (nếu có).

        3 tầng (context qua nút trên dòng x2many không đáng tin — client không
        chắc truyền đủ):
        1. id truyền thẳng qua context (rfq_resolve_wizard_id);
        2. default_rfq_line_id trong context (action gốc của wizard) → wizard
           mới nhất của dòng RFQ đó;
        3. wizard mới nhất trỏ đúng SẢN PHẨM của BOM này — bảng BOM Version
           trong wizard chỉ chứa BOM của product wizard đang chọn nên tra
           ngược theo product là đúng wizard đang mở. Wizard là bản ghi tạm
           (transient, tự dọn sau ~1h) nên không dính wizard của phiên cũ."""
        self.ensure_one()
        Wizard = self.env["dl.rfq.resolve.wizard"]
        wid = self.env.context.get("rfq_resolve_wizard_id")
        if wid:
            wiz = Wizard.browse(wid)
            if wiz.exists():
                return wiz
        line_id = self.env.context.get("default_rfq_line_id")
        if line_id:
            wiz = Wizard.search(
                [("rfq_line_id", "=", line_id)], order="id desc", limit=1)
            if wiz:
                return wiz
        if self.product_id:
            wiz = Wizard.search(
                [("product_id", "=", self.product_id.id)],
                order="id desc", limit=1)
            if wiz:
                return wiz
        return None

    def action_back_to_rfq_wizard(self):
        """Quay lại đúng màn Xử lý RFQ đang dở (giữ nguyên mọi lựa chọn)."""
        self.ensure_one()
        wiz = self._rfq_wizard()
        if not wiz:
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.act_window",
            "res_model": "dl.rfq.resolve.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_form_modal(self):
        """Mở chính BOM này bằng form dl.bom mặc định dưới dạng modal Ở CHẾ ĐỘ
        SỬA — dùng cho nút bút chì trên bảng BOM Version của màn Nhận RFQ
        (bấm thẳng vào dòng chỉ mở chế độ xem vì bom_ids là computed readonly).
        Giữ nguyên context để form BOM còn biết đường quay lại wizard."""
        self.ensure_one()
        # Cờ "mở từ wizard Xử lý RFQ" — nút này chỉ tồn tại trên bảng BOM
        # Version của wizard nên gắn thẳng tại đây (xem show_back_to_rfq).
        ctx = dict(self.env.context, rfq_bom_modal=True)
        return {
            "type": "ir.actions.act_window",
            "name": _("Chỉnh sửa %s") % self.display_name,
            "res_model": "dl.bom",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_copy_version_modal(self):
        """Copy BOM — nút bên cạnh bút chì trên bảng BOM Version của màn Xử lý
        RFQ: tạo 1 PHIÊN BẢN MỚI (Nháp) giống hệt BOM này (reuse
        action_create_new_version — copy cả dòng vật tư), chọn luôn làm "BOM
        đã chọn" của wizard rồi mở form sửa tiếp. Khác "Tạo BOM từ BOM mẫu":
        nguồn copy là 1 version BOM có sẵn của chính sản phẩm."""
        self.ensure_one()
        result = self.action_create_new_version()
        new_id = result.get("res_id")
        wiz = self._rfq_wizard()
        if wiz:
            wiz.selected_bom_id = new_id
        # Cờ "mở từ wizard Xử lý RFQ" — như action_open_form_modal.
        ctx = dict(self.env.context, rfq_bom_modal=True)
        return {
            "type": "ir.actions.act_window",
            "name": _("Copy BOM — phiên bản mới"),
            "res_model": "dl.bom",
            "res_id": new_id,
            "view_mode": "form",
            "target": "new",
            "context": ctx,
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
