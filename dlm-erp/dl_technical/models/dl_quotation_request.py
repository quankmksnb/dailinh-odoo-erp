from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

# Field-level RBAC (giống dl.material): chỉ Kỹ thuật/Admin được quyết định
# "sản phẩm xác định" / "không khả thi" — đây là đánh giá kỹ thuật, Sales chỉ
# được nhập yêu cầu (product_name/product_category_id/quantity/dimension_note).
_TECH_ONLY_LINE_FIELDS = {'resolved_product_id', 'resolved_bom_id', 'is_infeasible', 'infeasible_reason'}

# Chiều ngược lại: thông tin YÊU CẦU do Sales sở hữu. Kỹ thuật khi nhận RFQ chỉ
# xử lý phần kỹ thuật (Product/BOM/vật tư/bản vẽ nằm ở model dl.product/dl.bom),
# KHÔNG được sửa nội dung yêu cầu của dòng...
_SALES_ONLY_LINE_FIELDS = {
    'product_type', 'product_name', 'product_category_id',
    'reference_product_id', 'quantity', 'dimension_note', 'attachment_ids',
}
# ...cũng như thông tin thương mại ở header (khách hàng, ngày nhận, hạn yêu cầu).
_SALES_ONLY_HEADER_FIELDS = {'customer_id', 'requested_date', 'deadline'}


