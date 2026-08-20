from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.dl_quotation_request import _MATCH_THRESHOLD_AUTO


class DlRfqResolveParam(models.TransientModel):
    """Một dòng nhập tham số (D/R/C) trong panel 'Sinh định mức từ mẫu' của
    workspace xử lý RFQ (Đợt 4). Chỉ sống trong phiên xử lý hiện tại."""

    _name = "dl.rfq.resolve.param"
    _description = "Tham số sinh định mức (workspace RFQ)"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "dl.rfq.resolve.wizard", required=True, ondelete="cascade")
    template_param_id = fields.Many2one("dl.bom.template.param", readonly=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(readonly=True)
    name = fields.Char(string="Tham số", readonly=True)
    value = fields.Float(string="Giá trị")
    value_min = fields.Float(readonly=True)
    value_max = fields.Float(readonly=True)
    required = fields.Boolean(readonly=True)
    range_hint = fields.Char(string="Miền hợp lệ", compute="_compute_range_hint")

    @api.depends("value_min", "value_max")
    def _compute_range_hint(self):
        for rec in self:
            if rec.value_min or rec.value_max:
                rec.range_hint = _("Miền hợp lệ: %(min)s – %(max)s") % {
                    "min": rec.value_min or "—", "max": rec.value_max or "—"}
            else:
                rec.range_hint = False


class DlRfqResolveWizard(models.TransientModel):
    """Màn xử lý một dòng RFQ (Kỹ thuật) — làm ĐỊNH MỨC, không làm danh mục.

    Sản phẩm đã được quyết TRƯỚC khi màn này mở (xem `default_get` →
    `dl.quotation.request.line._dlm_autoresolve_product`): Sales chọn Kiểu
    hàng, hoặc hệ thống suy từ tên + nhóm Sales khai. Kỹ thuật không tạo sản
    phẩm ở đây — chỉ NHẬN DIỆN lại nếu máy trỏ sai, rồi chọn/sinh/dựng định mức.

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
        related="rfq_line_id.reference_product_id", string="Kiểu hàng (Sales chọn)", readonly=True)
    request_uom_id = fields.Many2one(
        related="rfq_line_id.uom_id", string="Đơn vị tính", readonly=True)
    # Thông số Sales đã điền theo mẫu của nhóm — hiện ở cột trái để KTV đối chiếu
    # với panel tham số bên phải (panel đã được mồi sẵn từ chính bộ này).
    request_param_ids = fields.One2many(
        related="rfq_line_id.param_ids", string="Thông số (Sales nhập)", readonly=True)
    request_has_params = fields.Boolean(
        related="rfq_line_id.has_parametric_template", readonly=True)
    request_params_out_of_range = fields.Boolean(
        related="rfq_line_id.has_out_of_range_params", readonly=True)
    # Ảnh / file Sales gửi kèm — cho KTV xem ngay trên màn xử lý (readonly).
    request_attachment_ids = fields.Many2many(
        related="rfq_line_id.attachment_ids", string="Ảnh / File Sales gửi", readonly=True)

    # Trạng thái kết luận "không khả thi" của dòng (chỉ để hiện banner + chặn
    # Hoàn tất khi mở lại; nhập/sửa lý do đi qua modal Kết luận không khả thi).
    is_infeasible = fields.Boolean(string="Không khả thi")
    infeasible_reason = fields.Text(string="Lý do không khả thi", readonly=True)

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

    # ── Sản phẩm của dòng ────────────────────────────────────────────────
    # Được điền SẴN khi mở workspace. KTV chỉ đổi khi máy trỏ sai, và chỉ đổi
    # sang sản phẩm ĐÃ CÓ — không có đường tạo mới ở màn này.
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        # CHỈ sản phẩm gia công — bán thành phẩm là cấu phần bên trong định mức,
        # không phải thứ khách đặt, nên không được lọt vào "SP đã từng gia công".
        domain=[("product_kind", "=", "manufactured")],
    )
    product_is_rfq_provisional = fields.Boolean(
        related="product_id.is_rfq_provisional",
        string="Sản phẩm đang tạm từ RFQ",
        readonly=True,
    )

    # EX-05 / D-F — lọc nhóm MỀM: mặc định chỉ hiện SP cùng nhóm Sales khai,
    # nhưng Sales có thể khai nhầm nhóm ⇒ KTV bật cờ này để tìm SP ở MỌI nhóm
    # (thay vì buộc tạo SP trùng nghĩa). Chọn SP khác nhóm sẽ ghi chatter lúc
    # Hoàn tất để Sales sửa nhóm cho RFQ sau. Không chặn — người biết việc là KTV.
    search_outside_category = fields.Boolean(
        string="Tìm sản phẩm ngoài nhóm Sales khai")

    # Danh sách SP hợp lệ để CHỌN: lọc theo Nhóm SP của RFQ (KHÔNG lọc theo
    # trạng thái vòng đời — chọn được cả draft lẫn active). Dùng làm domain cho
    # product_id (giống pattern bom_ids→selected_bom_id).
    allowed_product_ids = fields.Many2many(
        "product.product", compute="_compute_allowed_product_ids",
        string="Sản phẩm hợp lệ")

    @api.depends("request_category_id", "search_outside_category", "rfq_line_id")
    def _compute_allowed_product_ids(self):
        Product = self.env["product.product"]
        for rec in self:
            # CHỈ sản phẩm gia công (xem domain của product_id) — bán thành phẩm
            # thuộc nhánh Vật tư, chọn ở dòng định mức chứ không ở đây.
            domain = [("product_kind", "=", "manufactured")]
            # Lọc nhóm chỉ áp khi KTV CHƯA bật "tìm ngoài nhóm" (EX-05).
            if rec.request_category_id and not rec.search_outside_category:
                domain.append(("categ_id", "child_of", rec.request_category_id.id))
            if rec.rfq_line_id:
                domain.extend([
                    "|",
                    ("is_rfq_provisional", "=", False),
                    ("rfq_source_line_id", "=", rec.rfq_line_id.id),
                ])
            else:
                domain.append(("is_rfq_provisional", "=", False))
            allowed = Product.search(domain)
            # §3.6 — SP gợi ý có thể nằm NGOÀI nhóm Sales khai (vd khớp tên +
            # khách từng đặt nhưng khác nhóm). Gộp vào danh sách chọn được để
            # KTV bấm "Dùng SP này" hoặc chọn từ dropdown mà không phải bật
            # "Tìm ngoài nhóm" thủ công.
            for entry in rec._suggestion_candidates():
                allowed |= entry["product"]
            rec.allowed_product_ids = allowed

    # ── §3.6 · Gợi ý sản phẩm "đã từng gia công" ─────────────────────────────
    suggestion_state = fields.Selection(
        [
            ("none", "Không có gợi ý"),
            ("suggest", "Có gợi ý"),
            ("auto", "Gợi ý tự động"),
        ],
        string="Mức gợi ý", compute="_compute_suggestions")
    suggested_product_id = fields.Many2one(
        "product.product", string="Sản phẩm gợi ý (tốt nhất)",
        compute="_compute_suggestions")
    suggestion_reason = fields.Char(
        string="Vì sao gợi ý", compute="_compute_suggestions")
    suggestion_ids = fields.Many2many(
        "product.product", string="Các sản phẩm gợi ý",
        compute="_compute_suggestions")
    # Số ứng viên gợi ý — trình đánh giá biểu thức phía client của Odoo KHÔNG có
    # len(), nên modifier phải so field đếm này thay vì len(suggestion_ids).
    suggestion_count = fields.Integer(
        string="Số ứng viên gợi ý", compute="_compute_suggestions")
    # Đánh dấu SP hiện tại do hệ thống TỰ CHỌN (đường A, điểm ≥60) — để hiện
    # nhãn "gợi ý tự chọn" ở khối ⑴ đã thu gọn, nhắc KTV vẫn đang xem thứ máy đoán.
    # MỘT field cho mọi lý do, thay vì mỗi lý do một boolean: workspace nay tự
    # quyết sản phẩm ở 5 đường khác nhau, mà mức chắc chắn của chúng khác hẳn
    # nhau — KTV cần biết mình đang gật cái gì. Gộp lại còn để chỗ ghi lý do
    # không phình theo mỗi lần thêm đường.
    product_origin = fields.Selection(
        [
            ("exact_config", "Khớp chính xác cấu hình đã làm"),
            ("suggested", "Hệ thống gợi ý theo tên / nhóm / khách"),
            ("sales_pick", "Sales đã chọn Kiểu hàng"),
            ("name_match", "Trùng tên sản phẩm đã có"),
            ("created", "Tạo từ yêu cầu của Sales"),
        ],
        string="Vì sao là sản phẩm này", copy=False)
    # Có phải máy chọn hộ không (mọi origin đều là máy chọn) — dùng cho các chỗ
    # chỉ cần biết "KTV có tự tay chọn không".
    auto_selected = fields.Boolean(
        string="Sản phẩm do hệ thống tự chọn",
        compute="_compute_auto_selected")

    @api.depends("product_origin")
    def _compute_auto_selected(self):
        for rec in self:
            rec.auto_selected = bool(rec.product_origin)

    def _suggestion_candidates(self, limit=3):
        """Ứng viên gợi ý cho dòng RFQ đang xử lý (dùng lại matcher ở model dòng).

        Chạy khi CHƯA chọn sản phẩm, VÀ trong ca `product_origin='created'`.

        🔴 Vế thứ hai là bắt buộc, đừng rút gọn lại thành "chỉ khi chưa chọn".
        Từ khi workspace tự quyết sản phẩm, dòng nào cũng có `product_id` ngay
        lúc mở — nếu gợi ý tắt theo thì thẻ "Có phải sản phẩm này?" không bao
        giờ hiện nữa. Mà đó chính là chỗ trú của lá chắn TÊN GẦN GIỐNG: luật cũ
        bắt KTV tick xác nhận mới cho tạo, luật mới tạo luôn rồi để thẻ này nhắc
        "hay là dùng cái đã có?". Tắt thẻ = âm thầm đẻ sản phẩm trùng nghĩa.

        Các origin khác không cần: chúng đã trỏ vào một sản phẩm CÓ SẴN, thẻ gợi
        ý thêm chỉ gây nhiễu."""
        self.ensure_one()
        if not self.rfq_line_id:
            return []
        if self.product_id and self.product_origin != "created":
            return []
        return self.rfq_line_id._dlm_suggest_candidates(limit=limit)

    @api.depends("rfq_line_id", "product_id", "product_origin")
    def _compute_suggestions(self):
        for rec in self:
            rec.suggestion_state = "none"
            rec.suggested_product_id = False
            rec.suggestion_reason = False
            rec.suggestion_ids = self.env["product.product"]
            rec.suggestion_count = 0
            ranked = rec._suggestion_candidates(limit=3)
            if not ranked:
                continue
            best = ranked[0]
            rec.suggested_product_id = best["product"].id
            rec.suggestion_reason = ", ".join(best["reasons"])
            rec.suggestion_ids = [(6, 0, [e["product"].id for e in ranked])]
            rec.suggestion_count = len(ranked)
            rec.suggestion_state = (
                "auto" if best["score"] >= _MATCH_THRESHOLD_AUTO else "suggest")

    bom_ids = fields.Many2many(
        "dl.bom", compute="_compute_bom_ids", string="Phiên bản BOM")
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

    # ── EX-09: SP đã chọn đã có định mức nào chưa? (ẩn bảng phiên bản rỗng) ──
    has_any_bom = fields.Boolean(
        string="Sản phẩm đã có định mức", compute="_compute_has_any_bom")

    @api.depends("bom_ids")
    def _compute_has_any_bom(self):
        for rec in self:
            rec.has_any_bom = bool(rec.bom_ids)

    # ── Đợt 4 — sinh định mức từ BOM mẫu tham số ─────────────────────────────
    parametric_template_id = fields.Many2one(
        "dl.bom.template", string="Mẫu tham số",
        compute="_compute_parametric_template")
    has_parametric_template = fields.Boolean(
        string="Nhóm sản phẩm có mẫu tham số", compute="_compute_parametric_template")
    show_param_panel = fields.Boolean(string="Đang mở panel tham số")
    param_line_ids = fields.One2many(
        "dl.rfq.resolve.param", "wizard_id", string="Tham số")
    # RES-028 — định mức đang chọn là bản TÁI DÙNG (cấu hình này đã từng được
    # chốt) chứ không phải bản vừa sinh. Chỉ sống trong phiên xử lý hiện tại.
    param_reused_bom = fields.Boolean(string="Dùng lại định mức đã có")

    @api.depends("product_id", "product_id.categ_id", "request_category_id")
    def _compute_parametric_template(self):
        Template = self.env["dl.bom.template"]
        for rec in self:
            tmpl = Template.browse()
            # Chưa chọn SP thì lấy nhóm của dòng RFQ: nếu đợi có product_id mới
            # tìm được mẫu thì Kỹ thuật đã đi qua ngã ba "tạo SP mới" từ trước
            # (gà-và-trứng) — đúng cái khiến mỗi cỡ đẻ một mã sản phẩm.
            categ = rec.product_id.categ_id or rec.request_category_id
            if categ:
                tmpl = Template.search([
                    ("product_category_id", "=", categ.id),
                    ("status", "in", ("confirmed", "locked")),
                    ("is_parametric", "=", True),
                ], order="is_current desc, version desc", limit=1)
            rec.parametric_template_id = tmpl
            rec.has_parametric_template = bool(tmpl)

    # ── EX-16: định mức đang chọn có phải bản NHÁP TẠM (bỏ ngay được không) ──
    selected_bom_can_discard = fields.Boolean(
        string="Có thể bỏ bản nháp",
        compute="_compute_selected_bom_can_discard")

    @api.depends("selected_bom_id", "selected_bom_id.is_rfq_provisional",
                 "selected_bom_id.status")
    def _compute_selected_bom_can_discard(self):
        for rec in self:
            bom = rec.selected_bom_id
            rec.selected_bom_can_discard = bool(
                bom and bom.is_rfq_provisional and bom.status == "draft")

    # ── EX-13 / RES-022: vật tư trong định mức chưa có giá NCC đã duyệt ──────
    # Chỉ lộ TÊN + SỐ LƯỢNG vật tư thiếu giá — KTV KHÔNG thấy con số giá (§15.4).
    pricing_block_count = fields.Integer(
        string="Số vật tư thiếu giá nhà cung cấp", compute="_compute_pricing_block")
    pricing_block_names = fields.Char(
        string="Vật tư thiếu giá nhà cung cấp", compute="_compute_pricing_block")

    @api.depends("selected_bom_id", "selected_bom_id.line_ids",
                 "selected_bom_id.line_ids.material_id",
                 "selected_bom_id.line_ids.material_id.dlm_supplier_price_state")
    def _compute_pricing_block(self):
        for rec in self:
            missing = rec.selected_bom_id._dlm_unpriced_raw_materials()
            rec.pricing_block_count = len(missing)
            rec.pricing_block_names = ", ".join(
                missing.mapped("display_name")) if missing else False

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
                 "selected_bom_confirmed", "is_infeasible",
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
            if rec.is_infeasible:
                blockers.append(_(
                    "dòng đang kết luận Không khả thi — bấm “Xử lý lại dòng "
                    "này” nếu muốn tiếp tục"))
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

    @api.depends("product_id")
    def _compute_bom_ids(self):
        Bom = self.env["dl.bom"]
        for rec in self:
            if rec.product_id:
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

    @api.depends("bom_ids", "manual_bom_id", "product_id")
    def _compute_selected_bom_id(self):
        # selected_bom_id KHÔNG lưu → được tính lại mỗi lần đọc/nạp lại form.
        # Nhờ vậy khi KTV mở 1 BOM Nháp ra Xác nhận rồi quay lại workspace, giá
        # trị được tính lại và tự bắt đúng BOM vừa duyệt (không phải chọn lại
        # sản phẩm mới lấy được — đây là lỗi trước đây do onchange chỉ chạy khi
        # đổi product_id, còn quay lại workspace là reload phía client).
        for rec in self:
            if not rec.product_id:
                rec.selected_bom_id = False
                continue
            # Ưu tiên giữ đúng BOM KTV đã chỉ định (nếu còn hợp lệ với SP hiện tại).
            if rec.manual_bom_id and rec.manual_bom_id in rec.bom_ids:
                rec.selected_bom_id = rec.manual_bom_id
                continue
            # SẢN PHẨM DÙNG CHUNG của mẫu tham số: KHÔNG có định mức mặc định.
            # Định mức của nó là instance — mỗi bản MỘT CỠ, tồn tại song song —
            # nên "version cao nhất" chỉ là cỡ được sinh gần nhất. Tự chọn nó là
            # gán cho đơn đang xử lý một kích thước khác hẳn, mà checklist vẫn
            # tick đủ nên bấm Hoàn tất là chốt luôn. Để trống, buộc đi qua panel
            # nhập kích thước (nhập đúng cấu hình cũ thì generate_instance tự
            # trả về bản đã chốt — RES-028).
            if rec.product_id._dlm_is_parametric_generic():
                rec.selected_bom_id = False
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
                if line.supplement_note:
                    res["has_existing_supplement"] = True
                if line.is_infeasible:
                    # Mở lại dòng đã kết luận không khả thi → hiện banner kết
                    # luận (kèm lý do) ở đầu workspace; KTV sửa lý do trong modal
                    # hoặc bấm "Xử lý lại dòng này" để tiếp tục xử lý.
                    res.update({
                        "is_infeasible": True,
                        "infeasible_reason": line.infeasible_reason,
                    })
                else:
                    if line.resolved_product_id:
                        res.update({
                            "product_id": line.resolved_product_id.id,
                        })
                        # Dòng tự chốt qua làn L0: KTV mở ra xem lại thì phải
                        # thấy NGAY vì sao đã có sẵn kết quả mà mình chưa làm gì.
                        if line.auto_resolved:
                            res["product_origin"] = "exact_config"
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
                                    "product_id": provisional_product.id,
                            })
                        if provisional_bom:
                            res["manual_bom_id"] = provisional_bom.id
                # ── Chưa khôi phục được sản phẩm nào ⇒ HỆ THỐNG TỰ QUYẾT ──────
                # Kỹ thuật mở workspace ra là để làm ĐỊNH MỨC. Việc "món này mới
                # hay cũ, có phải đẻ thêm mã sản phẩm không" suy được từ dữ liệu
                # Sales đã khai, nên trả lời xong trước khi màn hình hiện ra.
                # KTV vẫn lật lại được bằng nút "Đổi sản phẩm".
                if not res.get("product_id") and not line.is_infeasible:

                    # (1) Khớp CHỮ KÝ THAM SỐ — cùng mẫu, cùng bộ số, tức cùng
                    # cấu hình. Đứng đầu vì đây không phải phỏng đoán.
                    #
                    # 🔴 Ở đây generic của mẫu tham số ĐƯỢC tự chọn, ngược với
                    # đường mờ (2). Không mâu thuẫn: (2) cấm generic vì điểm nó
                    # nhận là điểm "THUỘC HỌ" — đúng như nhau cho mọi cỡ nên tự
                    # gán là quyết hộ. Khớp chữ ký thì đã xuống tới ĐÚNG MỘT CỠ,
                    # và định mức đi kèm cũng là của đúng cỡ đó.
                    if line.exact_bom_id:
                        res.update({
                            "product_id": line.exact_bom_id.product_id.id,
                            "manual_bom_id": line.exact_bom_id.id,
                            "product_origin": "exact_config",
                        })

                    # (2) §3.6 đường A — bộ dò khớp đạt ngưỡng tự động (≥60).
                    # Đặt TRƯỚC bậc thang (3) vì tín hiệu mạnh nhất của nó là
                    # `reference_product_id`: Sales chỉ tận tay "giống cái này".
                    if not res.get("product_id"):
                        ranked = line._dlm_suggest_candidates(limit=1)
                        if (ranked and ranked[0]["score"] >= _MATCH_THRESHOLD_AUTO
                                and not ranked[0]["product"]._dlm_is_parametric_generic()):
                            res.update({
                                    "product_id": ranked[0]["product"].id,
                                "product_origin": "suggested",
                            })

                    # (3) Bậc thang suy sản phẩm: dùng chung của mẫu → trùng hệt
                    # tên → tạo mới từ tên + nhóm Sales khai. Đây là phần thay
                    # cho khối "Tạo sản phẩm mới" mà KTV từng phải tự điền.
                    if not res.get("product_id"):
                        product, origin = line._dlm_autoresolve_product()
                        if product:
                            res.update({
                                    "product_id": product.id,
                                "product_origin": origin,
                            })
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
        """Kết thúc workspace và trở về đúng RFQ nguồn.

        Dùng ``target: 'main'`` (KHÔNG phải 'current'): trở về RFQ khi thoát
        workspace phải ĐẶT LẠI breadcrumb về đúng một mục ``[RFQ]``, không đẩy
        thêm bản sao. 'current' đẩy một act_window RFQ MỚI lên cuối stack nên
        mỗi vòng "mở RFQ → xử lý → quay lại" lại nối thêm
        ``… / RFQ / Workspace / RFQ`` và càng lặp càng rối. 'main' xoá stack
        (action_service: target === 'main' ⇒ clearBreadcrumbs) rồi mở đúng RFQ.
        """
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
            "target": "main",
        }

    def _validate_product_step(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_(
                "Chưa xác định được sản phẩm cho dòng này. Chọn một sản phẩm đã "
                "từng gia công, hoặc bấm Cần bổ sung để Sales làm rõ yêu cầu."))

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
        """Khối ⑴ đang thu gọn → mở lại để KTV trỏ sang MỘT SẢN PHẨM ĐÃ CÓ khác.

        Không còn đường "tạo sản phẩm mới" ở đây: khai sinh danh mục là việc
        hành chính, hệ thống làm ngầm từ tên + nhóm Sales khai. Cái KTV làm ở
        đây là NHẬN DIỆN — "món này chính là thứ ta từng gia công" — và hệ quả
        của nó là kéo theo bộ định mức của sản phẩm đó."""
        self.ensure_one()
        self.write({
            "product_id": False,
            "manual_bom_id": False,
            "show_bom_picker": False,
            "product_origin": False,
            "param_reused_bom": False,
        })
        return self._action_reload()

    def action_restore_auto_product(self):
        """Quay lại sản phẩm hệ thống đã đề xuất (sau khi bấm nhầm Đổi sản phẩm).

        Bắt buộc phải có từ khi gỡ nút "Tạo sản phẩm mới": với một món thật sự
        mới, KTV bấm Đổi sản phẩm là mất luôn sản phẩm vừa được dựng ngầm mà
        không còn cách nào lấy lại — kẹt cứng giữa chừng. `_dlm_autoresolve_product`
        nhận lại bản tạm cũ nên gọi lại không đẻ thêm sản phẩm."""
        self.ensure_one()
        product, origin = self.rfq_line_id._dlm_autoresolve_product()
        if not product:
            raise UserError(_(
                "Không suy được sản phẩm từ yêu cầu của Sales. Hãy chọn một sản "
                "phẩm đã từng gia công, hoặc bấm Cần bổ sung để Sales làm rõ."))
        self.write({"product_id": product.id, "product_origin": origin})
        return self._action_reload()

    def action_use_suggested_product(self):
        """§3.6 — chấp nhận SP hệ thống gợi ý (thẻ 'Có phải cái này?'): gán
        thẳng làm sản phẩm xác định, khối ⑴ tự thu gọn sang khối ⑵."""
        self.ensure_one()
        if not self.suggested_product_id:
            raise UserError(_("Không có sản phẩm gợi ý để chọn."))
        chosen = self.suggested_product_id
        self.write({
            "product_id": chosen.id,
            "manual_bom_id": False,
            "product_origin": False,
        })
        # KTV vừa nói "dùng món cũ" ⇒ sản phẩm tạm mà hệ thống tự tạo cho dòng
        # này là rác, dọn ngay thay vì để cron 7 ngày sau mới gom. Không dọn thì
        # nó còn nằm trong danh mục Nháp và lọt vào ô chọn của người khác.
        self.rfq_line_id._cleanup_rfq_provisional_records(
            keep_product_ids=chosen.ids)
        return self._action_reload()

    def action_toggle_bom_picker(self):
        """Khối ⑵: bấm 'Chọn bản khác' để lộ lại bảng phiên bản định mức (khi đã
        có một định mức được tự chọn/thu gọn)."""
        self.ensure_one()
        self.show_bom_picker = not self.show_bom_picker
        return self._action_reload()

    def action_search_outside_category(self):
        """EX-05 / D-F — bật/tắt tìm SP ở MỌI nhóm (khi Sales khai nhầm nhóm).
        Xoá lựa chọn hiện tại để KTV chọn lại trong danh sách mở rộng."""
        self.ensure_one()
        self.write({
            "search_outside_category": not self.search_outside_category,
            "product_id": False,
            "manual_bom_id": False,
            "product_origin": False,
        })
        return self._action_reload()

    def action_discard_draft_bom(self):
        """EX-16 — bỏ NGAY một bản định mức nháp tạm (đổi ý) thay vì chờ cron 7
        ngày. Chỉ áp dụng cho BOM đang tạm (is_rfq_provisional) + Nháp."""
        self.ensure_one()
        bom = self.selected_bom_id
        if not (bom and bom.is_rfq_provisional and bom.status == "draft"):
            raise UserError(_(
                "Chỉ bỏ được bản định mức nháp tạm của phiên xử lý này."))
        self.manual_bom_id = False
        self.show_bom_picker = False
        bom.sudo().unlink()
        return self._action_reload()

    def action_notify_purchasing(self):
        """EX-13 / RES-022 — báo nhóm Mua hàng cập nhật giá NCC cho các vật tư
        thô còn thiếu giá đã duyệt trong định mức đang chọn.

        Giao việc + đăng chatter TRÊN CHÍNH VẬT TƯ (product.product): nhóm Mua
        hàng sở hữu vật tư (read+write) nên mở được. KHÔNG gắn việc lên RFQ vì
        Mua hàng KHÔNG có quyền đọc dl.quotation.request ⇒ activity sẽ trỏ vào
        bản ghi họ không mở nổi. Có CHỐNG TRÙNG: không tạo lại việc 'cập nhật
        giá' đang mở cho cùng vật tư + cùng người. KTV chỉ nêu TÊN vật tư, không
        đụng tới giá. RFQ chỉ nhận một dòng GHI VẾT (Sales/Kỹ thuật đọc được)."""
        self.ensure_one()
        missing = self.selected_bom_id._dlm_unpriced_raw_materials()
        if not missing:
            return self._action_reload()
        request = self.rfq_line_id.quotation_request_id
        line_name = self.rfq_line_id.product_name or ""
        purchasing = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        users = purchasing.users if purchasing else self.env["res.users"]
        todo_type = self.env.ref("mail.mail_activity_data_todo")
        Activity = self.env["mail.activity"].sudo()
        for material in missing:
            material.sudo().message_post(body=_(
                "Kỹ thuật (RFQ %(rfq)s — dòng %(line)s) cần Mua hàng cập nhật "
                "giá nhà cung cấp (đã duyệt &amp; đang áp dụng) cho vật tư này.",
                rfq=request.name, line=line_name))
            for user in users:
                already_open = Activity.search_count([
                    ("res_model", "=", "product.product"),
                    ("res_id", "=", material.id),
                    ("user_id", "=", user.id),
                    ("activity_type_id", "=", todo_type.id),
                ])
                if already_open:
                    continue
                material.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Cập nhật giá nhà cung cấp — %s") % material.display_name,
                    note=_("Yêu cầu từ Kỹ thuật khi xử lý RFQ %(rfq)s "
                           "(dòng %(line)s).", rfq=request.name, line=line_name),
                    user_id=user.id,
                )
        # Ghi vết trên RFQ để Sales/Kỹ thuật thấy đã báo Mua hàng (họ đọc RFQ được).
        request.sudo().message_post(body=_(
            "Kỹ thuật đã báo Mua hàng cập nhật giá nhà cung cấp cho vật tư của dòng "
            "<b>%(line)s</b>: %(names)s.",
            line=line_name, names=", ".join(missing.mapped("display_name"))))
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

    def _open_quick_wizard(self, res_model, view_xmlid, name):
        """Mở modal kết luận nhanh (dùng chung với luồng triage trên bảng RFQ)
        thay vì xổ ô nhập ngay trong dock — nhập lý do/nội dung rồi bấm xác nhận
        trong modal. Modal tự nạp lại nội dung cũ (default_get) nếu dòng đã có."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "view_mode": "form",
            "views": [(self.env.ref(view_xmlid).id, "form")],
            "target": "new",
            "context": {"default_rfq_line_id": self.rfq_line_id.id},
        }

    def action_show_supplement(self):
        return self._open_quick_wizard(
            "dl.rfq.line.supplement.wizard",
            "dl_technical.view_dl_rfq_line_supplement_wizard_form",
            _("Yêu cầu Sales bổ sung"))

    def action_show_infeasible(self):
        return self._open_quick_wizard(
            "dl.rfq.line.infeasible.wizard",
            "dl_technical.view_dl_rfq_line_infeasible_wizard_form",
            _("Kết luận không khả thi"))

    def action_reopen_feasible(self):
        """Mở lại dòng đã kết luận Không khả thi để xử lý tiếp — gỡ cờ tạm trong
        phiên này; cờ trên dòng RFQ chỉ được xóa hẳn khi bấm Hoàn tất."""
        self.ensure_one()
        self.write({"is_infeasible": False})
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

    def action_create_bom(self):
        """Tạo BOM nháp rồi mở form BOM full-page trên breadcrumb workspace."""
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Chưa xác định được sản phẩm cho dòng này."))
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

    # ── Đợt 4 — panel nhập tham số + Sinh định mức ───────────────────────────
    @api.model
    def _dlm_param_panel_commands(self, tmpl, rfq_line=None):
        """Lệnh o2m dựng panel tham số của một mẫu, mồi sẵn số Sales đã nhập.

        ⚠️ Luật ở đây ĐÃ ĐỔI, đọc kỹ trước khi "sửa cho nhất quán":

        Bản trước LUÔN để trống, với lý do "không đọc từ mô tả Sales vì đó là
        văn bản tự do, sai một chữ số là sai cả báo giá". Lý do đó đúng với văn
        bản tự do và vẫn còn hiệu lực — `_dlm_parse_dimensions` (regex đoán) tới
        giờ vẫn KHÔNG được phép mồi vào đây.

        Cái đổi là Sales nay nhập thông số vào Ô CÓ NHÃN DO CHÍNH MẪU NÀY ĐỊNH
        NGHĨA (`dl.quotation.request.line.param`), có miền hợp lệ và cổng chặn
        lúc gửi. Đó không còn là số đoán từ câu chữ, mà là đề bài khách đưa —
        thứ KTV vốn phải gõ lại y nguyên từ cột bên trái sang.

        Vẫn KHÔNG lấy `default_value` của mẫu: mặc định là con số của mẫu chứ
        không của khách; mồi nó vào thì mọi dòng thiếu kích thước cùng ra một
        định mức mà không ai thấy sai. Ô nào Sales bỏ trống thì để trống, và
        _dlm_validate_param_values chặn khi bấm Sinh định mức."""
        sales_values = {}
        if rfq_line:
            sales_values = {
                p.code: p.value for p in rfq_line.param_ids if p.value}
        commands = [(5, 0, 0)]
        for param in tmpl.param_ids:
            commands.append((0, 0, {
                "template_param_id": param.id,
                "sequence": param.sequence,
                "code": param.code,
                "name": param.name,
                "value": sales_values.get(param.code, 0.0),
                "value_min": param.value_min,
                "value_max": param.value_max,
                "required": param.required,
            }))
        return commands

    def action_open_param_panel(self):
        """Mở panel nhập tham số (D/R/C) của mẫu tham số cho nhóm SP hiện tại."""
        self.ensure_one()
        tmpl = self.parametric_template_id
        if not tmpl:
            raise UserError(_(
                "Nhóm sản phẩm này chưa có BOM mẫu tham số đã xác nhận."))
        self.write({
            "show_param_panel": True,
            "param_line_ids": self._dlm_param_panel_commands(
                tmpl, self.rfq_line_id),
        })
        return self._action_reload()

    def action_close_param_panel(self):
        self.ensure_one()
        self.write({"show_param_panel": False, "param_line_ids": [(5, 0, 0)]})
        return self._action_reload()

    def action_generate_instance(self):
        """Sinh định mức từ mẫu tham số + gắn làm định mức đang chọn của dòng.
        Định mức chuẩn của các dòng vật tư được tính tự động — KTV không nhập tay."""
        self.ensure_one()
        tmpl = self.parametric_template_id
        if not tmpl:
            raise UserError(_("Không có BOM mẫu tham số để sinh."))
        if not self.product_id:
            raise UserError(_("Vui lòng chọn sản phẩm trước khi sinh định mức."))
        param_values = {pl.code: pl.value for pl in self.param_line_ids}
        # Dọn bản tạm cũ của dòng (nếu KTV sinh lại) rồi sinh mới; giữ SP đang dùng.
        self.rfq_line_id._cleanup_rfq_provisional_records(
            keep_product_ids=self.product_id.ids)
        bom = tmpl.generate_instance(
            self.product_id, param_values, self.rfq_line_id)
        self.write({
            "manual_bom_id": bom.id,
            "show_param_panel": False,
            "param_line_ids": [(5, 0, 0)],
            # RES-028 — generate_instance trả bản CŨ khi cấu hình này đã từng
            # được chốt. Báo cho KTV biết đang tái dùng, không phải vừa sinh mới.
            "param_reused_bom": not bom.is_rfq_provisional,
        })
        return self._action_reload()

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

    def _dlm_finalize_btp_tree(self):
        """§12.7 — chính thức hóa cả cây vật tư/BTP tạm của dòng RFQ (không chỉ
        SP + BOM cha đã chọn). Confirm BOM con (BTP) TRƯỚC BOM cha để giá vốn
        BTP đã sẵn khi snapshot dòng cha tính lại (LK-16). BTP/BOM con KHÔNG
        được dùng thì cứ để tạm — _cleanup_rfq_provisional_records() cuối luồng
        sẽ dọn (has_stored_many2one_reference giữ cái còn được trỏ tới)."""
        self.ensure_one()
        line = self.rfq_line_id
        Bom = self.env["dl.bom"].sudo()
        Product = self.env["product.product"].sudo()
        parent_bom = self.selected_bom_id

        line_boms = Bom.search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "=", line.id),
        ])
        child_boms = line_boms - parent_bom
        # Vật tư/BTP đang thực sự được các định mức tạm của dòng dùng tới.
        used_material_ids = set(line_boms.mapped("line_ids.material_id").ids)

        # Confirm BOM con của các BTP đang được dùng (còn Nháp & có dòng).
        for bom in child_boms:
            if (bom.status == "draft" and bom.line_ids
                    and bom.product_id.id in used_material_ids):
                bom.action_confirm()

        # De-provision BTP tạm đang được dùng.
        provisional_products = Product.with_context(active_test=False).search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "=", line.id),
            ("id", "!=", self.product_id.id),
        ])
        for prod in provisional_products:
            if prod.id in used_material_ids:
                prod.write({"is_rfq_provisional": False})
                prod.message_post(body=_(
                    "Bán thành phẩm tạm đã được chính thức hóa khi hoàn tất "
                    "dòng RFQ %s.") % line.display_name)
        # De-provision BOM con của các BTP đã dùng (đã confirmed ở trên).
        for bom in child_boms:
            if (bom.product_id.id in used_material_ids
                    and bom.is_rfq_provisional and bom.status != "draft"):
                bom.write({"is_rfq_provisional": False})
                bom.message_post(body=_(
                    "Định mức bán thành phẩm tạm đã được chính thức hóa khi hoàn tất "
                    "dòng RFQ %s.") % line.display_name)

    def _do_confirm(self):
        self.ensure_one()
        self._check_still_processable()
        if self.rfq_line_id.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý qua màn này."))
        self._validate_product_step()
        self._validate_bom_step()

        # §12.7 — Chính thức hóa CẢ CÂY BTP tạm của dòng TRƯỚC (confirm BOM con
        # của BTP + de-provision BTP đang dùng) để giá vốn BTP đã sẵn sàng khi
        # snapshot định mức cha tính lại (LK-16).
        self._dlm_finalize_btp_tree()

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
        # EX-05 — SP chốt KHÁC nhóm Sales khai (KTV đã bật "Tìm ngoài nhóm"):
        # ghi chatter để Sales sửa nhóm cho RFQ sau. So bằng parent_path (child_of).
        req_categ = self.rfq_line_id.product_category_id
        prod_categ = self.product_id.categ_id
        if (req_categ and prod_categ and req_categ.parent_path
                and not (prod_categ.parent_path or "").startswith(req_categ.parent_path)):
            self.rfq_line_id.quotation_request_id.sudo().message_post(body=_(
                "Kỹ thuật chọn sản phẩm <b>%(prod)s</b> thuộc nhóm "
                "<b>%(pcat)s</b> cho dòng <b>%(line)s</b> mà Sales khai nhóm "
                "<b>%(rcat)s</b>. Cân nhắc sửa lại nhóm sản phẩm cho các RFQ sau.",
                prod=self.product_id.display_name, pcat=prod_categ.display_name,
                line=self.rfq_line_id.product_name or "",
                rcat=req_categ.display_name))

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
        # Băng chuyền: mở workspace dòng kế THAY THẾ breadcrumb thay vì chồng
        # thêm — RFQ nhiều dòng mà cứ đẩy 'current' sẽ dựng
        # ``[RFQ, ws1, ws2, ws3…]`` càng lúc càng rối. 'main' giữ breadcrumb
        # gọn ở đúng một workspace đang xử lý; thoát băng chuyền vẫn về [RFQ].
        action = next_line.action_open_resolve_wizard()
        action["target"] = "main"
        return action
