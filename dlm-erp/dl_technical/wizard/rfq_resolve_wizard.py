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
        # BẮT BUỘC khai cascade: Many2one `required` mà không khai ondelete thì
        # Odoo mặc định 'restrict' ⇒ Sales loại dòng khỏi phạm vi trong lúc Kỹ
        # thuật đang mở workspace sẽ vỡ khoá ngoại ở DB (EX-20). Hai wizard kết
        # luận nhanh đã khai cascade; workspace bị sót.
        ondelete="cascade",
    )

    # ── Trục tiến độ (display-only) ──────────────────────────────────────────
    # KHÔNG còn là cổng chặn tuần tự (bỏ action_next_step/previous_step). Chỉ là
    # khung tiến độ suy TỪ dữ liệu: chọn xong sản phẩm/định mức thì stepper tự
    # tiến. Thiết kế §5/§9.4 "một màn, ba khối, tự thu gọn".
    step = fields.Selection(
        [
            ("product", "1. Xác định sản phẩm"),
            ("bom", "2. Định mức BOM"),
            ("confirm", "3. Xác nhận"),
        ],
        string="Công đoạn",
        compute="_compute_step",
    )

    # Trạng thái điều khiển accordion / lối thoát trên MỘT màn. Không lưu lâu
    # dài — chỉ là trạng thái trình bày của phiên xử lý hiện tại.
    show_bom_picker = fields.Boolean(
        string="Đang mở danh sách chọn định mức",
        help="Bật khi KTV bấm 'Chọn bản khác' để lộ lại bảng phiên bản định mức.")
    active_exit = fields.Selection(
        [
            ("supplement", "Cần bổ sung"),
            ("infeasible", "Không khả thi"),
        ],
        string="Lối thoát đang mở")

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

    supplement_note = fields.Text(string="Nội dung cần bổ sung")
    has_existing_supplement = fields.Boolean(
        string="Dòng đã có yêu cầu bổ sung từ trước")

    # Dòng gia công CHƯA xử lý kế tiếp trong cùng RFQ (bỏ qua dòng đang chờ
    # Sales bổ sung — không có việc để làm) — cho nút "Hoàn tất & dòng tiếp theo".
    next_line_id = fields.Many2one(
        "dl.quotation.request.line", string="Dòng chưa xử lý kế tiếp",
        compute="_compute_next_line_id")

    @api.depends("rfq_line_id",
                 "rfq_line_id.quotation_request_id.line_ids.resolved_product_id",
                 "rfq_line_id.quotation_request_id.line_ids.resolved_bom_id",
                 "rfq_line_id.quotation_request_id.line_ids.is_infeasible",
                 "rfq_line_id.quotation_request_id.line_ids.supplement_note")
    def _compute_next_line_id(self):
        for rec in self:
            nxt = self.env["dl.quotation.request.line"]
            if rec.rfq_line_id:
                nxt = rec.rfq_line_id.quotation_request_id.line_ids.filtered(
                    lambda l: l.id != rec.rfq_line_id.id
                    and l.product_type == "manufactured"
                    and not l.supplement_note
                    and not l._is_resolved())[:1]
            rec.next_line_id = nxt

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
    product_is_rfq_provisional = fields.Boolean(
        related="product_id.is_rfq_provisional",
        string="Sản phẩm đang tạm từ RFQ",
        readonly=True,
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
            if rec.rfq_line_id:
                domain.extend([
                    "|",
                    ("is_rfq_provisional", "=", False),
                    ("rfq_source_line_id", "=", rec.rfq_line_id.id),
                ])
            else:
                domain.append(("is_rfq_provisional", "=", False))
            rec.allowed_product_ids = Product.search(domain)

    new_product_name = fields.Char(string="Tên sản phẩm mới")
    # SP tạo mới từ resolve là manufactured → chỉ nhóm nhánh Thành phẩm.
    new_product_category_id = fields.Many2one(
        "product.category", string="Nhóm sản phẩm",
        domain=[("dl_branch", "=", "finished")])

    # ── Soi trùng/gần giống tên khi tạo SP mới (Case B) ───────────────────
    # exact → chặn cứng (chọn lại SP có sẵn); similar → cảnh báo mềm, KTV tick
    # xác nhận mới tạo được. Soi trên toàn bộ SP gia công/BTP chính thức.
    name_dup_state = fields.Selection(
        [("none", "Không trùng"), ("exact", "Trùng hệt"), ("similar", "Gần giống")],
        string="Kết quả soi trùng tên", compute="_compute_name_dup")
    name_dup_message = fields.Char(
        string="Cảnh báo trùng tên", compute="_compute_name_dup")
    name_dup_exact_id = fields.Many2one(
        "product.product", string="SP trùng hệt", compute="_compute_name_dup")
    name_dup_similar_ids = fields.Many2many(
        "product.product", string="SP gần giống", compute="_compute_name_dup")
    confirm_similar_name = fields.Boolean(
        string="Xác nhận đây thực sự là sản phẩm khác")

    @api.depends("new_product_name", "mode")
    def _compute_name_dup(self):
        Product = self.env["product.product"]
        for rec in self:
            rec.name_dup_state = "none"
            rec.name_dup_message = False
            rec.name_dup_exact_id = False
            rec.name_dup_similar_ids = Product.browse()
            if rec.mode != "new" or not rec.new_product_name:
                continue
            matches = Product._dlm_find_name_matches(
                rec.new_product_name,
                kinds=("manufactured", "material_processed"),
                extra_domain=[("is_rfq_provisional", "=", False)],
            )
            if matches["exact"]:
                dup = matches["exact"][0]
                rec.name_dup_state = "exact"
                rec.name_dup_exact_id = dup.id
                rec.name_dup_message = _(
                    "Đã có sản phẩm “%(name)s” (nhóm %(categ)s). Không tạo trùng "
                    "— hãy chọn lại sản phẩm này.",
                    name=dup.display_name,
                    categ=dup.categ_id.display_name or _("chưa phân nhóm"))
            elif matches["similar"]:
                rec.name_dup_state = "similar"
                rec.name_dup_similar_ids = matches["similar"]
                names = ", ".join(matches["similar"][:5].mapped("display_name"))
                rec.name_dup_message = _(
                    "Có sản phẩm gần giống: %s. Nếu đây thực sự là sản phẩm "
                    "khác, tick xác nhận bên dưới rồi bấm Tạo sản phẩm.") % names

    bom_ids = fields.Many2many(
        "dl.bom", compute="_compute_bom_ids", string="BOM Version")
    # Lựa chọn BOM do KTV chỉ định (nếu có). Lưu riêng khỏi selected_bom_id để
    # selected_bom_id là field TÍNH (không lưu) — tính lại mỗi lần nạp form nên
    # tự bắt được BOM vừa được Xác nhận khi KTV mở BOM ra duyệt rồi quay lại
    # workspace (trước đây phải chọn lại sản phẩm mới auto-lấy được BOM đã duyệt).
    manual_bom_id = fields.Many2one("dl.bom")
    selected_bom_id = fields.Many2one(
        "dl.bom", string="BOM đã chọn", domain="[('id', 'in', bom_ids)]",
        compute="_compute_selected_bom_id",
        inverse="_inverse_selected_bom_id",
        store=False, readonly=False)
    selected_bom_is_rfq_provisional = fields.Boolean(
        related="selected_bom_id.is_rfq_provisional",
        string="BOM đang tạm từ RFQ",
        readonly=True,
    )
    selected_bom_line_ids = fields.One2many(
        related="selected_bom_id.line_ids", string="Chi tiết BOM", readonly=True)

    # ── Tóm tắt định mức để hiện ở khối ⑵ thu gọn + decision dock ────────────
    selected_bom_label = fields.Char(
        string="Nhãn định mức", compute="_compute_bom_summary")
    selected_bom_line_count = fields.Integer(
        string="Số dòng vật tư", compute="_compute_bom_summary")
    selected_bom_has_lines = fields.Boolean(
        string="Định mức có dòng vật tư", compute="_compute_bom_summary")
    selected_bom_confirmed = fields.Boolean(
        string="Định mức đã xác nhận", compute="_compute_bom_summary")

    @api.depends("selected_bom_id", "selected_bom_id.status",
                 "selected_bom_id.bom_type", "selected_bom_id.version",
                 "selected_bom_id.line_ids")
    def _compute_bom_summary(self):
        status_lbl = dict(
            self.env["dl.bom"]._fields["status"]._description_selection(self.env))
        for rec in self:
            bom = rec.selected_bom_id
            rec.selected_bom_line_count = len(bom.line_ids)
            rec.selected_bom_has_lines = bool(bom.line_ids)
            rec.selected_bom_confirmed = bom.status in ("confirmed", "locked")
            if not bom:
                rec.selected_bom_label = False
                continue
            # BOM báo giá = INSTANCE của một đơn → KHÔNG gọi là "Phiên bản" (DoD
            # §7.4c #8). Dùng "Lần sinh #" cho báo giá, "Phiên bản" cho BOM mẫu.
            if bom.bom_type == "quotation":
                rec.selected_bom_label = _("Định mức đơn #%(n)s — %(st)s") % {
                    "n": bom.version, "st": status_lbl.get(bom.status, bom.status)}
            else:
                rec.selected_bom_label = _("BOM mẫu v%(n)s — %(st)s") % {
                    "n": bom.version, "st": status_lbl.get(bom.status, bom.status)}

    # ── Checklist ⑶ (tự tick) + điều kiện Hoàn tất (decision dock) ───────────
    check_product = fields.Boolean(compute="_compute_checklist")
    check_bom_selected = fields.Boolean(compute="_compute_checklist")
    check_bom_belongs = fields.Boolean(compute="_compute_checklist")
    check_bom_has_lines = fields.Boolean(compute="_compute_checklist")
    check_bom_confirmed = fields.Boolean(compute="_compute_checklist")
    check_request_unchanged = fields.Boolean(compute="_compute_checklist")
    checklist_done = fields.Integer(compute="_compute_checklist")
    checklist_total = fields.Integer(compute="_compute_checklist")
    can_confirm = fields.Boolean(
        string="Đủ điều kiện hoàn tất", compute="_compute_checklist")
    confirm_blocker = fields.Char(
        string="Còn thiếu", compute="_compute_checklist")

    @api.depends("product_id", "selected_bom_id", "selected_bom_has_lines",
                 "selected_bom_confirmed", "is_infeasible", "active_exit",
                 "rfq_line_id.needs_review")
    def _compute_checklist(self):
        for rec in self:
            has_product = bool(rec.product_id)
            has_bom = bool(rec.selected_bom_id)
            belongs = has_bom and rec.selected_bom_id.product_id == rec.product_id
            has_lines = rec.selected_bom_has_lines
            confirmed = rec.selected_bom_confirmed
            unchanged = not rec.rfq_line_id.needs_review

            rec.check_product = has_product
            rec.check_bom_selected = has_bom
            rec.check_bom_belongs = bool(belongs)
            rec.check_bom_has_lines = has_lines
            rec.check_bom_confirmed = confirmed
            rec.check_request_unchanged = unchanged

            # 4 mục checklist §9.4 (xác nhận định mức tính riêng vì Hoàn tất tự
            # xác nhận — xem §19.7).
            done = sum([has_product, bool(belongs), confirmed, unchanged])
            rec.checklist_done = done
            rec.checklist_total = 4

            # Đủ điều kiện Hoàn tất: KHÔNG đòi BOM đã xác nhận (Hoàn tất sẽ tự
            # xác nhận, §19.7) nhưng ĐÒI có dòng vật tư (nếu rỗng, action_confirm
            # sẽ raise — chặn trước ở đây để nút disable thay vì nổ modal).
            blockers = []
            if not has_product:
                blockers.append(_("chưa xác định sản phẩm"))
            if not has_bom:
                blockers.append(_("chưa có định mức"))
            elif not belongs:
                blockers.append(_("định mức không thuộc sản phẩm đã chọn"))
            elif not has_lines:
                blockers.append(_("định mức chưa có dòng vật tư"))
            if rec.is_infeasible or rec.active_exit == "infeasible":
                blockers.append(_("đang ở nhánh Không khả thi"))
            rec.can_confirm = not blockers
            rec.confirm_blocker = (
                _("Còn thiếu: %s") % ", ".join(blockers)) if blockers else False

    @api.depends("product_id", "check_bom_belongs", "check_bom_has_lines")
    def _compute_step(self):
        # Trục tiến độ suy từ dữ liệu (không phải cổng chặn): chưa có sản phẩm →
        # ⑴; có sản phẩm nhưng định mức chưa sẵn sàng → ⑵; đủ → ⑶.
        for rec in self:
            if not rec.product_id:
                rec.step = "product"
            elif not (rec.check_bom_belongs and rec.check_bom_has_lines):
                rec.step = "bom"
            else:
                rec.step = "confirm"

    @api.depends("product_id", "mode")
    def _compute_bom_ids(self):
        Bom = self.env["dl.bom"]
        for rec in self:
            if rec.mode == "existing" and rec.product_id:
                domain = [("product_id", "=", rec.product_id.id)]
                if rec.rfq_line_id:
                    domain.extend([
                        "|",
                        ("is_rfq_provisional", "=", False),
                        ("rfq_source_line_id", "=", rec.rfq_line_id.id),
                    ])
                else:
                    domain.append(("is_rfq_provisional", "=", False))
                rec.bom_ids = Bom.search(domain, order="version desc")
            else:
                rec.bom_ids = Bom.browse()

    @api.depends("bom_ids", "manual_bom_id", "mode", "product_id")
    def _compute_selected_bom_id(self):
        # selected_bom_id KHÔNG lưu → được tính lại mỗi lần đọc/nạp lại form.
        # Nhờ vậy khi KTV mở 1 BOM Nháp ra Xác nhận rồi quay lại workspace, giá
        # trị được tính lại và tự bắt đúng BOM vừa duyệt (không phải chọn lại
        # sản phẩm mới lấy được — đây là lỗi trước đây do onchange chỉ chạy khi
        # đổi product_id, còn quay lại workspace là reload phía client).
        for rec in self:
            if rec.mode != "existing" or not rec.product_id:
                rec.selected_bom_id = False
                continue
            # Ưu tiên giữ đúng BOM KTV đã chỉ định (nếu còn hợp lệ với SP hiện tại).
            if rec.manual_bom_id and rec.manual_bom_id in rec.bom_ids:
                rec.selected_bom_id = rec.manual_bom_id
                continue
            # Mặc định: BOM version CAO NHẤT đang Đã xác nhận/Đã khóa của SP
            # (không dựa vào cờ is_current — cờ theo "confirm sau cùng thắng" nên
            # có thể trỏ về version thấp hơn). KTV vẫn đổi version khác được.
            confirmed = rec.bom_ids.filtered(
                lambda b: b.status in ("confirmed", "locked")).sorted(
                    key=lambda b: b.version, reverse=True)
            rec.selected_bom_id = confirmed[:1]

    def _inverse_selected_bom_id(self):
        # KTV chọn tay 1 BOM → lưu vào manual_bom_id để giữ qua các lần nạp lại
        # form (kể cả BOM Nháp đang chỉnh dở).
        for rec in self:
            rec.manual_bom_id = rec.selected_bom_id

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
                if line.supplement_note:
                    res["supplement_note"] = line.supplement_note
                    res["has_existing_supplement"] = True
                if line.is_infeasible:
                    # Mở lại dòng đã kết luận không khả thi → vào thẳng nhánh
                    # lối thoát tương ứng ở decision dock.
                    res.update({
                        "is_infeasible": True,
                        "infeasible_reason": line.infeasible_reason,
                        "active_exit": "infeasible",
                    })
                else:
                    if line.resolved_product_id:
                        res.update({
                            "mode": "existing",
                            "product_id": line.resolved_product_id.id,
                        })
                    if line.resolved_bom_id:
                        res["manual_bom_id"] = line.resolved_bom_id.id
                    if not line.resolved_product_id:
                        provisional_bom = self.env["dl.bom"].sudo().search([
                            ("is_rfq_provisional", "=", True),
                            ("rfq_source_line_id", "=", line.id),
                        ], order="write_date desc, id desc", limit=1)
                        provisional_product = provisional_bom.product_id
                        if not provisional_product:
                            provisional_product = self.env["product.product"].sudo().search([
                                ("is_rfq_provisional", "=", True),
                                ("rfq_source_line_id", "=", line.id),
                            ], order="write_date desc, id desc", limit=1)
                        if provisional_product:
                            res.update({
                                "mode": "existing",
                                "product_id": provisional_product.id,
                            })
                        if provisional_bom:
                            res["manual_bom_id"] = provisional_bom.id
                    # Mở lại dòng đang chờ bổ sung (chưa xác định SP) → hiện sẵn
                    # nhánh bổ sung ở dock để KTV thấy/sửa nội dung đã yêu cầu.
                    if (line.supplement_note and not line.resolved_product_id
                            and not line.is_infeasible):
                        res["active_exit"] = "supplement"
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
                "Vui lòng chọn hoặc tạo định mức trước khi hoàn tất dòng."))
        if self.selected_bom_id.product_id != self.product_id:
            raise UserError(_("Định mức đã chọn không thuộc sản phẩm đã chọn."))
        # KHÔNG còn đòi BOM đã xác nhận ở đây: Hoàn tất dòng sẽ tự xác nhận định
        # mức Nháp (§19.7 — "một ý định = một cú bấm"). action_confirm của BOM
        # vẫn chặn định mức rỗng, nên rỗng bị chặn ở tầng server thật.

    # ── Điều khiển accordion / lối thoát trên MỘT màn ────────────────────────
    def action_change_product(self):
        """Khối ⑴ đang thu gọn → bấm 'Đổi sản phẩm' để mở lại: xoá lựa chọn hiện
        tại (cả BOM đã chọn tay) để KTV chọn/tạo sản phẩm khác."""
        self.ensure_one()
        self.write({
            "product_id": False,
            "manual_bom_id": False,
            "show_bom_picker": False,
        })
        return self._action_reload()

    def action_toggle_bom_picker(self):
        """Khối ⑵: bấm 'Chọn bản khác' để lộ lại bảng phiên bản định mức (khi đã
        có một định mức được tự chọn/thu gọn)."""
        self.ensure_one()
        self.show_bom_picker = not self.show_bom_picker
        return self._action_reload()

    def action_confirm_bom(self):
        """Nút [Xác nhận định mức] ngay trong checklist ⑶ — dành cho ai muốn chốt
        định mức trước rồi mới Hoàn tất (vd bàn giao cho người khác). Hoàn tất
        dòng vẫn tự xác nhận nếu bỏ qua bước này (§19.7)."""
        self.ensure_one()
        if not self.selected_bom_id:
            raise UserError(_("Chưa có định mức để xác nhận."))
        if self.selected_bom_id.status == "draft":
            self.selected_bom_id.action_confirm()
        return self._action_reload()

    def action_show_supplement(self):
        self.ensure_one()
        self.write({"active_exit": "supplement", "is_infeasible": False})
        return self._action_reload()

    def action_show_infeasible(self):
        self.ensure_one()
        self.write({"active_exit": "infeasible", "is_infeasible": True})
        return self._action_reload()

    def action_hide_exit(self):
        """Quay lại phương án kỹ thuật (đóng nhánh lối thoát đang mở)."""
        self.ensure_one()
        self.write({"active_exit": False, "is_infeasible": False})
        return self._action_reload()

    def action_cancel(self):
        # Giữ bản tạm để KTV có thể mở lại đúng dòng và tiếp tục. Cron sẽ chỉ
        # dọn bản không dùng sau khoảng an toàn cấu hình.
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
        # Soi trùng LẠI ngay lúc bấm (không tin state đã compute) — chặn tạo SP
        # trùng hệt, và đòi xác nhận nếu chỉ gần giống.
        matches = self.env["product.product"]._dlm_find_name_matches(
            self.new_product_name,
            kinds=("manufactured", "material_processed"),
            extra_domain=[("is_rfq_provisional", "=", False)],
        )
        if matches["exact"]:
            dup = matches["exact"][0]
            raise UserError(_(
                "Đã tồn tại sản phẩm “%(name)s” (nhóm %(categ)s). Không tạo "
                "trùng — chuyển sang “Sản phẩm đã từng gia công” và chọn lại "
                "sản phẩm này (nút “Dùng sản phẩm này”).",
                name=dup.display_name,
                categ=dup.categ_id.display_name or _("chưa phân nhóm")))
        if matches["similar"] and not self.confirm_similar_name:
            names = ", ".join(matches["similar"][:5].mapped("display_name"))
            raise UserError(_(
                "Có sản phẩm gần giống: %s.\nNếu đây thực sự là sản phẩm khác, "
                "hãy tick “Xác nhận đây thực sự là sản phẩm khác” rồi tạo lại.")
                % names)
        self.rfq_line_id._cleanup_rfq_provisional_records()
        product = self.env["product.product"].create({
            "name": self.new_product_name,
            "categ_id": self.new_product_category_id.id,
            "product_kind": "manufactured",
            # Case B "hoàn toàn mới": SP nằm ở Nháp cho tới khi đơn chốt/duyệt.
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
            "rfq_source_line_id": self.rfq_line_id.id,
        })
        self.product_id = product.id
        self.mode = "existing"
        return self._action_reload()

    def action_use_duplicate_product(self):
        """Từ cảnh báo trùng hệt: chọn lại SP có sẵn thay vì tạo bản trùng."""
        self.ensure_one()
        if not self.name_dup_exact_id:
            raise UserError(_("Không xác định được sản phẩm trùng để chọn lại."))
        self.write({
            "mode": "existing",
            "product_id": self.name_dup_exact_id.id,
            "new_product_name": False,
            "confirm_similar_name": False,
        })
        return self._action_reload()

    def action_create_bom(self):
        """Tạo BOM nháp rồi mở form BOM full-page trên breadcrumb workspace."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Vui lòng chọn hoặc tạo sản phẩm trước."))
        self.rfq_line_id._cleanup_rfq_provisional_records(
            keep_product_ids=self.product_id.ids)
        bom = self.env["dl.bom"].create({
            "product_id": self.product_id.id,
            "version": self._next_version(self.product_id),
            "bom_type": "quotation",
            "status": "draft",
            "is_rfq_provisional": True,
            "rfq_source_line_id": self.rfq_line_id.id,
        })
        self.manual_bom_id = bom.id
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
            # KHÔNG dùng action_create_new_version(): copy() kế thừa `bom_type`,
            # nên chỉnh một BOM MẪU cho một đơn lại đẻ ra thêm một BOM MẪU —
            # định mức của một đơn bị xếp vào dòng dõi ĐỊNH MỨC CHUẨN của sản
            # phẩm (chiếm số phiên bản, hiện nhãn "BOM mẫu", và có thể bị lấy
            # làm giá vốn chuẩn khi sản phẩm là bán thành phẩm — xem
            # quotation_pricing_service._resolve_child_bom).
            #
            # Bản chỉnh cho một đơn LUÔN là BOM báo giá (instance), và nhận số
            # sê-ri trong dòng dõi báo giá của sản phẩm — tính TRƯỚC khi copy để
            # không đụng unique(product_id, version, bom_type).
            bom = bom.copy({
                "bom_type": "quotation",
                "version": self._next_version(bom.product_id),
                "status": "draft",
                "is_rfq_provisional": True,
                "rfq_source_line_id": self.rfq_line_id.id,
            })
            self.manual_bom_id = bom.id
            self.rfq_line_id._cleanup_rfq_provisional_records(
                keep_product_ids=self.product_id.ids,
                keep_bom_ids=bom.ids,
            )
        return self._action_open_bom(bom, _("Chỉnh sửa BOM cho RFQ"))

    def action_mark_infeasible(self):
        """Kết luận dòng RFQ là không khả thi — ghi thẳng lên dòng (kèm notify
        Sales, logic chung ở line._mark_infeasible) và đóng màn."""
        self.ensure_one()
        self.rfq_line_id._mark_infeasible(self.infeasible_reason)
        return self._action_return_to_rfq()

    def action_mark_supplement(self):
        """KTV đánh dấu dòng cần Sales bổ sung thông tin (kèm chatter +
        activity cho người tạo RFQ, logic chung ở line._mark_supplement)."""
        self.ensure_one()
        self.rfq_line_id._mark_supplement(self.supplement_note)
        return self._action_return_to_rfq()

    def _check_still_processable(self):
        """Kiểm tra LẠI ngay trước khi ghi kết quả (thiết kế RES-002/RES-003).

        Workspace là màn full-page mở lâu: giữa lúc KTV mở và lúc bấm Hoàn tất,
        Sales có thể đã hủy RFQ, đã đánh dấu đã tạo báo giá, hoặc đã loại dòng
        khỏi phạm vi. Kiểm ở lúc MỞ là chưa đủ — nếu không kiểm lại thì kết quả
        được ghi vào một dòng/RFQ đã đóng và không ai biết.
        """
        self.ensure_one()
        line = self.rfq_line_id
        if not line.exists():
            raise UserError(_(
                "Dòng RFQ này đã bị loại khỏi yêu cầu báo giá trong lúc bạn xử "
                "lý. Hãy quay lại RFQ để xem phạm vi hiện tại."))
        request = line.quotation_request_id
        if request.status == "cancelled":
            raise UserError(_(
                "Yêu cầu báo giá %s đã bị hủy trong lúc bạn xử lý — không thể "
                "ghi kết quả kỹ thuật.") % request.name)
        if request.status == "quoted":
            raise UserError(_(
                "Yêu cầu báo giá %s đã được tạo báo giá trong lúc bạn xử lý. "
                "Muốn đổi kết quả kỹ thuật thì phải làm phiên bản báo giá mới.")
                % request.name)

    def _do_confirm(self):
        self.ensure_one()
        self._check_still_processable()
        if self.rfq_line_id.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý qua màn này."))
        self._validate_product_step()
        self._validate_bom_step()

        # §19.7 — Hoàn tất dòng tự XÁC NHẬN định mức còn Nháp và ghi người xử lý
        # là người duyệt (action_confirm ghi approved_by/date). Bỏ được vòng
        # "sang form BOM chỉ để bấm Xác nhận rồi quay lại". Định mức rỗng vẫn bị
        # action_confirm chặn (đã đón đầu bằng nút disable ở dock — can_confirm).
        if self.selected_bom_id.status == "draft":
            self.selected_bom_id.action_confirm()

        self.rfq_line_id.write({
            "resolved_product_id": self.product_id.id,
            "resolved_bom_id": self.selected_bom_id.id,
            "is_infeasible": False,
            "infeasible_reason": False,
            "supplement_note": False,
            "supplement_done": False,
            # Xác nhận lại = đã xem lại xong (dùng cho luồng "Cần xem lại").
            "needs_review": False,
        })
        if self.product_id.is_rfq_provisional:
            self.product_id.write({"is_rfq_provisional": False})
            self.product_id.message_post(body=_(
                "Sản phẩm tạm đã được chính thức hóa khi hoàn tất dòng RFQ %s.")
                % self.rfq_line_id.display_name)
        if self.selected_bom_id.is_rfq_provisional:
            self.selected_bom_id.write({"is_rfq_provisional": False})
            # KHÔNG gọi _set_current_version() ở đây nữa.
            # BOM báo giá là ĐỊNH MỨC CỦA MỘT ĐƠN (instance), không phải phiên
            # bản mới của sản phẩm — trước đây gọi hàm này khiến một đơn lẻ
            # (vd bàn 1400x830) ghi đè "định mức hiện hành" của sản phẩm
            # (bàn 1200x800), làm hỏng truy xuất đơn cũ. Xem
            # dl_bom._should_set_current_version() và thiết kế §3/§7.4.
            self.selected_bom_id.message_post(body=_(
                "BOM tạm đã được chính thức hóa khi hoàn tất dòng RFQ %s.")
                % self.rfq_line_id.display_name)
        self.rfq_line_id._cleanup_rfq_provisional_records()

    def action_confirm(self):
        self._do_confirm()
        return self._action_return_to_rfq()

    def action_confirm_next(self):
        """Băng chuyền cho RFQ nhiều dòng: hoàn tất dòng này rồi mở luôn
        workspace của dòng gia công chưa xử lý kế tiếp — khỏi quay về RFQ
        tự tìm dòng tiếp theo."""
        self.ensure_one()
        next_line = self.next_line_id
        self._do_confirm()
        if not next_line:
            return self._action_return_to_rfq()
        return next_line.action_open_resolve_wizard()
