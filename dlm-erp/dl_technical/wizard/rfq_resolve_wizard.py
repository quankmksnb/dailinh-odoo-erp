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
    _rec_name = "request_product_name"

    rfq_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ",
        required=True,
        readonly=True,
    )

    step = fields.Selection(
        [
            ("product", "1. Xác định sản phẩm"),
            ("bom", "2. Định mức BOM"),
            ("confirm", "3. Xác nhận"),
        ],
        string="Công đoạn",
        default="product",
        required=True,
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
        # Mặc định chọn sẵn phiên bản BOM có version CAO NHẤT đang ở trạng thái
        # Đã xác nhận/Đã khóa của sản phẩm (không dựa vào cờ is_current — cờ này
        # theo "confirm sau cùng thắng" nên có thể trỏ về bản version thấp hơn).
        # KTV vẫn đổi sang version khác được (thiết kế BOM truy xuất §4.3).
        # Khi mở lại dòng đã xử lý, giữ đúng BOM đã gắn thay vì tự đổi sang
        # version mới nhất; khi đổi sang Product khác, BOM cũ tự bị thay.
        if self.mode == "existing" and self.product_id:
            if (self.selected_bom_id
                    and self.selected_bom_id.product_id == self.product_id):
                return
            current = self.env["dl.bom"].search(
                [
                    ("product_id", "=", self.product_id.id),
                    ("status", "in", ("confirmed", "locked")),
                ],
                order="version desc",
                limit=1,
            )
            self.selected_bom_id = current.id or False
        else:
            self.selected_bom_id = False

    @api.model
    def default_get(self, fields_list):
        """Nạp kết quả hiện tại để wizard là cửa duy nhất cho cả xử lý mới và
        sửa kết luận đã có; đồng thời lấy tên Sales nhập làm tên SP mới mặc định."""
        res = super().default_get(fields_list)
        line_id = res.get("rfq_line_id") or self.env.context.get("default_rfq_line_id")
        if line_id:
            line = self.env["dl.quotation.request.line"].browse(line_id)
            if line.exists():
                if line.product_name and not res.get("new_product_name"):
                    res["new_product_name"] = line.product_name
                if line.is_infeasible:
                    res.update({
                        "is_infeasible": True,
                        "infeasible_reason": line.infeasible_reason,
                    })
                else:
                    if line.resolved_product_id:
                        res.update({
                            "mode": "existing",
                            "product_id": line.resolved_product_id.id,
                        })
                    if line.resolved_bom_id:
                        res["selected_bom_id"] = line.resolved_bom_id.id
                    if line.resolved_product_id and line.resolved_bom_id:
                        res["step"] = "confirm"
        return res

    def _action_reload(self):
        """Nạp lại controller hiện tại mà không tải lại toàn bộ trang.

        ``soft_reload`` giữ nguyên action stack nên breadcrumb Workspace RFQ ↔ BOM
        vẫn quay lại được; client action ``reload`` sẽ tải lại browser và làm mất
        stack này.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }

    def _action_return_to_rfq(self):
        """Kết thúc workspace và trở về đúng RFQ nguồn."""
        self.ensure_one()
        request = self.rfq_line_id.quotation_request_id
        view = self.env.ref("dl_technical.view_dl_quotation_request_form")
        return {
            "type": "ir.actions.act_window",
            "name": request.display_name,
            "res_model": "dl.quotation.request",
            "res_id": request.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }

    def _validate_product_step(self):
        self.ensure_one()
        if not self.product_id:
            if self.mode == "new":
                raise UserError(_(
                    "Vui lòng tạo sản phẩm mới trước khi sang bước Định mức BOM."))
            raise UserError(_(
                "Vui lòng chọn sản phẩm trước khi sang bước Định mức BOM."))

    def _validate_bom_step(self):
        self.ensure_one()
        if not self.selected_bom_id:
            raise UserError(_(
                "Vui lòng chọn hoặc tạo BOM trước khi sang bước Xác nhận."))
        if self.selected_bom_id.product_id != self.product_id:
            raise UserError(_("Định mức đã chọn không thuộc sản phẩm đã chọn."))
        if self.selected_bom_id.status not in ("confirmed", "locked"):
            raise UserError(_(
                "BOM phải ở trạng thái Đã xác nhận hoặc Đã khóa trước khi tiếp tục."))

    def action_next_step(self):
        self.ensure_one()
        if self.is_infeasible:
            raise UserError(_(
                "Hãy xác nhận Không khả thi hoặc bỏ lựa chọn này để tiếp tục."))
        if self.step == "product":
            self._validate_product_step()
            self.step = "bom"
        elif self.step == "bom":
            self._validate_product_step()
            self._validate_bom_step()
            self.step = "confirm"
        return self._action_reload()

    def action_previous_step(self):
        self.ensure_one()
        if self.step == "confirm":
            self.step = "bom"
        elif self.step == "bom":
            self.step = "product"
        return self._action_reload()

    def action_cancel(self):
        return self._action_return_to_rfq()

    def _next_version(self, product, bom_type="quotation"):
        existing = self.env["dl.bom"].search([
            ("product_id", "=", product.id), ("bom_type", "=", bom_type)])
        return (max(existing.mapped("version")) + 1) if existing else 1

    def _action_open_bom(self, bom, name=None):
        """Đẩy form BOM lên breadcrumb, giữ workspace hiện tại ở phía sau."""
        self.ensure_one()
        view = self.env.ref("dl_technical.view_dl_bom_form")
        return {
            "type": "ir.actions.act_window",
            "name": name or bom.display_name,
            "res_model": "dl.bom",
            "res_id": bom.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }

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
        return self._action_reload()

    def action_create_bom(self):
        """Tạo BOM nháp rồi mở form BOM full-page trên breadcrumb workspace."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Vui lòng chọn hoặc tạo sản phẩm trước."))
        bom = self.env["dl.bom"].create({
            "product_id": self.product_id.id,
            "version": self._next_version(self.product_id),
            "bom_type": "quotation",
            "status": "draft",
        })
        self.selected_bom_id = bom.id
        return self._action_open_bom(bom, _("BOM mới"))

    def action_edit_selected_bom(self):
        """Mở BOM nháp để sửa; BOM đã duyệt thì sao chép thành version nháp.

        Không tạo thêm version nếu người dùng đang chỉnh chính một BOM nháp.
        """
        self.ensure_one()
        if not self.selected_bom_id:
            raise UserError(_("Vui lòng chọn 1 BOM trước khi chỉnh sửa."))
        bom = self.selected_bom_id
        if bom.status != "draft":
            result = bom.action_create_new_version()
            bom = self.env["dl.bom"].browse(result["res_id"])
            self.selected_bom_id = bom.id
        return self._action_open_bom(bom, _("Chỉnh sửa BOM cho RFQ"))

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
        return self._action_return_to_rfq()

    def action_confirm(self):
        self.ensure_one()
        if self.rfq_line_id.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý qua màn này."))
        self._validate_product_step()
        self._validate_bom_step()

        self.rfq_line_id.write({
            "resolved_product_id": self.product_id.id,
            "resolved_bom_id": self.selected_bom_id.id,
            # Cho phép sửa một kết luận "Không khả thi" thành phương án khả thi
            # ngay trong cùng cửa xử lý, không cần mở field kết quả trực tiếp.
            "is_infeasible": False,
            "infeasible_reason": False,
        })
        return self._action_return_to_rfq()