def _user_is_sales(env):
    """Sales sở hữu thông tin yêu cầu = BA / Trưởng phòng KD / Admin."""
    user = env.user
    return (user.has_group('dl_base.dl_group_ba')
            or user.has_group('dl_base.dl_group_sales_manager')
            or user.has_group('dl_base.dl_group_admin'))


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
            ("returned", "Trả lại bổ sung"),
            ("supplemented", "Đã bổ sung"),
            ("confirmed", "Đã xử lý xong – chờ tạo báo giá"),
            ("quoted", "Đã tạo báo giá"),
            ("cancelled", "Đã hủy"),
        ],
        string="Trạng thái",
        default="new",
        readonly=True,
        copy=False,
        tracking=True,
    )

    # Lý do KTV trả lại RFQ cho Sales bổ sung (giữ lý do gần nhất; lịch sử đầy
    # đủ nằm ở chatter).
    return_reason = fields.Text(
        string="Lý do trả lại",
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

    # Tiếp nhận: ai bấm "Nhận xử lý" + lúc nào. Để Sales thấy "đang do ai xử lý"
    # và chống hai KTV làm song song một RFQ (nhất là tránh tạo product Draft
    # trùng khi cùng xử lý custom lines). Gán ở action_receive.
    received_by = fields.Many2one(
        "res.users",
        string="Người tiếp nhận",
        readonly=True,
        copy=False,
        tracking=True,
    )
    received_date = fields.Datetime(
        string="Thời điểm tiếp nhận",
        readonly=True,
        copy=False,
    )

    # Cờ + câu cảnh báo mềm cho banner "đang do anh A xử lý từ HH:MM": hiện khi
    # RFQ đã có người tiếp nhận và người đang mở KHÔNG phải người đó. Người mở
    # sau vẫn xem/thao tác được — chỉ nhắc để tránh xử lý trùng.
    received_by_other = fields.Boolean(
        string="Đã có người khác tiếp nhận",
        compute="_compute_received_info",
    )
    received_info = fields.Char(
        string="Thông tin tiếp nhận",
        compute="_compute_received_info",
    )

    @api.depends("received_by", "received_date")
    def _compute_received_info(self):
        for rec in self:
            rec.received_by_other = (
                bool(rec.received_by) and rec.received_by != self.env.user)
            if rec.received_by:
                when = ""
                if rec.received_date:
                    local_dt = fields.Datetime.context_timestamp(
                        rec, rec.received_date)
                    when = _(" từ %s") % local_dt.strftime("%H:%M %d/%m/%Y")
                rec.received_info = _("Đang do %s xử lý%s.") % (
                    rec.received_by.name, when)
            else:
                rec.received_info = ""

    note = fields.Text(
        string="Ghi chú",
    )

    line_ids = fields.One2many(
        "dl.quotation.request.line",
        "quotation_request_id",
        string="Danh sách sản phẩm",
    )

    # Tiến độ dành riêng cho phần việc Kỹ thuật: chỉ tính dòng gia công vì dòng
    # thương mại đã được Sales chọn sản phẩm và không đi qua BOM.
    technical_total_line_count = fields.Integer(
        string="Tổng dòng gia công",
        compute="_compute_technical_progress",
    )
    technical_done_line_count = fields.Integer(
        string="Dòng gia công đã xử lý",
        compute="_compute_technical_progress",
    )
    technical_progress_percent = fields.Float(
        string="Phần trăm tiến độ kỹ thuật",
        compute="_compute_technical_progress",
    )
    technical_progress_label = fields.Char(
        string="Tiến độ kỹ thuật",
        compute="_compute_technical_progress",
    )

    @api.depends(
        "line_ids.product_type",
        "line_ids.resolved_product_id",
        "line_ids.resolved_bom_id",
        "line_ids.is_infeasible",
    )
    def _compute_technical_progress(self):
        for rec in self:
            technical_lines = rec.line_ids.filtered(
                lambda line: line.product_type == "manufactured")
            total = len(technical_lines)
            done = len(technical_lines.filtered(
                lambda line: line.is_infeasible
                or bool(line.resolved_product_id and line.resolved_bom_id)))

            rec.technical_total_line_count = total
            rec.technical_done_line_count = done
            rec.technical_progress_percent = (done * 100.0 / total) if total else 0.0
            rec.technical_progress_label = (
                _("Đã xử lý %(done)s/%(total)s dòng gia công",
                  done=done, total=total)
                if total
                else _("Không có dòng gia công cần xử lý")
            )

    # Tô màu dòng RFQ cận/quá hạn ngay trên danh sách (đồng bộ list Báo giá):
    # deadline sắp tới hoặc đã qua → cảnh báo để Kỹ thuật/Sales ưu tiên xử lý.
    # Chỉ tính khi RFQ CÒN MỞ (chưa "Đã tạo báo giá"/"Đã hủy") — khớp đúng điều
    # kiện của filter "Quá hạn" trong search view. RFQ đã đóng luôn để 'ok'
    # (không tô), nhường màu xám cho decoration-muted.
    _OPEN_DEADLINE_STATES = ("new", "processing", "returned", "supplemented", "confirmed")

    deadline_state = fields.Selection(
        [
            ("ok", "Còn hạn"),
            ("soon", "Sắp đến hạn"),
            ("overdue", "Quá hạn"),
        ],
        string="Tình trạng hạn",
        compute="_compute_deadline_state",
    )

    @api.depends("deadline", "status")
    def _compute_deadline_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            state = "ok"
            if rec.status in self._OPEN_DEADLINE_STATES and rec.deadline:
                if rec.deadline < today:
                    state = "overdue"
                elif (rec.deadline - today).days <= 7:
                    state = "soon"
            rec.deadline_state = state

    # Màn Tạo RFQ tách 2 bảng riêng (trên/dưới) để cột không trùng nhau — cùng
    # trỏ line_ids, lọc + mặc định theo product_type. line_ids gốc vẫn dùng cho
    # status/logic.
    manufactured_line_ids = fields.One2many(
        "dl.quotation.request.line",
        "quotation_request_id",
        string="Sản phẩm gia công",
        domain=[("product_type", "=", "manufactured")],
        context={"default_product_type": "manufactured"},
    )
    trading_line_ids = fields.One2many(
        "dl.quotation.request.line",
        "quotation_request_id",
        string="Sản phẩm thương mại",
        domain=[("product_type", "=", "trading")],
        context={"default_product_type": "trading"},
    )

    # Hiển thị trên list "RFQ cần xử lý" — gộp từ các dòng (1 RFQ có thể nhiều
    # dòng, mỗi dòng 1 Product/BOM tham chiếu riêng).
    resolved_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_resolved_refs",
        string="Product Reference",
    )
    resolved_bom_ids = fields.Many2many(
        "dl.bom",
        compute="_compute_resolved_refs",
        string="BOM Reference",
    )

    @api.depends("line_ids.resolved_product_id", "line_ids.resolved_bom_id")
    def _compute_resolved_refs(self):
        for rec in self:
            rec.resolved_product_ids = rec.line_ids.mapped("resolved_product_id")
            rec.resolved_bom_ids = rec.line_ids.mapped("resolved_bom_id")

    # Field-level RBAC (đối xứng với dòng RFQ): True nếu user là Kỹ thuật/Admin —
    # dùng để khóa readonly các field YÊU CẦU (khách hàng / ngày nhận / hạn) trên
    # form xử lý. compute_sudo vì user ngoài nhóm vẫn cần đọc để tính readonly.
    is_technician = fields.Boolean(
        compute="_compute_is_technician", compute_sudo=True)

    def _compute_is_technician(self):
        is_tech = (self.env.user.has_group("dl_base.dl_group_tech")
                   or self.env.user.has_group("dl_base.dl_group_admin"))
        for rec in self:
            rec.is_technician = is_tech

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("dl.quotation.request")
                    or _("New")
                )
        return super().create(vals_list)

    @api.constrains("deadline", "requested_date")
    def _check_deadline(self):
        """Hạn xử lý RFQ không được nằm trước ngày tiếp nhận yêu cầu — neo vào
        requested_date (không phải "hôm nay") để RFQ cũ đã qua hạn hợp lệ vẫn
        sửa được, còn RFQ mới (requested_date mặc định = hiện tại) thì tương
        đương "không được chọn ngày quá khứ"."""
        for rec in self:
            if not rec.deadline or not rec.requested_date:
                continue
            requested = fields.Date.to_date(rec.requested_date)
            if rec.deadline < requested:
                raise ValidationError(_(
                    "Hạn yêu cầu (%(deadline)s) không được trước ngày nhận "
                    "yêu cầu (%(requested)s).",
                    deadline=rec.deadline, requested=requested))

    def _recompute_status_from_lines(self):
        for rec in self:

            # Các trạng thái "chốt" hoặc chờ thao tác người dùng — không tự đổi:
            #  - returned: chờ Sales bổ sung (chỉ action_resubmit đưa ra).
            #  - quoted/cancelled: đã kết thúc.
            if rec.status in ("returned", "quoted", "cancelled"):
                continue

            lines = rec.line_ids

            # Xử lý xong TẤT CẢ dòng → chờ Sales kiểm tra và tạo báo giá.
            if lines and all(line._is_resolved() for line in lines):
                status = "confirmed"

            # KTV ĐÃ bắt đầu xử lý nhưng chưa xong hết → "Đang xử lý". Coi là đã
            # bắt đầu khi: đã bấm "Nhận xử lý" (status đang processing/
            # confirmed cũ), HOẶC ít nhất 1 dòng đã chọn Sản phẩm / đánh dấu không
            # khả thi. (Hàng gia công cần cả Product + BOM mới coi là "xong", nên
            # riêng việc chọn Product đã tính là đang xử lý.)
            elif rec.status in ("processing", "confirmed") or any(
                    line.resolved_product_id or line.is_infeasible for line in lines):
                status = "processing"

            # new / supplemented: chưa ai đụng tới → GIỮ NGUYÊN.
            else:
                status = rec.status

            if rec.status != status:
                rec.status = status

    def write(self, vals):
        # RBAC: thông tin thương mại/yêu cầu (khách hàng, ngày nhận, hạn) do
        # Sales quản lý — Kỹ thuật nhận RFQ chỉ xử lý phần kỹ thuật, không được
        # đổi các field này (chặn cả qua RPC/import, không chỉ readonly ở view).
        if not self.env.su:
            gated = _SALES_ONLY_HEADER_FIELDS & vals.keys()
            if gated and not _user_is_sales(self.env):
                raise AccessError(_(
                    "Thông tin khách hàng / ngày nhận / hạn yêu cầu do Sales "
                    "quản lý — Kỹ thuật không được chỉnh sửa."))
        return super().write(vals)

    def action_receive(self):
        """Ghi nhận KTV bắt đầu xử lý (Mới / Đã bổ sung → Đang xử lý).

        Gán người tiếp nhận + thời điểm để Sales thấy "ai đang xử lý" và để
        cảnh báo khi người khác mở cùng RFQ. Luồng chính gọi hàm này tự động
        khi KTV bấm ``Xử lý`` trên một dòng gia công."""
        for rec in self:
            if rec.status not in ("new", "supplemented"):
                raise UserError(_(
                    "Chỉ RFQ ở trạng thái 'Mới' hoặc 'Đã bổ sung' mới nhận để xử lý."))
            rec.write({
                "status": "processing",
                "received_by": self.env.user.id,
                "received_date": fields.Datetime.now(),
            })
            rec.message_post(
                body=_("%s đã nhận RFQ để xử lý.") % self.env.user.name)

    def action_open_history(self):
        """Nút "Lịch sử" trên list RFQ (Sales & Kỹ thuật) — mở modal timeline
        chỉ đọc: từ lúc tạo, RFQ đổi trạng thái/field gì, ghi chú nào."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lịch sử %s") % self.name,
            "res_model": "dl.rfq.history.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_cancel(self):
        self.write({
            "status": "cancelled",
        })

    def action_open_return_wizard(self):
        """KTV: mở wizard nhập lý do để trả RFQ về cho Sales bổ sung."""
        self.ensure_one()
        if self.status in ("quoted", "cancelled"):
            raise UserError(_(
                "Không thể trả lại RFQ đã tạo báo giá hoặc đã hủy."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Trả lại RFQ để bổ sung"),
            "res_model": "dl.rfq.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_resubmit(self):
        """Sales: sau khi bổ sung, gửi lại RFQ cho Kỹ thuật xử lý tiếp. Trạng
        thái chuyển sang 'Đã bổ sung'; lần bấm 'Xử lý' tiếp theo sẽ tự tiếp nhận."""
        for rec in self:
            if rec.status != "returned":
                raise UserError(_(
                    "Chỉ RFQ đang ở trạng thái 'Trả lại bổ sung' mới gửi lại được."))
            rec.status = "supplemented"
            rec.message_post(body=_("Sales đã bổ sung và gửi lại RFQ."))

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
    _rec_name = "product_name"
    _order = "id"

    quotation_request_id = fields.Many2one(
        "dl.quotation.request",
        string="Yêu cầu báo giá",
        required=True,
        ondelete="cascade",
    )

    # Loại dòng sản phẩm — quyết định phần form Sales phải nhập (Tạo RFQ, §2-4):
    # trading (thương mại, có sẵn trong hệ thống, không qua BOM) vs manufactured
    # (gia công, Kỹ thuật xử lý qua BOM). Dùng chung key với product.product's
    # product_kind để domain resolved_product_id/reference_product_id đơn giản.
    product_type = fields.Selection(
        [
            ("manufactured", "Sản phẩm gia công"),
            ("trading", "Sản phẩm thương mại"),
        ],
        string="Loại sản phẩm",
        required=True,
        default="manufactured",
    )

    product_name = fields.Char(
        string="Tên sản phẩm",
    )

    product_category_id = fields.Many2one(
        "product.category",
        string="Nhóm sản phẩm",
        # Khách đặt THÀNH PHẨM — chỉ nhóm nhánh Thành phẩm, loại nhóm gốc
        # container (đồng bộ selectable_category_ids, chặn cả cell tree
        # không khai domain).
        domain=[("dl_branch", "=", "finished"), ("parent_id", "!=", False)],
    )

    # Sales có thể không biết chính xác Product khi RFQ là hàng gia công — field
    # này chỉ mang tính THAM KHẢO, khác resolved_product_id (quyết định chính
    # thức của Kỹ thuật, RBAC-gated bên dưới).
    # Chỉ SP GIA CÔNG (manufactured) — "sản phẩm đã từng gia công" theo đúng
    # nghĩa Sales tham khảo; BTP (material_processed) là cấu phần BOM, không
    # phải hàng tham khảo cho khách.
    reference_product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm tham khảo",
        domain=[("product_kind", "=", "manufactured"),
                ("dlm_lifecycle_state", "=", "active")],
        help="Chỉ mang tính tham khảo nếu Sales biết sản phẩm tương tự đã từng "
             "gia công — Kỹ thuật sẽ xác nhận sản phẩm chính thức sau.",
    )

    quantity = fields.Float(
        string="Số lượng",
        required=True,
        default=1.0,
    )

    dimension_note = fields.Text(
        string="Kích thước / Yêu cầu",
    )

    # Ảnh (nhiều) + file đính kèm cho dòng gia công (§ màn Tạo RFQ). Ảnh dùng
    # model con để hiển thị thumbnail; file dùng ir.attachment (many2many_binary).
    image_ids = fields.One2many(
        "dl.quotation.request.line.image",
        "line_id",
        string="Thư viện ảnh",
    )
    image_count = fields.Integer(
        string="Số ảnh", compute="_compute_image_count")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "dl_rfq_line_ir_attachment_rel",
        "line_id",
        "attachment_id",
        string="File đính kèm",
    )

    @api.depends("image_ids")
    def _compute_image_count(self):
        for rec in self:
            rec.image_count = len(rec.image_ids)

    # § Tạo RFQ (1d + 2b): Ảnh & file đính kèm gộp chung vào attachment_ids
    # (many2many_binary). preview_image = ảnh đầu tiên trong file đính kèm — dùng
    # để hiển thị THUMBNAIL ở list thay vì hiện số lượng.
    preview_image = fields.Image(
        string="Ảnh xem trước", compute="_compute_preview_image", attachment=False)

    @api.depends("attachment_ids")
    def _compute_preview_image(self):
        for rec in self:
            img = rec.attachment_ids.filtered(
                lambda a: a.mimetype and a.mimetype.startswith("image/"))[:1]
            rec.preview_image = img.datas if img else False

    resolved_product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm xác định",
    )

    # SP hợp lệ để CHỌN khi resolve (gia công): lọc theo Nhóm SP của dòng RFQ
    # (KHÔNG lọc theo trạng thái vòng đời — chọn được cả draft lẫn active).
    # Domain của resolved_product_id ở form Kỹ thuật (view) trỏ vào field này.
    resolvable_product_ids = fields.Many2many(
        "product.product", compute="_compute_resolvable_product_ids",
        string="SP hợp lệ để chọn")

    @api.depends("product_category_id")
    def _compute_resolvable_product_ids(self):
        Product = self.env["product.product"]
        for rec in self:
            domain = [
                ("product_kind", "in", ("manufactured", "material_processed")),
            ]
            if rec.product_category_id:
                domain.append(("categ_id", "child_of", rec.product_category_id.id))
            domain.extend([
                "|",
                ("is_rfq_provisional", "=", False),
                ("rfq_source_line_id", "=", rec.id),
            ])
            rec.resolvable_product_ids = Product.search(domain)

    # § Tạo RFQ (1a): danh sách Nhóm SP cho Sales chọn = nhánh THÀNH PHẨM
    # (dl_branch='finished' — khách đặt hàng thành phẩm, không đặt vật tư/BTP).
    # Nhánh suy từ cây danh mục nên tự loại luôn nhóm hệ thống Odoo
    # (All/Internal/Expense đều là 'other'). Lúc tạo RFQ sản phẩm chưa tồn tại
    # nên KHÔNG lọc theo SP (tránh danh sách rỗng "No records").
    selectable_category_ids = fields.Many2many(
        "product.category", compute="_compute_selectable_category_ids",
        string="Nhóm SP chọn được")

    @api.depends_context("uid")
    def _compute_selectable_category_ids(self):
        # parent_id != False: loại nhóm GỐC "Thành phẩm" (container của cây,
        # không phải nhóm sản phẩm thật để Sales chọn).
        cats = self.env["product.category"].search(
            [("dl_branch", "=", "finished"), ("parent_id", "!=", False)])
        for rec in self:
            rec.selectable_category_ids = cats

    # § Tạo RFQ (1b): SP tham khảo lọc theo Nhóm SP đã chọn của dòng (chỉ SP gia
    # công đang active). Domain của reference_product_id ở view trỏ vào field này.
    reference_product_ids = fields.Many2many(
        "product.product", compute="_compute_reference_product_ids",
        string="SP tham khảo hợp lệ")

    @api.depends("product_category_id")
    def _compute_reference_product_ids(self):
        Product = self.env["product.product"]
        for rec in self:
            # Chỉ SP GIA CÔNG đang active (khớp domain reference_product_id) —
            # không lẫn BTP/vật tư vào danh sách tham khảo của Sales.
            domain = [
                ("product_kind", "=", "manufactured"),
                ("dlm_lifecycle_state", "=", "active"),
            ]
            if rec.product_category_id:
                domain.append(("categ_id", "child_of", rec.product_category_id.id))
            rec.reference_product_ids = Product.search(domain)

    # Màn "Nhận RFQ" (Kỹ thuật) — BOM cụ thể được chọn/tạo để sản xuất
    # resolved_product_id. Không áp dụng cho dòng thương mại (không qua BOM).
    resolved_bom_id = fields.Many2one(
        "dl.bom",
        string="BOM tham chiếu",
        help="BOM Kỹ thuật đã chọn hoặc tạo mới khi xử lý RFQ — dùng để sản xuất "
             "sản phẩm xác định. Chỉ áp dụng cho dòng gia công.",
    )

    # Hiển thị đơn giá tham khảo khi Sales chọn thẳng Product cho dòng "Sản
    # phẩm thương mại" (§3 — không qua BOM). Trước dùng purchase_cost (đã bị
    # đồng nghiệp bỏ ở dl_product, xem product_views.xml) — đổi sang list_price
    # (Giá bán, field chuẩn Odoo) theo đúng field mới đang dùng cho trading.
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        related="resolved_product_id.currency_id",
        readonly=True,
    )

    # list_price là Float (digits="Product Price"), không phải Monetary — field
    # liên kết phải cùng kiểu. currency_id vẫn giữ để hiển thị widget="monetary"
    # trên view (ký hiệu tiền tệ), theo đúng cách dl_product tự hiển thị list_price.
    product_price = fields.Float(
        string="Đơn giá",
        related="resolved_product_id.list_price",
        digits="Product Price",
        readonly=True,
    )

    # Thành tiền cho dòng thương mại (đơn giá × số lượng) — hiển thị ở bảng
    # thương mại màn Tạo RFQ.
    price_subtotal = fields.Float(
        string="Thành tiền",
        compute="_compute_price_subtotal",
        digits="Product Price",
        readonly=True,
    )

    @api.depends("product_price", "quantity")
    def _compute_price_subtotal(self):
        for rec in self:
            rec.price_subtotal = (rec.product_price or 0.0) * (rec.quantity or 0.0)

    is_infeasible = fields.Boolean(
        string="Không khả thi",
        default=False,
    )

    infeasible_reason = fields.Text(
        string="Lý do không khả thi",
    )

    technical_status = fields.Selection(
        [
            ("pending", "Chưa xử lý"),
            ("processing", "Đang xử lý"),
            ("done", "Đã xử lý"),
            ("infeasible", "Không khả thi"),
            ("not_required", "Không cần Kỹ thuật"),
        ],
        string="Trạng thái kỹ thuật",
        compute="_compute_technical_status",
    )

    @api.depends(
        "product_type",
        "resolved_product_id",
        "resolved_bom_id",
        "is_infeasible",
    )
    def _compute_technical_status(self):
        for rec in self:
            if rec.product_type == "trading":
                rec.technical_status = "not_required"
            elif rec.is_infeasible:
                rec.technical_status = "infeasible"
            elif rec.resolved_product_id and rec.resolved_bom_id:
                rec.technical_status = "done"
            elif rec.resolved_product_id or rec.resolved_bom_id:
                rec.technical_status = "processing"
            else:
                rec.technical_status = "pending"

    # Trạng thái RFQ cha — để view khóa các field kết quả khi RFQ chưa được
    # nhận xử lý ("Mới"/"Đã bổ sung"). KTV mở xem tự do, phải bấm "Nhận xử lý"
    # (→ Đang xử lý) mới thao tác được — xem quotation_request_views.xml.
    request_status = fields.Selection(
        related="quotation_request_id.status",
        string="Trạng thái RFQ",
        store=False,
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

    def _is_resolved(self):
        """Dòng được coi là đã xử lý xong khi: không khả thi, HOẶC đã có sản
        phẩm xác định (thương mại không cần BOM; gia công còn phải có thêm
        BOM tham chiếu — §3 màn Nhận RFQ)."""
        self.ensure_one()
        if self.is_infeasible:
            return True
        if not self.resolved_product_id:
            return False
        if self.product_type == "trading":
            return True
        return bool(self.resolved_bom_id)

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(
                    _("Số lượng phải lớn hơn 0.")
                )

    @api.constrains("product_type", "resolved_bom_id", "resolved_product_id")
    def _check_resolved_bom(self):
        for rec in self:
            if not rec.resolved_bom_id:
                continue
            if rec.product_type == "trading":
                raise ValidationError(
                    _("Sản phẩm thương mại không cần BOM tham chiếu.")
                )
            if rec.resolved_product_id and rec.resolved_bom_id.product_id != rec.resolved_product_id:
                raise ValidationError(
                    _("BOM tham chiếu phải thuộc đúng Sản phẩm xác định.")
                )
            if rec.resolved_bom_id.status not in ("confirmed", "locked"):
                raise ValidationError(
                    _("BOM tham chiếu phải ở trạng thái Đã xác nhận hoặc Đã khóa.")
                )

    @api.constrains("product_type", "product_name", "resolved_product_id")
    def _check_product_type_required(self):
        for rec in self:
            if rec.product_type == "trading":
                if not rec.resolved_product_id:
                    raise ValidationError(
                        _("Vui lòng chọn Sản phẩm cho dòng Sản phẩm thương mại.")
                    )
            elif not rec.product_name:
                raise ValidationError(
                    _("Vui lòng nhập Tên sản phẩm cho dòng Sản phẩm gia công.")
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
            # Hàng thương mại không qua BOM (§3) — chỉ bắt buộc BOM cho gia công.
            if rec.resolved_product_id and rec.product_type != "trading":
                bom_count = self.env["dl.bom"].search_count([
                    ("product_id", "=", rec.resolved_product_id.id),
                    ("status", "in", ("confirmed", "locked")),
                ])

                if not bom_count:
                    raise ValidationError(
                        _("Sản phẩm phải có BOM ở trạng thái Đã xác nhận hoặc Đã khóa.")
                    )

    def _stamp_attachments(self):
        """Widget many2many_binary tạo ir.attachment với res_id=0 (file được
        upload trước khi dòng có id). Attachment res_id=0 chỉ NGƯỜI TẠO + admin
        đọc được (cơ chế lọc của ir.attachment) ⇒ user khác mở RFQ có đính kèm sẽ
        bị AccessError. Gắn res_model/res_id về đúng dòng RFQ để: ai đọc được dòng
        thì đọc được file (Sales tạo → Kỹ thuật/CEO/TrKD xem được)."""
        for rec in self:
            orphan = rec.attachment_ids.filtered(lambda a: not a.res_id)
            if orphan:
                orphan.sudo().write({"res_model": rec._name, "res_id": rec.id})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("quotation_request_id")._recompute_status_from_lines()
        records._stamp_attachments()
        return records

    def write(self, vals):
        gated = _TECH_ONLY_LINE_FIELDS & vals.keys()
        if not self.env.su and gated:
            user = self.env.user
            is_tech = (user.has_group('dl_base.dl_group_tech')
                       or user.has_group('dl_base.dl_group_admin'))
            if not is_tech:
                # Ngoại lệ: dòng "Sản phẩm thương mại" không qua Kỹ thuật (§3)
                # — Sales được tự chọn thẳng resolved_product_id. is_infeasible/
                # infeasible_reason vẫn luôn là quyết định của Kỹ thuật.
                new_type = vals.get('product_type')
                is_trading_only = gated == {'resolved_product_id'} and not self.filtered(
                    lambda l: (new_type or l.product_type) != 'trading'
                )
                if not is_trading_only:
                    raise AccessError(_(
                        'Chỉ Kỹ thuật hoặc Admin được quyết định "Sản phẩm xác định" '
                        '/ "Không khả thi" — đây là đánh giá kỹ thuật.'))

        # Chiều ngược lại: thông tin yêu cầu (tên/nhóm/SL/mô tả/đính kèm) do Sales
        # sở hữu — Kỹ thuật (không kiêm Sales) không được sửa nội dung yêu cầu.
        sales_gated = _SALES_ONLY_LINE_FIELDS & vals.keys()
        if not self.env.su and sales_gated and not _user_is_sales(self.env):
            raise AccessError(_(
                'Thông tin yêu cầu (tên / nhóm SP / số lượng / mô tả / đính kèm) '
                'do Sales quản lý — Kỹ thuật không được chỉnh sửa.'))

        res = super().write(vals)

        if "attachment_ids" in vals:
            self._stamp_attachments()

        if {"resolved_product_id", "resolved_bom_id", "is_infeasible"} & set(vals.keys()):
            self.mapped("quotation_request_id")._recompute_status_from_lines()

        return res

    def unlink(self):
        provisional_boms = self.env["dl.bom"].sudo().search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "in", self.ids),
        ])
        provisional_products = self.env["product.product"].sudo().search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "in", self.ids),
        ])
        requests = self.mapped("quotation_request_id")
        res = super().unlink()
        provisional_boms._cleanup_unused_rfq_provisional()
        provisional_products._cleanup_unused_rfq_provisional()
        requests._recompute_status_from_lines()
        return res

    def _cleanup_rfq_provisional_records(
            self, keep_product_ids=None, keep_bom_ids=None):
        """Clean unused temporary master data created by these RFQ lines."""
        line_ids = self.ids
        if not line_ids:
            return {"boms": 0, "products": 0}
        keep_product_ids = set(keep_product_ids or [])
        keep_bom_ids = set(keep_bom_ids or [])
        boms = self.env["dl.bom"].sudo().search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "in", line_ids),
            ("id", "not in", list(keep_bom_ids)),
        ])
        deleted_boms = boms._cleanup_unused_rfq_provisional()
        products = self.env["product.product"].sudo().with_context(
            active_test=False).search([
                ("is_rfq_provisional", "=", True),
                ("rfq_source_line_id", "in", line_ids),
                ("id", "not in", list(keep_product_ids)),
            ])
        deleted_products = products._cleanup_unused_rfq_provisional()
        return {"boms": deleted_boms, "products": deleted_products}

    @api.model
    def _cron_cleanup_rfq_provisional_records(self):
        """Daily fail-safe cleanup for abandoned RFQ provisional records."""
        raw_days = self.env["ir.config_parameter"].sudo().get_param(
            "dl_technical.rfq_provisional_cleanup_days", 7)
        try:
            days = max(int(raw_days), 1)
        except (TypeError, ValueError):
            days = 7
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        boms = self.env["dl.bom"].sudo().search([
            ("is_rfq_provisional", "=", True),
            ("write_date", "<", cutoff),
        ], limit=500)
        boms._cleanup_unused_rfq_provisional()
        products = self.env["product.product"].sudo().with_context(
            active_test=False).search([
                ("is_rfq_provisional", "=", True),
                ("write_date", "<", cutoff),
            ], limit=500)
        products._cleanup_unused_rfq_provisional()
        return True

    def action_open_resolve_wizard(self):
        """Mở workspace Product + BOM và tự tiếp nhận RFQ khi cần.

        Với RFQ Mới/Đã bổ sung, chính thao tác Xử lý là ý định nhận việc rõ
        ràng nên hệ thống ghi người + thời điểm trước khi mở workspace. RFQ đã
        Đang xử lý/Đã xử lý xong chỉ được mở lại, không đổi người phụ trách.
        """
        self.ensure_one()
        request = self.quotation_request_id
        if request.status in ("new", "supplemented"):
            request.action_receive()
        if request.status not in ("processing", "confirmed"):
            raise UserError(_(
                "RFQ ở trạng thái hiện tại không thể xử lý kỹ thuật."))
        wizard = self.env["dl.rfq.resolve.wizard"].with_context(
            default_rfq_line_id=self.id,
        ).create({})
        view = self.env.ref("dl_technical.view_dl_rfq_resolve_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Xử lý RFQ — %s") % (self.product_name or self.resolved_product_id.display_name),
            "res_model": "dl.rfq.resolve.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        }


class DlQuotationRequestLineImage(models.Model):
    _name = "dl.quotation.request.line.image"
    _description = "Ảnh dòng yêu cầu báo giá"
    _order = "sequence, id"

    line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Thứ tự", default=10)
    name = fields.Char(string="Mô tả ảnh")
    image = fields.Image(string="Ảnh", required=True, max_width=1920, max_height=1920)
