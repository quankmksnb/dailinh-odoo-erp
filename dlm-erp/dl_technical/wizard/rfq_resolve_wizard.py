from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DlRfqResolveWizard(models.TransientModel):
    """Màn 'Nhận RFQ' (Kỹ thuật) — chọn/tạo Product + BOM cho 1 dòng RFQ.

    A. Product đã từng gia công: tìm/chọn product.product có sẵn, xem danh
       sách BOM Version của product đó, chọn hoặc tạo phiên bản mới để sửa
       theo yêu cầu khách (không đụng BOM gốc — action_create_new_version).
    B. Product chưa từng gia công: tạo product mới (chọn Nhóm sản phẩm) rồi
       tạo BOM mới cho nó.
    Xác nhận sẽ ghi resolved_product_id/resolved_bom_id lên dòng RFQ.
    """

    _name = "dl.rfq.resolve.wizard"
    _description = "Xử lý RFQ — chọn/tạo Product và BOM"

    rfq_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ",
        required=True,
        readonly=True,
    )

    # ── Thông tin yêu cầu (chỉ để tham khảo, readonly) ──────────────────────
    request_product_name = fields.Char(
        related="rfq_line_id.product_name", string="Tên sản phẩm (RFQ)", readonly=True)
    request_quantity = fields.Float(
        related="rfq_line_id.quantity", string="Số lượng", readonly=True)
    request_category_id = fields.Many2one(
        related="rfq_line_id.product_category_id", string="Nhóm sản phẩm (RFQ)", readonly=True)
    request_dimension_note = fields.Text(
        related="rfq_line_id.dimension_note", string="Kích thước / Yêu cầu", readonly=True)
    request_reference_product_id = fields.Many2one(
        related="rfq_line_id.reference_product_id", string="Sản phẩm tham khảo (Sales)", readonly=True)
    # Ảnh / file Sales gửi kèm — cho KTV xem ngay trên màn xử lý (readonly).
    request_attachment_ids = fields.Many2many(
        related="rfq_line_id.attachment_ids", string="Ảnh / File Sales gửi", readonly=True)

    # Đánh dấu "không khả thi" ngay trên màn xử lý (thay vì phải ra form dòng).
    is_infeasible = fields.Boolean(string="Không khả thi")
    infeasible_reason = fields.Text(string="Lý do không khả thi")

    # ── A/B ──────────────────────────────────────────────────────────────
    mode = fields.Selection(
        [
            ("existing", "Sản phẩm đã từng gia công"),
            ("new", "Sản phẩm chưa từng gia công"),
        ],
        string="Trường hợp",
        default="existing",
        required=True,
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        domain=[("product_kind", "in", ("manufactured", "material_processed"))],
    )

    # Danh sách SP hợp lệ để CHỌN: lọc theo Nhóm SP của RFQ (KHÔNG lọc theo
    # trạng thái vòng đời — chọn được cả draft lẫn active). Dùng làm domain cho
    # product_id (giống pattern bom_ids→selected_bom_id).
    allowed_product_ids = fields.Many2many(
        "product.product", compute="_compute_allowed_product_ids",
        string="SP hợp lệ")

    @api.depends("request_category_id")
    def _compute_allowed_product_ids(self):
        Product = self.env["product.product"]
        for rec in self:
            domain = [
                ("product_kind", "in", ("manufactured", "material_processed")),
            ]
            if rec.request_category_id:
                domain.append(("categ_id", "child_of", rec.request_category_id.id))
            rec.allowed_product_ids = Product.search(domain)

    new_product_name = fields.Char(string="Tên sản phẩm mới")
    # SP tạo mới từ resolve là manufactured → chỉ nhóm nhánh Thành phẩm.
    new_product_category_id = fields.Many2one(
        "product.category", string="Nhóm sản phẩm",
        domain=[("dl_branch", "=", "finished")])

    bom_ids = fields.Many2many(
        "dl.bom", compute="_compute_bom_ids", string="BOM Version")
    selected_bom_id = fields.Many2one(
        "dl.bom", string="BOM đã chọn", domain="[('id', 'in', bom_ids)]")
    selected_bom_line_ids = fields.One2many(
        related="selected_bom_id.line_ids", string="Chi tiết BOM", readonly=True)

    @api.depends("product_id", "mode")
    def _compute_bom_ids(self):
        Bom = self.env["dl.bom"]
        for rec in self:
            if rec.mode == "existing" and rec.product_id:
                rec.bom_ids = Bom.search(
                    [("product_id", "=", rec.product_id.id)], order="version desc")
            else:
                rec.bom_ids = Bom.browse()

    @api.onchange("product_id", "mode")
    def _onchange_product_id(self):
        # Mặc định chọn sẵn phiên bản BOM hiện hành (is_current) của sản phẩm —
        # KTV vẫn đổi sang version khác được (thiết kế BOM truy xuất §4.3).
        if self.mode == "existing" and self.product_id:
            current = self.env["dl.bom"].search(
                [("product_id", "=", self.product_id.id), ("is_current", "=", True)],
                limit=1,
            )
            self.selected_bom_id = current.id or False
        else:
            self.selected_bom_id = False

    @api.model
    def default_get(self, fields_list):
        """§3c — lấy luôn Tên sản phẩm Sales đã nhập ở RFQ làm tên mặc định khi
        Kỹ thuật tạo sản phẩm mới (khỏi phải gõ lại)."""
        res = super().default_get(fields_list)
        line_id = res.get("rfq_line_id") or self.env.context.get("default_rfq_line_id")
        if line_id and not res.get("new_product_name"):
            line = self.env["dl.quotation.request.line"].browse(line_id)
            if line.exists() and line.product_name:
                res["new_product_name"] = line.product_name
        return res

    def _next_version(self, product, bom_type="quotation"):
        existing = self.env["dl.bom"].search([
            ("product_id", "=", product.id), ("bom_type", "=", bom_type)])
        return (max(existing.mapped("version")) + 1) if existing else 1

    def action_create_product(self):
        """Case B — tạo Product mới (không tạo trùng: dùng chính product_id
        làm kết quả, chuyển sang chế độ 'existing' để chọn/tạo BOM tiếp)."""
        self.ensure_one()
        if not self.new_product_name:
            raise UserError(_("Vui lòng nhập Tên sản phẩm mới."))
        if not self.new_product_category_id:
            raise UserError(_("Vui lòng chọn Nhóm sản phẩm."))
        product = self.env["product.product"].create({
            "name": self.new_product_name,
            "categ_id": self.new_product_category_id.id,
            "product_kind": "manufactured",
            # Case B "hoàn toàn mới": SP nằm ở Nháp cho tới khi đơn chốt/duyệt.
            "dlm_lifecycle_state": "draft",
        })
        self.product_id = product.id
        self.mode = "existing"
        return {
            "type": "ir.actions.act_window",
            "res_model": "dl.rfq.resolve.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_create_bom(self):
        """Tạo BOM mới cho product_id rồi mở NGUYÊN màn Product BOM (form
        dl.bom mặc định) dưới dạng modal — khai báo dòng vật tư / Create From
        BOM Template... bằng đúng UI BOM hiện có."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Vui lòng chọn hoặc tạo Product trước."))
        bom = self.env["dl.bom"].create({
            "product_id": self.product_id.id,
            "version": self._next_version(self.product_id),
            "bom_type": "quotation",
            "status": "draft",
        })
        self.selected_bom_id = bom.id
        return {
            "type": "ir.actions.act_window",
            "name": _("BOM mới"),
            "res_model": "dl.bom",
            "res_id": bom.id,
            "view_mode": "form",
            "target": "new",
            # Form BOM hiện nút "Quay lại Xử lý RFQ" quay đúng wizard này.
            "context": {"rfq_resolve_wizard_id": self.id},
        }

    def action_edit_selected_bom(self):
        """Sửa BOM theo yêu cầu khách — KHÔNG đụng bản gốc: tự tạo phiên bản
        mới (reuse dl.bom.action_create_new_version) rồi mở form để sửa."""
        self.ensure_one()
        if not self.selected_bom_id:
            raise UserError(_("Vui lòng chọn 1 BOM trước khi chỉnh sửa."))
        result = self.selected_bom_id.action_create_new_version()
        self.selected_bom_id = result.get("res_id")
        result["name"] = _("Chỉnh sửa BOM cho RFQ")
        result["target"] = "new"
        # Form BOM hiện nút "Quay lại Xử lý RFQ" quay đúng wizard này.
        result["context"] = {"rfq_resolve_wizard_id": self.id}
        return result

    def action_mark_infeasible(self):
        """Kết luận dòng RFQ là không khả thi — ghi thẳng lên dòng, xóa Product/
        BOM đã chọn (nếu có) và đóng màn."""
        self.ensure_one()
        if not (self.infeasible_reason or "").strip():
            raise UserError(_("Vui lòng nhập lý do không khả thi."))
        self.rfq_line_id.write({
            "is_infeasible": True,
            "infeasible_reason": self.infeasible_reason,
            "resolved_product_id": False,
            "resolved_bom_id": False,
        })
        return {"type": "ir.actions.act_window_close"}

    def action_confirm(self):
        self.ensure_one()
        if self.rfq_line_id.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý qua màn này."))
        if not self.product_id:
            raise UserError(_("Vui lòng chọn hoặc tạo Product trước khi xác nhận."))
        if not self.selected_bom_id:
            raise UserError(_("Vui lòng chọn hoặc tạo BOM trước khi xác nhận."))
        if self.selected_bom_id.product_id != self.product_id:
            raise UserError(_("BOM đã chọn không thuộc Product đã chọn."))

        self.rfq_line_id.write({
            "resolved_product_id": self.product_id.id,
            "resolved_bom_id": self.selected_bom_id.id,
        })
        return {"type": "ir.actions.act_window_close"}
