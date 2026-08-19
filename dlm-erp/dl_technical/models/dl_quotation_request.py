import base64
import re

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.image import image_process

# Field-level RBAC (giống dl.material): chỉ Kỹ thuật/Admin được quyết định
# "sản phẩm xác định" / "không khả thi" — đây là đánh giá kỹ thuật, Sales chỉ
# được nhập yêu cầu (product_name/product_category_id/quantity/dimension_note).
_TECH_ONLY_LINE_FIELDS = {'resolved_product_id', 'resolved_bom_id', 'is_infeasible', 'infeasible_reason'}

# Chiều ngược lại: thông tin YÊU CẦU do Sales sở hữu. Kỹ thuật khi nhận RFQ chỉ
# xử lý phần kỹ thuật (Product/BOM/vật tư/bản vẽ nằm ở model dl.product/dl.bom),
# KHÔNG được sửa nội dung yêu cầu của dòng...
_SALES_ONLY_LINE_FIELDS = {
    'product_type', 'product_name', 'product_category_id',
    'reference_product_id', 'quantity', 'uom_id', 'dimension_note',
    'attachment_ids', 'param_ids',
}
# ...cũng như thông tin thương mại ở header (khách hàng, ngày nhận, hạn yêu cầu).
_SALES_ONLY_HEADER_FIELDS = {'customer_id', 'requested_date', 'deadline'}

# Chuẩn hóa văn bản do người dùng gõ: gộp khoảng trắng lặp, cắt hai đầu.
# Cùng cách làm với dl_partner/models/res_partner.py.
_MULTI_SPACE_RE = re.compile(r'\s+')
# Độ dài tối thiểu của Tên sản phẩm gia công. Chỉ chặn được tên một ký tự kiểu
# 'a' — không phải bộ lọc rác đầy đủ ('..' vẫn qua), mục đích là bắt cái sai rõ
# ràng nhất khi nhập vội. Khớp _MIN_NAME_LEN của màn Khách hàng cho cùng chuẩn.
_MIN_PRODUCT_NAME_LEN = 2

# ── Bộ dò khớp SP "đã từng gia công" (§3.6, Đợt 2) ──────────────────────────
# Điểm số theo bảng §3.6 (LỚP 2 — sản phẩm/instance cụ thể). LỚP 1 (họ có
# template tham số) thuộc Đợt 4 nên CHƯA tính ở đây: khi bộ sinh instance +
# param_signature tồn tại, thêm tín hiệu +45 (khớp bộ tham số) và +50 (thuộc họ
# template) vào đúng chỗ ghi chú trong _dlm_suggest_candidates.
_MATCH_SCORE_REFERENCE = 50     # Sales đã chọn reference_product_id (mạnh nhất)
_MATCH_SCORE_NAME_EXACT = 40    # tên chuẩn hoá TRÙNG HỆT
_MATCH_SCORE_NAME_SIMILAR = 25  # tên GẦN GIỐNG (thiếu dấu / hậu tố...)
_MATCH_SCORE_SAME_CATEGORY = 10  # cùng nhóm sản phẩm
_MATCH_SCORE_SAME_CUSTOMER = 10  # đã từng xử lý cho cùng khách hàng
# So SỐ VỚI SỐ (§3.6, điều kiện tiên quyết S05): kích thước trích từ mô tả Sales
# khớp thuộc tính kỹ thuật (D/R/C) của SP. Đây là lý do các field dlm_dim_* tồn
# tại — dấu vân kích thước là tín hiệu bổ trợ mạnh, nhưng KHÔNG tự đủ ngưỡng tự
# chọn một mình (hai SP khác hẳn nhau vẫn có thể trùng khổ 1200x800), phải cộng
# với tên/nhóm/tham khảo mới lên auto.
_MATCH_SCORE_DIM_MATCH = 30     # khổ D×R (và C nếu có) khớp thuộc tính kỹ thuật SP
_MATCH_PENALTY_OBSOLETE = -60   # SP đang Ngừng sử dụng — vẫn hiện nhưng đội sổ
# LỚP 1 (§3.6) — họ sản phẩm có mẫu tham số. Nhóm có mẫu thì SẢN PHẨM DÙNG CHUNG
# của mẫu là đích đến đúng cho MỌI cỡ trong họ (không đẻ mã mới theo từng cỡ);
# nếu đã từng sinh định mức đúng bộ tham số này thì gần như chắc chắn là nó.
_MATCH_SCORE_TEMPLATE_FAMILY = 50   # SP dùng chung của mẫu tham số cùng nhóm
_MATCH_SCORE_PARAM_SIGNATURE = 45   # đã từng sinh định mức đúng bộ tham số này
# Ngưỡng phân loại (§3.6): ≥60 = đề xuất tự động (auto-điền), 30–59 = gợi ý
# (hiện thẻ "Có phải cái này?"), <30 = không gợi ý.
_MATCH_THRESHOLD_AUTO = 60
_MATCH_THRESHOLD_SUGGEST = 30

# Dung sai khớp kích thước (mm): số đo cùng khổ ghi lệch vài mm do làm tròn /
# gõ tay vẫn tính là một; lớn hơn coi như khác cỡ.
_DIM_MATCH_TOLERANCE = 2.0


def _user_is_sales(env):
    """Sales sở hữu thông tin yêu cầu = BA / Trưởng phòng KD / Admin."""
    user = env.user
    return (user.has_group('dl_base.dl_group_ba')
            or user.has_group('dl_base.dl_group_sales_manager')
            or user.has_group('dl_base.dl_group_admin'))


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _dlm_image_thumb(self, size=(480, 480)):
        """Thumbnail base64 của ảnh đính kèm (thu về ~480px), rỗng nếu không phải ảnh hoặc ảnh hỏng."""
        # Song sinh của dl_inventory `_dlm_evidence_thumb` (màn Kiểm hàng QC): cùng
        # bài toán "many2many_binary chỉ bày thẻ file, không xem được ảnh". Hai
        # module không có tổ tiên nào đã _inherit ir.attachment nên tạm giữ hai
        # bản; gộp về dl_base khi có lý do đụng cả hai.
        self.ensure_one()
        if not (self.mimetype or "").startswith("image/"):
            return ""
        try:
            # sudo: ảnh vừa upload còn res_id=0. Dùng `raw` (bytes thô), không phải `datas`.
            raw = self.sudo().raw
            if not raw:
                return ""
            thumb = image_process(raw, size=size, output_format="JPEG")
            return base64.b64encode(thumb or b"").decode()
        except Exception:  # noqa: BLE001 — ảnh hỏng chỉ mất tấm đó
            return ""

    def _dlm_file_icon(self):
        """Icon Font Awesome theo loại file — dùng cho thẻ file không phải ảnh."""
        self.ensure_one()
        mt = (self.mimetype or "").lower()
        name = (self.name or "").lower()
        if "pdf" in mt or name.endswith(".pdf"):
            return "fa-file-pdf-o"
        if "word" in mt or name.endswith((".doc", ".docx")):
            return "fa-file-word-o"
        if ("excel" in mt or "spreadsheet" in mt
                or name.endswith((".xls", ".xlsx", ".csv"))):
            return "fa-file-excel-o"
        if ("powerpoint" in mt or "presentation" in mt
                or name.endswith((".ppt", ".pptx"))):
            return "fa-file-powerpoint-o"
        if ("zip" in mt or "compressed" in mt
                or name.endswith((".zip", ".rar", ".7z"))):
            return "fa-file-archive-o"
        if name.endswith((".dwg", ".dxf")):
            return "fa-file-code-o"
        return "fa-file-o"


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

    # Loại RFQ: một RFQ chỉ đi MỘT vòng đời. 
    request_type = fields.Selection(
        [
            ("manufactured", "Sản phẩm gia công"),
            ("trading", "Sản phẩm thương mại"),
        ],
        string="Loại yêu cầu",
        required=True,
        default="manufactured",
        tracking=True,
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
            ("confirmed", "Chờ tạo báo giá"),
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

    @api.depends("received_by", "received_date", "status")
    def _compute_received_info(self):
        for rec in self:
            # Banner "đang do X xử lý" chỉ có nghĩa khi RFQ CÒN ĐANG XỬ LÝ — RFQ
            # đã đóng (đã tạo báo giá / đã hủy) hoặc đang ở phía Sales (trả lại
            # bổ sung) thì thôi nhắc, tránh treo tên KTV mãi.
            rec.received_by_other = (
                bool(rec.received_by)
                and rec.received_by != self.env.user
                and rec.status in ("processing", "supplemented", "confirmed"))
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
    supplement_count = fields.Integer(
        string="Dòng chờ bổ sung",
        compute="_compute_supplement_count",
        store=True,
    )
    # Số dòng Sales ĐÃ bổ sung, sẵn sàng gửi lại Kỹ thuật (điều khiển hiển thị
    # nút "Gửi lại"): nút chỉ hiện khi có ít nhất 1 dòng như vậy, không phụ
    # thuộc RFQ đã ở "Trả lại bổ sung" hay chưa (hợp nhất luồng partial/full).
    supplement_ready_count = fields.Integer(
        string="Dòng đã bổ sung chờ gửi lại",
        compute="_compute_supplement_count",
        store=True,
    )

    @api.depends("line_ids.supplement_note", "line_ids.supplement_done")
    def _compute_supplement_count(self):
        for rec in self:
            waiting = rec.line_ids.filtered(
                lambda l: l.supplement_note and not l.supplement_done)
            ready = rec.line_ids.filtered(
                lambda l: l.supplement_note and l.supplement_done)
            rec.supplement_count = len(waiting)
            rec.supplement_ready_count = len(ready)

    # Tín hiệu "không khả thi" cho Sales — đối xứng với supplement_count:
    # Sales cần biết SỚM (chủ động trao đổi lại với khách) thay vì chỉ phát
    # hiện khi RFQ sang "Đã xử lý xong". all_infeasible = toàn bộ dòng đều
    # không khả thi → không có gì để báo giá (chặn "Đánh dấu đã tạo báo giá").
    infeasible_count = fields.Integer(
        string="Dòng không khả thi",
        compute="_compute_infeasible_stats",
    )
    all_infeasible = fields.Boolean(
        string="Toàn bộ không khả thi",
        compute="_compute_infeasible_stats",
    )

    @api.depends("line_ids", "line_ids.is_infeasible")
    def _compute_infeasible_stats(self):
        for rec in self:
            infeasible = rec.line_ids.filtered(lambda l: l.is_infeasible)
            rec.infeasible_count = len(infeasible)
            rec.all_infeasible = bool(rec.line_ids) and len(infeasible) == len(rec.line_ids)

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
    # Bản GỌN của tiến độ cho list Sales: "2/4" (đã xử lý / tổng dòng gia công).
    # Sales nắm được RFQ nhiều dòng đã xong tới đâu ngay trên list, KHÔNG phải mở
    # chi tiết. RỖNG khi RFQ không có dòng gia công (chỉ hàng thương mại) — tránh
    # nhiễu như cột "Tiến độ kỹ thuật" câu-dài (technical_progress_label) đã gỡ
    # khỏi list Sales; câu dài vẫn giữ cho list Kỹ thuật.
    tech_progress_short = fields.Char(
        string="Tiến độ kỹ thuật",
        compute="_compute_technical_progress",
    )
    tech_progress_complete = fields.Boolean(
        string="Kỹ thuật đã xử lý xong",
        compute="_compute_technical_progress",
    )

    @api.depends(
        "line_ids.product_type",
        "line_ids.resolved_product_id",
        "line_ids.resolved_bom_id",
        "line_ids.is_infeasible",
        "line_ids.supplement_note",
        "line_ids.supplement_done",
        "line_ids.needs_review",
    )
    def _compute_technical_progress(self):
        for rec in self:
            technical_lines = rec.line_ids.filtered(
                lambda line: line.product_type == "manufactured")
            total = len(technical_lines)
            # Dòng "Cần xem lại" (Sales sửa yêu cầu sau khi xác định) không tính
            # là đã xong — đồng bộ với _is_resolved.
            done = len(technical_lines.filtered(
                lambda line: line.is_infeasible
                or bool(line.resolved_product_id and line.resolved_bom_id
                        and not line.needs_review)))

            rec.technical_total_line_count = total
            rec.technical_done_line_count = done
            rec.technical_progress_percent = (done * 100.0 / total) if total else 0.0

            if total:
                label = _("Đã xử lý %(done)s/%(total)s dòng gia công",
                          done=done, total=total)
                # "Đã xử lý" gồm cả dòng không khả thi (KTV đã có kết luận nhưng
                # KHÔNG báo giá được) — tách rõ để không hiểu nhầm là làm được.
                infeasible = len(technical_lines.filtered(lambda l: l.is_infeasible))
                if infeasible:
                    label += _(" (%(n)s không khả thi)", n=infeasible)
            else:
                label = _("Không có dòng gia công cần xử lý")

            # Chỉ đếm dòng còn CHỜ Sales bổ sung (đã bổ sung nhưng chưa gửi lại
            # không tính là "cần bổ sung" nữa).
            supplement = len(rec.line_ids.filtered(
                lambda l: l.supplement_note and not l.supplement_done))
            if supplement:
                label += _(" · %(n)s cần bổ sung", n=supplement)

            rec.technical_progress_label = label
            # Bản gọn "2/4" cho list Sales — rỗng khi không có dòng gia công.
            rec.tech_progress_short = ("%s/%s" % (done, total)) if total else False
            rec.tech_progress_complete = bool(total) and done >= total

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

    # Ưu tiên hiển thị trên danh sách Sales ("Quản lý RFQ"): RFQ đang chờ CHÍNH
    # SALES ra tay (tạo báo giá / bổ sung) nổi lên đầu, kế đến là RFQ đang ở Kỹ
    # thuật (Sales chỉ theo dõi), cuối cùng là RFQ đã đóng (đã tạo báo giá / đã
    # hủy). Đây là "hàng đợi việc" nên việc cần làm phải nằm trên, không để 9
    # dòng đã xong che mất 2 dòng cần xử lý. store=True để tree default_order sắp
    # bằng SQL. CHỈ áp cho list Sales — list Kỹ thuật ("RFQ cần xử lý") giữ thứ
    # tự riêng (xem view_dl_quotation_request_tree_my), vì "việc của tôi" của KTV
    # khác Sales.
    _SALES_PRIORITY_BY_STATUS = {
        "returned": 10,       # bóng ở Sales — cần bổ sung để gửi lại Kỹ thuật
        "confirmed": 10,      # bóng ở Sales — cần tạo báo giá
        "new": 20,            # đang/chờ ở Kỹ thuật — Sales theo dõi
        "processing": 20,
        "supplemented": 20,
        "quoted": 30,         # đã đóng
        "cancelled": 30,
    }

    sales_priority = fields.Integer(
        string="Ưu tiên xử lý (Sales)",
        compute="_compute_sales_priority",
        store=True,
    )

    @api.depends("status")
    def _compute_sales_priority(self):
        for rec in self:
            rec.sales_priority = self._SALES_PRIORITY_BY_STATUS.get(rec.status, 20)

    # Đối xứng sales_priority nhưng theo GÓC KỸ THUẬT cho hàng đợi "RFQ cần xử
    # lý": RFQ đang cần KTV ra tay (chưa nhận / đang xử lý / Sales vừa gửi lại)
    # nổi đầu; RFQ bóng đang ở Sales (trả lại / chờ báo giá) và RFQ đã đóng xuống
    # dưới. Lưu ý confirmed với KTV là ĐÃ XONG (không phải việc cần làm) — ngược
    # với sales_priority. store=True để tree default_order sắp bằng SQL.
    _TECH_PRIORITY_BY_STATUS = {
        "new": 10,           # chờ Kỹ thuật nhận
        "processing": 10,    # Kỹ thuật đang làm
        "supplemented": 10,  # Sales gửi lại — chờ Kỹ thuật làm tiếp
        "returned": 20,      # bóng ở Sales (chờ bổ sung)
        "confirmed": 25,     # Kỹ thuật xong, chờ Sales báo giá
        "quoted": 30,        # đã đóng
        "cancelled": 30,
    }

    tech_priority = fields.Integer(
        string="Ưu tiên xử lý (Kỹ thuật)",
        compute="_compute_tech_priority",
        store=True,
    )

    @api.depends("status")
    def _compute_tech_priority(self):
        for rec in self:
            rec.tech_priority = self._TECH_PRIORITY_BY_STATUS.get(rec.status, 10)

    # Mốc "vào hàng đợi Kỹ thuật": đã nhận thì tính từ lúc nhận, chưa nhận thì từ
    # lúc nhận yêu cầu. Dùng làm khóa sort PHỤ (chờ lâu nhất lên đầu trong cùng
    # nhóm ưu tiên). Stored được vì CHỈ phụ thuộc field stored — khác
    # tech_waiting_days (phụ thuộc now(), không stored, không sort SQL được).
    tech_queue_since = fields.Datetime(
        string="Vào hàng đợi Kỹ thuật lúc",
        compute="_compute_tech_queue_since",
        store=True,
    )

    @api.depends("status", "received_date", "requested_date")
    def _compute_tech_queue_since(self):
        for rec in self:
            rec.tech_queue_since = rec.received_date or rec.requested_date

    # Giai đoạn theo GÓC NHÌN KỸ THUẬT — gộp 7 trạng thái vòng đời (phần lớn do
    # Sales sở hữu) về đúng các mốc KTV quan tâm, dùng cho badge list "RFQ cần
    # xử lý" thay cột status 7-state (đỡ rối, đúng phần việc). Chỉ để HIỂN THỊ:
    # không lưu, không lọc — thanh chip vẫn lọc trên `status` thật.
    #   Mới / Đã bổ sung   → Chưa nhận (chờ KTV bắt đầu / tiếp tục)
    #     NGOẠI LỆ: RFQ đã có người tiếp nhận (bị trả lại bổ sung rồi Sales gửi
    #     lại) vẫn thuộc KTV đã nhận trước đó → "Đang xử lý", không lùi "Chưa
    #     nhận" (tránh lệch với cột "Người tiếp nhận" đã có tên).
    #   Đang xử lý         → Đang xử lý
    #   Trả lại bổ sung    → Chờ Sales bổ sung (bóng đang ở Sales)
    #   Đã xử lý xong      → Đã xử lý xong (KTV xong, chờ Sales tạo báo giá)
    #   Đã tạo BG / Đã hủy → Đã đóng (ra khỏi hàng đợi việc của KTV)
    _TECH_STAGE_BY_STATUS = {
        "new": "pending",
        "supplemented": "pending",
        "processing": "processing",
        "returned": "waiting_sales",
        "confirmed": "done",
        "quoted": "closed",
        "cancelled": "closed",
    }

    tech_stage = fields.Selection(
        [
            ("pending", "Chưa nhận"),
            ("processing", "Đang xử lý"),
            ("waiting_sales", "Chờ Sales bổ sung"),
            ("done", "Đã xử lý xong"),
            ("closed", "Đã đóng"),
        ],
        string="Giai đoạn kỹ thuật",
        compute="_compute_tech_stage",
    )

    @api.depends("status", "received_by")
    def _compute_tech_stage(self):
        for rec in self:
            stage = self._TECH_STAGE_BY_STATUS.get(rec.status, "pending")
            # Đã có KTV tiếp nhận từ trước (RFQ từng xử lý rồi bị trả lại bổ
            # sung, nay Sales gửi lại) → giữ "Đang xử lý", không lùi "Chưa nhận".
            if stage == "pending" and rec.received_by:
                stage = "processing"
            rec.tech_stage = stage

    # U3 — RFQ nằm trong hàng đợi Kỹ thuật quá lâu (Chưa nhận/Đang xử lý). Xưởng
    # nhỏ không ai canh hàng đợi ⇒ RFQ dễ "thối"; badge đỏ nhắc KTV ưu tiên. Mốc
    # đếm: đang xử lý → từ lúc tiếp nhận; chưa nhận → từ lúc nhận yêu cầu. Ngưỡng
    # cấu hình qua ir.config_parameter dl_technical.rfq_tech_aging_days (mặc định 3).
    tech_waiting_days = fields.Integer(
        string="Số ngày chờ xử lý", compute="_compute_tech_waiting")
    tech_overdue = fields.Boolean(
        string="Chờ xử lý quá lâu", compute="_compute_tech_waiting")

    @api.depends("status", "received_by", "received_date", "requested_date")
    def _compute_tech_waiting(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "dl_technical.rfq_tech_aging_days", 3)
        try:
            threshold = max(int(raw), 1)
        except (TypeError, ValueError):
            threshold = 3
        now = fields.Datetime.now()
        for rec in self:
            days = 0
            stage = rec.tech_stage
            if stage in ("pending", "processing"):
                anchor = rec.received_date if stage == "processing" else rec.requested_date
                if anchor:
                    days = (now - anchor).days
            rec.tech_waiting_days = days
            rec.tech_overdue = days >= threshold and stage in ("pending", "processing")

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
        string="Sản phẩm tham chiếu",
    )
    resolved_bom_ids = fields.Many2many(
        "dl.bom",
        compute="_compute_resolved_refs",
        string="BOM tham chiếu",
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

    # Phải khai CẢ BA field trỏ cùng quan hệ: Odoo chỉ chạy constrain của đúng
    # tên field được ghi, nên ghi qua manufactured_line_ids/trading_line_ids
    # (đường của form) sẽ lọt nếu chỉ khai line_ids.
    @api.constrains("request_type", "line_ids",
                    "manufactured_line_ids", "trading_line_ids")
    def _check_line_type_matches_header(self):
        """Mọi dòng phải cùng loại với header.

        Header quyết định RFQ đi vòng đời nào; dòng lệch loại là dòng sẽ không
        bao giờ được xử lý (hàng đợi Kỹ thuật lọc theo request_type, form Sales
        chỉ hiện đúng một bảng). Chặn ở đây thay vì tự sửa im lặng: dòng lệch
        loại luôn là dấu hiệu của import/RPC sai, không phải thao tác hợp lệ."""
        for rec in self:
            wrong = rec.line_ids.filtered(
                lambda l: l.product_type != rec.request_type)
            if wrong:
                raise ValidationError(_(
                    "RFQ loại '%(kind)s' không chứa được dòng khác loại "
                    "(%(lines)s). Tách thành RFQ riêng cho từng loại.",
                    kind=dict(self._fields["request_type"].selection)[rec.request_type],
                    lines=", ".join(wrong.mapped("product_name") or ["?"])))

    @api.onchange("request_type")
    def _onchange_request_type(self):
        """Đổi loại lúc TẠO MỚI thì bỏ các dòng đã nhập của loại kia.

        Hai bảng có bộ field khác hẳn nhau nên không chuyển đổi dòng được; để
        lại thì dòng nằm trong bảng đang bị ẩn và chặn Lưu bằng lỗi khó hiểu.
        View khóa request_type sau khi Lưu, nên chỗ này chỉ đụng dòng chưa lưu."""
        if self.request_type == "trading":
            self.manufactured_line_ids = [(5, 0, 0)]
        else:
            self.trading_line_ids = [(5, 0, 0)]

    @api.constrains("line_ids", "status")
    def _check_has_lines(self):
        """RFQ phải có ít nhất một dòng.

        View đã có required chéo trên trading_line_ids/manufactured_line_ids để
        tô đỏ ngay khi nhập, nhưng đó chỉ chặn người bấm trên giao diện: import
        Excel, gọi RPC hay create() từ code vẫn đẻ ra RFQ rỗng — một yêu cầu báo
        giá không có gì để báo giá, Kỹ thuật mở ra không hiểu phải làm gì.

        Ghi chú cũ ở đây nói tránh @api.constrains vì nó bung modal. Lý do đó đã
        hết hiệu lực từ khi lỗi nghiệp vụ chuyển hết sang toast
        (dl_base/static/src/js/error_toast.js).

        Miễn cho RFQ đã hủy: hủy là điểm dừng, không bắt bổ sung dòng ở đó."""
        for rec in self:
            if rec.status == "cancelled":
                continue
            if not rec.line_ids:
                raise ValidationError(_(
                    "Yêu cầu báo giá %s phải có ít nhất một dòng sản phẩm. "
                    "Nếu khách đã rút lại yêu cầu thì bấm Hủy RFQ thay vì bỏ "
                    "hết dòng.") % (rec.name or ""))

    def _recompute_status_from_lines(self):
        for rec in self:

            # quoted/cancelled: đã kết thúc — không tự đổi.
            if rec.status in ("quoted", "cancelled"):
                continue

            lines = rec.line_ids

            # Xử lý xong TẤT CẢ dòng → chờ Sales kiểm tra và tạo báo giá.
            if lines and all(line._is_resolved() for line in lines):
                status = "confirmed"
            else:
                # Chỉ chuyển "returned" khi KTV bị CHẶN hoàn toàn: MỌI dòng chưa
                # xong đều đang chờ Sales bổ sung. Còn dòng làm được thì giữ
                # "processing" — Sales đã có tín hiệu qua activity + chatter +
                # alert "N dòng chờ bổ sung" + filter "Cần bổ sung"; flip sớm
                # khiến worklist KTV rớt "Đang xử lý" trong khi việc vẫn còn.
                unresolved = lines.filtered(lambda l: not l._is_resolved())

                # Bằng chứng "Kỹ thuật đã bắt tay vào việc": có người tiếp nhận,
                # hoặc có dòng đã ra kết quả kỹ thuật. Nhánh này chỉ chạy cho RFQ
                # GIA CÔNG — RFQ thương mại có mọi dòng resolved sẵn nên không
                # bao giờ xuống tới đây (chốt 2026-08-18, một RFQ một vòng đời).
                tech_started = bool(rec.received_by) or any(
                    l.resolved_product_id or l.is_infeasible for l in lines)

                if unresolved and all(l.supplement_note for l in unresolved):
                    status = "returned"

                # KTV ĐÃ bắt đầu xử lý nhưng chưa xong hết → "Đang xử lý".
                elif tech_started or rec.status in ("processing", "returned"):
                    status = "processing"

                # Từng đủ điều kiện tạo báo giá, nay lại có dòng chưa xử lý mà
                # chưa ai đụng vào (Sales xóa hết dòng cũ rồi thêm dòng mới) →
                # trả về hàng đợi Kỹ thuật ở mốc "Chưa nhận", không đứng lại ở
                # "Chờ tạo báo giá" (Sales sẽ tạo báo giá thiếu dòng chưa xử lý).
                elif rec.status == "confirmed":
                    status = "new"

                # new / supplemented: chưa ai đụng tới → GIỮ NGUYÊN.
                else:
                    status = rec.status

            if rec.status != status:
                if status == "returned":
                    parts = []
                    for l in lines.filtered(lambda l: l.supplement_note):
                        parts.append("• %s: %s" % (
                            l.product_name or "", l.supplement_note))
                    rec.return_reason = "\n".join(parts)
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
        # Chốt cứng ở server (không chỉ ẩn nút ở view): không hủy RFQ đã tạo báo
        # giá (còn ràng buộc báo giá) hoặc đã hủy sẵn.
        for rec in self:
            if rec.status in ("quoted", "cancelled"):
                raise UserError(_(
                    "Không thể hủy RFQ đã tạo báo giá hoặc đã hủy."))
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
        """Sales: sau khi bổ sung, gửi lại RFQ cho Kỹ thuật xử lý tiếp.

        Chỉ gửi lại đúng các dòng Sales THỰC SỰ đã bổ sung (supplement_done —
        đặt tự động khi Sales sửa nội dung yêu cầu của dòng đang chờ). Các dòng
        còn chờ mà Sales chưa động tới được GIỮ NGUYÊN cờ để Kỹ thuật vẫn thấy —
        tránh xóa mù khi RFQ nhiều dòng. Nếu còn dòng chưa bổ sung, hệ thống báo
        rõ trong chatter thay vì âm thầm bỏ qua."""
        for rec in self:
            if rec.status in ("quoted", "cancelled"):
                raise UserError(_(
                    "Không thể gửi lại RFQ đã tạo báo giá hoặc đã hủy."))
            flagged = rec.line_ids.filtered(lambda l: l.supplement_note)
            addressed = flagged.filtered(lambda l: l.supplement_done)
            pending = flagged - addressed
            if not addressed:
                raise UserError(_(
                    "Chưa có dòng nào được bổ sung. Hãy sửa thông tin ở các dòng "
                    "đang 'Chờ bổ sung' (bảng bên dưới) rồi mới gửi lại."))
            # Xóa CÂU HỎI bổ sung (supplement_note) nhưng GIỮ cờ supplement_done:
            # dòng vẫn hiện "Đã bổ sung" để KTV biết cần xử lý lại (cờ chỉ mất khi
            # KTV Xác nhận / kết luận / trả lại lần nữa). _recompute_status_from_lines
            # chạy theo (supplement_note đổi) — RFQ 'Trả lại bổ sung' cần đẩy về
            # phía Kỹ thuật nên set 'supplemented' đè lên sau đó.
            was_returned = rec.status == "returned"
            addressed.write({"supplement_note": False})
            if was_returned:
                rec.status = "supplemented"
            if pending:
                rec.message_post(body=_(
                    "Sales đã bổ sung %(done)s dòng và gửi lại RFQ. Còn "
                    "%(pending)s dòng CHƯA bổ sung: %(names)s.",
                    done=len(addressed), pending=len(pending),
                    names=", ".join(pending.mapped("product_name"))))
            else:
                rec.message_post(body=_("Sales đã bổ sung và gửi lại RFQ."))

    def action_mark_quoted(self):
        for rec in self:
            if rec.status != "confirmed":
                raise UserError(
                    _("Chỉ yêu cầu báo giá đã xử lý xong mới được đánh dấu đã tạo báo giá.")
                )
            # Toàn bộ dòng không khả thi vẫn tính là "đã xử lý xong" (KTV đã có
            # kết luận) nhưng không có sản phẩm nào để báo giá.
            if rec.all_infeasible:
                raise UserError(_(
                    "Tất cả dòng đều không khả thi — không có sản phẩm để báo "
                    "giá. Hãy trao đổi lại với khách hàng hoặc Hủy RFQ."))

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

    # Đơn vị tính của thứ khách đặt (bộ / cái / m). Sổ đặt hàng thật của doanh
    # nghiệp đã có cột "ĐV" từ trước khi có ERP — cùng một con số 100 nghĩa là
    # 100 bộ bàn ghế hay 100 mét máng điện là hai đơn hàng khác hẳn nhau.
    # Dùng uom.uom chuẩn Odoo (không phải Selection tự chế) để còn quy đổi được
    # khi nối sang báo giá và kho.
    uom_id = fields.Many2one(
        "uom.uom",
        string="Đơn vị tính",
        required=True,
        default=lambda self: self.env.ref(
            "uom.product_uom_unit", raise_if_not_found=False),
    )

    dimension_note = fields.Text(
        string="Kích thước / Yêu cầu",
    )

    # ── Tham số theo mẫu của nhóm SP ────────────────────────────────────────
    # Nhóm sản phẩm là CHÌA KHOÁ ĐỊNH TUYẾN: nhóm nào có BOM mẫu tham số thì form
    # Sales hiện đúng các ô mẫu ấy hỏi (Dài/Rộng/Cao với cái bàn, Dài/Khổ với
    # máng điện), nhóm nào chưa có mẫu thì chỉ mô tả + bản vẽ như trước.
    #
    # Vì sao KHÔNG làm 3 ô D/R/C cứng: một "bộ bàn ghế" có kích thước bàn + cao
    # ghế + khổ mặt ghế + khổ tựa, còn cái bảng chỉ có 2 chiều và cái máng bán
    # theo mét. Ô cứng thì thừa chỗ này thiếu chỗ kia, mà mỗi lần thêm loại hàng
    # lại phải sửa code. Để mẫu tự khai mình hỏi gì thì thêm loại hàng chỉ là
    # dựng thêm một BOM mẫu — việc của Kỹ thuật, không phải của lập trình.
    # 🔴 Mẫu suy từ KIỂU HÀNG (`reference_product_id`), KHÔNG từ nhóm. Nhóm là
    # trục thương mại và chứa nhiều kết cấu; hỏi "mẫu của nhóm này" không có câu
    # trả lời đơn nhất. Sales chỉ đích danh kiểu hàng thì mẫu mới xác định.
    parametric_template_id = fields.Many2one(
        "dl.bom.template",
        string="Mẫu tham số của kiểu hàng",
        compute="_compute_parametric_template",
    )
    has_parametric_template = fields.Boolean(
        string="Kiểu hàng có mẫu tham số",
        compute="_compute_parametric_template",
    )
    # Kiểu hàng đã có ĐỊNH MỨC CHUẨN hiện hành (Hạng B — cỡ cố định): chọn xong
    # là báo giá được, không hỏi kích thước và không qua Kỹ thuật.
    standard_bom_id = fields.Many2one(
        "dl.bom", string="Định mức chuẩn của kiểu hàng",
        compute="_compute_parametric_template")

    @api.depends("product_type", "reference_product_id")
    def _compute_parametric_template(self):
        Template = self.env["dl.bom.template"]
        Bom = self.env["dl.bom"]
        for rec in self:
            tmpl, std = Template, Bom
            if rec.product_type == "manufactured" and rec.reference_product_id:
                tmpl = rec.reference_product_id._dlm_parametric_template()
                if not tmpl:
                    std = rec.reference_product_id._dlm_standard_bom()
            rec.parametric_template_id = tmpl
            rec.has_parametric_template = bool(tmpl)
            rec.standard_bom_id = std

    param_ids = fields.One2many(
        "dl.quotation.request.line.param",
        "line_id",
        string="Thông số theo mẫu",
        copy=True,
    )

    # Tham số bắt buộc còn trống — nuôi cả cổng chặn lúc gửi lẫn nhãn nhắc trên
    # form. Tách thành field để view hỏi được mà không phải gọi lại vòng lặp.
    missing_param_names = fields.Char(
        string="Thông số còn thiếu", compute="_compute_param_state")
    has_missing_params = fields.Boolean(compute="_compute_param_state")
    has_out_of_range_params = fields.Boolean(compute="_compute_param_state")

    @api.depends("param_ids.value", "param_ids.required",
                 "param_ids.out_of_range", "has_parametric_template",
                 "parametric_template_id")
    def _compute_param_state(self):
        for rec in self:
            # 🔴 Dòng thuộc nhóm có mẫu nhưng KHÔNG có ô nào = "không thiếu gì",
            # cố ý. Đó là dòng CŨ: tạo từ trước khi có panel thông số, hoặc tạo
            # khi nhóm chưa gắn mẫu rồi mẫu mới được dựng sau. Coi chúng là
            # thiếu sẽ khoá cứng mọi thao tác sửa trên RFQ lịch sử, và làm chính
            # migration nổ giữa chừng.
            #
            # Lỗ "import/RPC né được cổng chặn" KHÔNG bịt ở đây mà ở
            # `_dlm_seed_param_vals`: mọi dòng tạo mới thuộc nhóm có mẫu đều được
            # dựng sẵn bộ ô, nên tới lượt kiểm là đã có ô để soi.
            missing = rec.param_ids.filtered(
                lambda p: p.required and not p.value)
            rec.has_missing_params = bool(missing)
            rec.missing_param_names = ", ".join(
                missing.mapped(lambda p: p.name or p.code))
            rec.has_out_of_range_params = any(
                p.out_of_range for p in rec.param_ids)

    @api.model
    def _dlm_template_param_commands(self, template, keep_values=None):
        """Lệnh o2m dựng bộ tham số theo ``template``, giữ số cũ theo MÃ.

        Giữ theo `code` chứ không theo id bản ghi: Sales đổi nhóm rồi đổi lại,
        hoặc mẫu lên phiên bản mới, thì "D=1200" vẫn còn nguyên thay vì bắt gõ
        lại. Mã nào mẫu mới không còn thì rụng theo — đó là ý muốn, vì tham số
        đó không còn nghĩa với mẫu mới.

        Ô để TRỐNG, không lấy `default_value` của mẫu: mặc định là con số của
        mẫu chứ không phải của khách, mà nó chảy thẳng vào định mức rồi vào giá
        bán. Mọi dòng bỏ trống sẽ cùng ra một định mức mà không ai thấy sai."""
        keep_values = keep_values or {}
        commands = [(5, 0, 0)]
        for param in template.param_ids:
            commands.append((0, 0, {
                "template_param_id": param.id,
                "sequence": param.sequence,
                "code": param.code,
                "name": param.name,
                "dim_role": param.dim_role,
                "value": keep_values.get(param.code, 0.0),
                "value_min": param.value_min,
                "value_max": param.value_max,
                "required": param.required,
            }))
        return commands

    def _dlm_param_commands(self, template):
        """Bản theo bản ghi: dựng lại bộ tham số, mang theo số dòng này đã có."""
        self.ensure_one()
        return self._dlm_template_param_commands(
            template, {p.code: p.value for p in self.param_ids if p.value})

    @api.onchange("product_type", "reference_product_id")
    def _onchange_category_sync_params(self):
        """Đổi Kiểu hàng → dựng lại đúng bộ ô thông số mà mẫu của nó khai."""
        for rec in self:
            if rec.product_type != "manufactured":
                if rec.param_ids:
                    rec.param_ids = [(5, 0, 0)]
                continue
            template = (rec.reference_product_id._dlm_parametric_template()
                        if rec.reference_product_id
                        else self.env["dl.bom.template"])
            # Bộ hiện tại đã đúng mẫu này rồi thì đừng đụng vào — onchange chạy
            # cả khi Sales sửa field khác, dựng lại vô cớ sẽ nháy hết ô đang gõ.
            current = set(rec.param_ids.mapped("code"))
            wanted = set(template.param_ids.mapped("code"))
            if current == wanted and (wanted or not rec.param_ids):
                continue
            rec.param_ids = rec._dlm_param_commands(template)

    def _dlm_sync_params(self):
        """Đồng bộ bộ tham số ở tầng SERVER (import/RPC không chạy onchange).

        Form Sales đã có onchange lo phần nhìn thấy được, nhưng dòng RFQ còn vào
        hệ thống bằng import Excel và RPC — không có bộ tham số thì cổng chặn
        lúc gửi không có gì để kiểm, và dòng lặp lại không khớp được chữ ký."""
        for rec in self:
            if rec.product_type != "manufactured":
                if rec.param_ids:
                    rec.param_ids.unlink()
                continue
            template = (rec.reference_product_id._dlm_parametric_template()
                        if rec.reference_product_id
                        else self.env["dl.bom.template"])
            if set(rec.param_ids.mapped("code")) == set(
                    template.param_ids.mapped("code")):
                continue
            # sudo: đây là đồng bộ của HỆ THỐNG, không phải người sửa yêu cầu —
            # đi qua cổng _SALES_ONLY_LINE_FIELDS sẽ chặn oan chính nó khi ghi
            # đệ quy, và trên DB thì param_ids vẫn chỉ đổi theo nhóm Sales chọn.
            rec.sudo().param_ids = rec._dlm_param_commands(template)

    def _dlm_param_values(self):
        """Bộ tham số Sales đã nhập, dạng ``{'D': 1200.0, ...}``.

        Chỉ trả về khi ĐỦ tham số bắt buộc — thiếu một ô là chữ ký tham số vô
        nghĩa (khớp nhầm cấu hình khác chỉ vì hai ô trùng nhau)."""
        self.ensure_one()
        if not self.param_ids:
            return {}
        if any(p.required and not p.value for p in self.param_ids):
            return {}
        return {p.code: p.value for p in self.param_ids if p.value}

    def _dlm_wanted_dimensions(self):
        """Kích thước để chấm điểm: ĐỌC ô Sales nhập trước, hết cách mới đoán.

        `_dlm_parse_dimensions` (regex trên văn bản tự do) từ đây là ĐƯỜNG DỰ
        PHÒNG, dùng cho dòng thuộc nhóm chưa có mẫu và dòng cũ nhập trước khi có
        panel tham số. Không xoá nó: phần lớn RFQ vẫn rơi vào nhóm chưa có mẫu."""
        self.ensure_one()
        dims = {}
        for param in self.param_ids:
            if param.dim_role and param.dim_role != "none" and param.value:
                dims[param.dim_role] = param.value
        if dims.get("length") and dims.get("width"):
            return dims
        guessed = self._dlm_parse_dimensions(
            self.dimension_note, self.product_name)
        # Số Sales gõ vào ô có nhãn LUÔN thắng số đoán từ câu chữ.
        guessed.update(dims)
        return guessed

    # ── Làn L1 chính xác — khớp CHỮ KÝ tham số, không phải chấm điểm mờ ──────
    # Cùng một cấu hình bàn 1200×400×670 xuất hiện 5 lần trong 4 tháng qua 2
    # khách (sổ đặt hàng thật). Chấm điểm mờ theo tên chỉ bắt được khi Sales gõ
    # giống lần trước; chữ ký tham số bắt được kể cả khi tên viết khác hẳn.
    exact_bom_id = fields.Many2one(
        "dl.bom",
        string="Định mức đã có đúng cấu hình này",
        compute="_compute_exact_bom",
    )

    @api.depends("product_type", "reference_product_id", "param_ids.value",
                 "resolved_product_id", "auto_resolved", "is_infeasible")
    def _compute_exact_bom(self):
        Bom = self.env["dl.bom"]
        for rec in self:
            rec.exact_bom_id = Bom
            # 🔴 Chỉ bỏ qua dòng do NGƯỜI chốt. Bỏ qua cả dòng tự chốt thì sinh
            # vòng lật cờ: làn L0 đọc exact_bom_id để chốt → chốt xong
            # exact_bom_id thành rỗng → lần ghi sau _dlm_autoresolve_bom không
            # thấy gì nữa và HUỶ chốt, rồi lại chốt lại...
            if (rec.product_type != "manufactured" or rec.is_infeasible
                    or (rec.resolved_product_id and not rec.auto_resolved)):
                continue
            template = rec.parametric_template_id
            values = rec._dlm_param_values()
            if not template or not values:
                continue
            # Ngoài miền hợp lệ thì KHÔNG nhận là "đã từng làm": cỡ đặc biệt phải
            # để Kỹ thuật xem tận nơi, dù chữ ký có tình cờ trùng.
            if rec.has_out_of_range_params:
                continue
            rec.exact_bom_id = Bom.search([
                ("product_id", "=", template.generic_product_id.id),
                ("bom_type", "=", "quotation"),
                ("param_signature", "=", Bom._dlm_param_signature(values)),
                ("status", "in", ("confirmed", "locked")),
                ("is_rfq_provisional", "=", False),
            ], order="id desc", limit=1)

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

    # Lưới xem trước ảnh ĐÍNH KÈM ngay trên form dòng (widget many2many_binary chỉ
    # bày thẻ file, không xem được ảnh — giống màn Kiểm hàng QC). Ảnh nhúng thẳng
    # dạng data URI để né route /web/image lỗi khi ảnh vừa upload còn res_id=0.
    attachment_gallery = fields.Html(
        string="Lưới ảnh đính kèm", sanitize=False, readonly=True,
        compute="_compute_attachment_gallery")

    @api.depends("attachment_ids")
    def _compute_attachment_gallery(self):
        for rec in self:
            items = []
            for att in rec.attachment_ids:
                name = att.name or ""
                thumb = att._dlm_image_thumb()
                if thumb:
                    # Ảnh: thumbnail nhúng thẳng data URI (né /web/image lỗi khi res_id=0).
                    items.append(Markup(
                        '<div class="dl-rfq-evi-item" title="%s">'
                        '<img src="data:image/jpeg;base64,%s" alt="%s"/>'
                        '<span class="dl-rfq-evi-name">%s</span></div>'
                    ) % (name, thumb, name, name))
                else:
                    # File khác: thẻ có icon theo loại, bấm mở/xem trong tab mới
                    # (PDF render thẳng; loại khác trình duyệt tự mở hoặc tải).
                    items.append(Markup(
                        '<a class="dl-rfq-evi-item dl-rfq-evi-file" '
                        'href="/web/content/%s" target="_blank" '
                        'rel="noopener" title="%s">'
                        '<span class="dl-rfq-evi-thumb"><i class="fa %s"></i></span>'
                        '<span class="dl-rfq-evi-name">%s</span></a>'
                    ) % (att.id, name, att._dlm_file_icon(), name))
            rec.attachment_gallery = (
                Markup('<div class="dl-rfq-evi-gallery">%s</div>')
                % Markup("").join(items)) if items else False

    # Số file đính kèm — cột tín hiệu trên bảng dòng để KTV triage nhanh
    # (dòng gia công không có đính kèm thường là ứng viên "cần bổ sung").
    attachment_count = fields.Integer(
        string="Số file đính kèm", compute="_compute_attachment_count")

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    resolved_product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm xác định",
    )

    # SP hợp lệ để CHỌN khi resolve (gia công): lọc theo Nhóm SP của dòng RFQ
    # (KHÔNG lọc theo trạng thái vòng đời — chọn được cả draft lẫn active).
    # Domain của resolved_product_id ở form Kỹ thuật (view) trỏ vào field này.
    resolvable_product_ids = fields.Many2many(
        "product.product", compute="_compute_resolvable_product_ids",
        string="Sản phẩm hợp lệ để chọn")

    @api.depends("product_category_id")
    def _compute_resolvable_product_ids(self):
        Product = self.env["product.product"]
        for rec in self:
            # CHỈ sản phẩm gia công: dòng RFQ là thứ KHÁCH đặt, còn bán thành phẩm
            # là cấu phần bên trong định mức (chọn ở dòng BOM, không phải ở đây).
            domain = [("product_kind", "=", "manufactured")]
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
        string="Nhóm sản phẩm chọn được")

    # ĐỪNG BỎ @api.depends("product_type"). Danh sách này KHÔNG phụ thuộc field nào
    # của dòng, nhưng compute chỉ khai depends_context thì Odoo không đưa field vào
    # spec onchange ⇒ DÒNG MỚI (chưa lưu, đang mở dialog "Sản phẩm gia công") nhận
    # [] và ô Nhóm sản phẩm hiện "Không có dữ liệu"; dòng đã lưu thì lại bình thường
    # nên rất dễ tưởng là lỗi dữ liệu. product_type luôn có mặt (required + default)
    # nên dùng làm mồi kích hoạt.
    @api.depends_context("uid")
    @api.depends("product_type")
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
        string="Sản phẩm tham khảo hợp lệ")

    @api.depends("product_category_id")
    def _compute_reference_product_ids(self):
        """Kiểu hàng Sales chọn được: SP gia công của nhóm, và PHẢI dùng được.

        "Dùng được" = có mẫu tham số (chọn xong nhập kích thước là sinh định
        mức) HOẶC đã có ít nhất một định mức đã duyệt (dùng lại được ngay).

        🔴 KHÔNG lọc thành "phải có định mức đã duyệt": sản phẩm dùng chung của
        một họ mới khai mẫu chưa có instance nào, nhưng vẫn phải chọn được —
        chọn xong nhập kích thước là ra. Lọc chặt sẽ giấu mất cả một họ.

        Ngược lại, SP không mẫu và không định mức nào là cái bẫy: Sales chọn
        phải thì chẳng có gì để dùng lại, mà cũng không biết vì sao."""
        Product = self.env["product.product"]
        Bom = self.env["dl.bom"]
        Template = self.env["dl.bom.template"]
        for rec in self:
            domain = [
                ("product_kind", "=", "manufactured"),
                ("dlm_lifecycle_state", "=", "active"),
            ]
            if rec.product_category_id:
                domain.append(("categ_id", "child_of", rec.product_category_id.id))
            candidates = Product.search(domain)
            if not candidates:
                rec.reference_product_ids = candidates
                continue
            with_template = set(Template.search([
                ("generic_product_id", "in", candidates.ids),
                ("status", "in", ("confirmed", "locked")),
                ("is_parametric", "=", True),
            ]).mapped("generic_product_id").ids)
            with_bom = set(Bom.search([
                ("product_id", "in", candidates.ids),
                ("status", "in", ("confirmed", "locked")),
            ]).mapped("product_id").ids)
            usable = with_template | with_bom
            rec.reference_product_ids = candidates.filtered(
                lambda p: p.id in usable)

    # ── §3.6 · Bộ dò khớp "đã từng gia công" ────────────────────────────────
    # Trả tín hiệu 💡 để KTV khỏi tự gõ tìm (và khỏi tạo SP trùng vì gõ khác chữ).
    suggested_product_id = fields.Many2one(
        "product.product", string="Sản phẩm gợi ý",
        compute="_compute_suggestion")
    suggestion_reason = fields.Char(
        string="Vì sao gợi ý", compute="_compute_suggestion")
    suggestion_state = fields.Selection(
        [
            ("none", "Không có gợi ý"),
            ("suggest", "Có gợi ý"),
            ("auto", "Gợi ý tự động"),
        ],
        string="Mức gợi ý sản phẩm", compute="_compute_suggestion")

    @api.depends("product_type", "product_name", "reference_product_id",
                 "product_category_id", "resolved_product_id", "is_infeasible",
                 "dimension_note", "param_ids.value")
    def _compute_suggestion(self):
        for rec in self:
            rec.suggested_product_id = False
            rec.suggestion_reason = False
            rec.suggestion_state = "none"
            # Chỉ gợi ý cho dòng gia công CHƯA xác định SP và chưa kết luận
            # không khả thi — dòng đã xong không cần 💡.
            if (rec.product_type != "manufactured" or rec.resolved_product_id
                    or rec.is_infeasible):
                continue
            ranked = rec._dlm_suggest_candidates(limit=1)
            if not ranked:
                continue
            best = ranked[0]
            rec.suggested_product_id = best["product"].id
            rec.suggestion_reason = ", ".join(best["reasons"])
            rec.suggestion_state = (
                "auto" if best["score"] >= _MATCH_THRESHOLD_AUTO else "suggest")

    @api.model
    def _dlm_parse_dimensions(self, *texts):
        """Trích kích thước (mm) từ mô tả tự do của Sales (dimension_note + tên SP).

        Bắt các mẫu phổ biến (§3.6): "1400x830", "1200 x 800 x 750",
        "dài 1400 rộng 830 cao 750", "dày 2". Trả dict chỉ gồm khoá tìm thấy:
        ``{'length','width','height','thickness'}`` (float, mm). Từ khoá tường
        minh (dài/rộng/cao/dày) GHI ĐÈ giá trị suy từ mẫu "A×B×C".

        ⚠️ Đây là dữ liệu ĐOÁN từ văn bản tự do — chỉ dùng để CHẤM ĐIỂM gợi ý,
        không bao giờ tự ghi vào BOM (§3.6: sai một chữ số là sai cả báo giá).
        """
        dims = {}
        blob = " ".join(t for t in texts if t).lower()
        if not blob:
            return dims

        def _num(token):
            return float(token.replace(",", "."))

        num = r"(\d+(?:[.,]\d+)?)"
        # (1) Mẫu "A × B [× C]" — coi là Dài × Rộng [× Cao].
        m = re.search(num + r"\s*[x×*]\s*" + num
                      + r"(?:\s*[x×*]\s*" + num + r")?", blob)
        if m:
            dims["length"] = _num(m.group(1))
            dims["width"] = _num(m.group(2))
            if m.group(3):
                dims["height"] = _num(m.group(3))
        # (2) Từ khoá tường minh — ưu tiên hơn mẫu "A×B".
        for key, kw in (("length", "dài"), ("width", "rộng"),
                        ("height", "cao"), ("thickness", "dày")):
            km = re.search(kw + r"\s*[:=]?\s*" + num, blob)
            if km:
                dims[key] = _num(km.group(1))
        return dims

    @api.model
    def _dlm_dimensions_match(self, wanted, product):
        """Khổ D×R (và C nếu cả hai cùng khai) của ``product`` có khớp bộ kích
        thước ``wanted`` đã trích không? So theo cặp KHÔNG phân biệt chiều
        (D×R = R×D), dung sai ``_DIM_MATCH_TOLERANCE`` mm. Chỉ khớp khi product
        khai đủ D, R (>0) — SP chưa nhập thuộc tính kỹ thuật thì bỏ qua."""
        pl, pw = product.dlm_dim_length, product.dlm_dim_width
        if not (pl and pw and wanted.get("length") and wanted.get("width")):
            return False
        tol = _DIM_MATCH_TOLERANCE
        want_pair = sorted((wanted["length"], wanted["width"]))
        prod_pair = sorted((pl, pw))
        if any(abs(a - b) > tol for a, b in zip(want_pair, prod_pair)):
            return False
        # Chiều cao chỉ dùng để LOẠI TRỪ khi cả hai cùng khai mà lệch nhau.
        wh, ph = wanted.get("height"), product.dlm_dim_height
        if wh and ph and abs(wh - ph) > tol:
            return False
        return True

    def _dlm_suggest_candidates(self, limit=5):
        """Dò các SP "đã từng gia công" khớp dòng RFQ này, xếp theo điểm §3.6.

        Trả về danh sách dict ``{'product', 'score', 'reasons'}`` đã lọc theo
        ngưỡng gợi ý (≥30) và sắp giảm dần theo điểm. Gồm LỚP 2 (sản phẩm/instance
        cụ thể) và LỚP 1 (họ có mẫu tham số — xem cuối hàm).
        """
        self.ensure_one()
        Product = self.env["product.product"]
        if self.product_type != "manufactured":
            return []
        # CHỈ sản phẩm gia công: gợi ý ở đây là "sản phẩm nào làm ra thứ khách
        # đặt". Bán thành phẩm là cấu phần bên trong định mức, không bao giờ là
        # kết quả của một dòng RFQ.
        kinds = ("manufactured",)
        scores = {}

        def add(product, points, reason):
            if not product or product.is_rfq_provisional:
                return
            entry = scores.get(product.id)
            if not entry:
                entry = {"product": product, "score": 0, "reasons": []}
                scores[product.id] = entry
            entry["score"] += points
            entry["reasons"].append(reason)

        # (a) Sales đã chọn SP tham khảo — tín hiệu mạnh nhất (§3.6 nguyên tắc #2).
        add(self.reference_product_id, _MATCH_SCORE_REFERENCE,
            _("Sales chọn tham khảo"))

        # (b) Khớp tên (tái dùng _dlm_find_name_matches đã có ở dl_product).
        if self.product_name:
            matches = Product._dlm_find_name_matches(
                self.product_name, kinds=kinds,
                extra_domain=[("is_rfq_provisional", "=", False)])
            for product in matches["exact"]:
                add(product, _MATCH_SCORE_NAME_EXACT, _("Trùng tên"))
            for product in matches["similar"]:
                add(product, _MATCH_SCORE_NAME_SIMILAR, _("Tên gần giống"))

        # (c) Cùng nhóm sản phẩm — chỉ cộng dồn cho SP đã có tín hiệu khác
        #     (đứng một mình +10 < 30 nên tự bị lọc; kết hợp với tên gần giống
        #     mới đủ ngưỡng gợi ý).
        if self.product_category_id:
            same_cat = Product.search([
                ("product_kind", "in", kinds),
                ("categ_id", "child_of", self.product_category_id.id),
                ("is_rfq_provisional", "=", False),
            ], limit=80)
            for product in same_cat:
                add(product, _MATCH_SCORE_SAME_CATEGORY, _("Cùng nhóm"))

        # (d) Khách hàng này từng đặt (đơn lặp lại thường cùng khách).
        customer = self.quotation_request_id.customer_id
        if customer:
            # Loại chính dòng này khỏi lịch sử. Dùng _origin.id: khi đang soạn
            # dòng CHƯA lưu (onchange), self.id là NewId ("NewId_4") — đẩy thẳng
            # vào SQL sẽ nổ "invalid input syntax for type integer". _origin.id
            # là id thật trong DB (falsy nếu dòng hoàn toàn mới, khi đó không có
            # gì để loại).
            domain = [
                ("quotation_request_id.customer_id", "=", customer.id),
                ("resolved_product_id", "!=", False),
            ]
            if self._origin.id:
                domain.append(("id", "!=", self._origin.id))
            prev_lines = self.env["dl.quotation.request.line"].search(
                domain, limit=200)
            for product in prev_lines.mapped("resolved_product_id"):
                add(product, _MATCH_SCORE_SAME_CUSTOMER, _("Khách từng đặt"))

        # (d2) So SỐ VỚI SỐ (§3.6, S05): khổ kích thước trích từ mô tả Sales
        #      khớp thuộc tính kỹ thuật D/R/C của ứng viên. Đây là lý do các
        #      field dlm_dim_* tồn tại. CHỈ cộng điểm cho SP đã lọt vào scores
        #      qua tín hiệu khác — dấu vân kích thước củng cố, không tự phát hiện
        #      SP mới (khổ trùng nhưng khác hẳn tên/nhóm thường là món khác).
        wanted = self._dlm_wanted_dimensions()
        if wanted.get("length") and wanted.get("width"):
            for entry in scores.values():
                if self._dlm_dimensions_match(wanted, entry["product"]):
                    entry["score"] += _MATCH_SCORE_DIM_MATCH
                    entry["reasons"].append(_("Khớp kích thước"))

        # ── LỚP 1 — đã từng làm ĐÚNG CẤU HÌNH NÀY ────────────────────────
        # 🔴 Bỏ tín hiệu "thuộc họ có mẫu tham số" (+50) từ 2026-08-19: mẫu nay
        # neo theo SẢN PHẨM và Sales chỉ đích danh kiểu hàng, nên "thuộc họ" đã
        # chính là điểm _MATCH_SCORE_REFERENCE. Cộng cả hai là đếm hai lần
        # (50 tham khảo + 50 họ + 10 nhóm = 110 cho một tín hiệu duy nhất).
        template = self.parametric_template_id
        if template:
            generic = template.generic_product_id
            values = self._dlm_param_values()
            if values:
                Bom = self.env["dl.bom"]
                signature = Bom._dlm_param_signature(values)
                if Bom.search_count([
                        ("product_id", "=", generic.id),
                        ("bom_type", "=", "quotation"),
                        ("param_signature", "=", signature)]):
                    add(generic, _MATCH_SCORE_PARAM_SIGNATURE,
                        _("Đã từng làm đúng cấu hình này"))

        # (e) Phạt SP đang Ngừng sử dụng — vẫn hiện nhưng đội xuống cuối/bị loại.
        for entry in scores.values():
            if entry["product"].dlm_lifecycle_state == "obsolete":
                entry["score"] += _MATCH_PENALTY_OBSOLETE
                entry["reasons"].append(_("Ngừng sử dụng"))

        ranked = sorted(
            (e for e in scores.values() if e["score"] >= _MATCH_THRESHOLD_SUGGEST),
            key=lambda e: (e["score"], e["product"].id), reverse=True)
        return ranked[:limit]

    # ── LÀN L0 — dòng tự chốt, KHÔNG qua Kỹ thuật ───────────────────────────
    # Bỏ qua Kỹ thuật được KHI VÀ CHỈ KHI đã tồn tại một ĐỊNH MỨC ĐÃ DUYỆT cho
    # đúng thứ này. Không có ngoại lệ nào khác.
    auto_resolved = fields.Boolean(
        string="Tự chốt (không qua Kỹ thuật)",
        readonly=True, copy=False,
        help="Dòng khớp một định mức đã duyệt nên hệ thống tự chốt kết quả kỹ "
             "thuật. Sales sửa lại yêu cầu thì cờ này mất và dòng quay về hàng "
             "đợi Kỹ thuật.")

    def _dlm_autoresolve_bom(self):
        """Định mức ĐÃ DUYỆT dùng thẳng được cho dòng này (hoặc rỗng).

        Hai đường, đều là "đã có bản duyệt cho đúng thứ này":
        • Kiểu hàng cỡ cố định (Hạng B) có định mức chuẩn hiện hành.
        • Kiểu hàng theo kích thước + bộ thông số trùng CHỮ KÝ một instance đã
          duyệt — tức đúng cấu hình đã từng làm.

        Cỡ ngoài miền hợp lệ KHÔNG bao giờ đi đường này, dù chữ ký có trùng:
        `exact_bom_id` đã tự loại."""
        self.ensure_one()
        if self.product_type != "manufactured" or self.is_infeasible:
            return self.env["dl.bom"]
        if not self.reference_product_id:
            return self.env["dl.bom"]
        if self.has_parametric_template:
            return self.exact_bom_id
        return self.standard_bom_id

    def _dlm_try_autoresolve(self):
        """Chốt (hoặc BỎ chốt) dòng theo làn tự động — gọi sau mỗi lần ghi.

        🔴 Chiều BỎ chốt quan trọng ngang chiều chốt: Sales sửa "Dài 1200 →
        1500" sau khi dòng đã tự chốt thì định mức cũ sai hẳn. Không gỡ cờ ở
        đây thì báo giá đi ra với định mức của một cỡ khác, và không ai biết.

        Không đụng dòng do NGƯỜI chốt (`auto_resolved` False mà đã có kết quả):
        đó là quyết định của Kỹ thuật, hệ thống không ghi đè."""
        for rec in self:
            if rec.product_type != "manufactured":
                continue
            if rec.resolved_product_id and not rec.auto_resolved:
                continue          # Kỹ thuật đã chốt tay — không đụng
            bom = rec._dlm_autoresolve_bom()
            if bom:
                if (rec.resolved_bom_id == bom
                        and rec.resolved_product_id == bom.product_id):
                    continue      # đã đúng rồi, khỏi ghi lại
                rec.sudo().with_context(dlm_skip_autoresolve=True).write({
                    "resolved_product_id": bom.product_id.id,
                    "resolved_bom_id": bom.id,
                    "auto_resolved": True,
                    "is_infeasible": False,
                    "infeasible_reason": False,
                })
                rec.quotation_request_id.sudo().message_post(body=_(
                    "Dòng <b>%(line)s</b> tự chốt theo định mức đã duyệt "
                    "<b>%(bom)s</b> của <b>%(prod)s</b> — không cần qua Kỹ thuật.",
                    line=rec.product_name or "",
                    bom=bom.display_name, prod=bom.product_id.display_name))
            elif rec.auto_resolved:
                rec.sudo().with_context(dlm_skip_autoresolve=True).write({
                    "resolved_product_id": False,
                    "resolved_bom_id": False,
                    "auto_resolved": False,
                })
                rec.quotation_request_id.sudo().message_post(body=_(
                    "Dòng <b>%s</b> đã đổi yêu cầu nên không còn khớp định mức "
                    "cũ — chuyển lại cho Kỹ thuật xử lý.")
                    % (rec.product_name or ""))

    def _dlm_autoresolve_product(self):
        """Suy ra SẢN PHẨM của dòng từ những gì Sales đã khai — không hỏi ai.

        Nhiệm vụ của Kỹ thuật là thiết kế ĐỊNH MỨC. "Món này là hàng mới hay
        hàng cũ, có phải đẻ thêm một mã sản phẩm không" là việc hành chính suy
        được từ dữ liệu, nên hệ thống tự trả lời rồi mới mở workspace.

        Trả ``(product, origin)``; ``origin`` để workspace nói cho KTV biết vì
        sao lại là sản phẩm đó (KTV vẫn đổi được bằng nút "Đổi sản phẩm").

        Ba nấc, theo đúng thứ tự — mỗi nấc thay cho một lá chắn TRƯỚC ĐÂY bắt
        KTV tự bấm trong khối "Tạo sản phẩm mới":

        1. ``generic`` — nhóm có mẫu tham số ⇒ MỌI kích thước dùng chung sản
           phẩm dùng chung của mẫu, chỉ định mức là riêng. Thay cho ô tick
           "Đây là sản phẩm khác kết cấu": ở đây không có gì để tick, vì đường
           đẻ mã theo từng cỡ đã bị bịt bằng cấu trúc.
        2. ``name_match`` — đã có sản phẩm TRÙNG HỆT tên. Luật cũ chặn cứng rồi
           bảo KTV "quay lại chọn chính sản phẩm này"; nay hệ thống chọn hộ.
        3. ``created`` — chưa từng có ⇒ tạo sản phẩm TẠM mang đúng tên Sales gõ
           và đúng nhóm Sales chọn. Tạm (``is_rfq_provisional``) nên bỏ dở thì
           cron dọn, và chỉ thành sản phẩm thật khi dòng RFQ hoàn tất.

        ⚠️ Lá chắn "tên GẦN GIỐNG" cố ý KHÔNG chuyển vào đây: nó là phán đoán
        thật sự (hai cái tên na ná có thể là một món hoặc hai món khác hẳn),
        không suy được. Nó vẫn sống, nhưng dưới dạng thẻ gợi ý "Có phải sản
        phẩm này?" — nhắc chứ không chặn. Bộ dò khớp cho tên gần giống 25 điểm
        + cùng nhóm 10 = 35, vượt ngưỡng hiện thẻ."""
        self.ensure_one()
        Product = self.env["product.product"]
        if self.product_type != "manufactured" or not self.product_category_id:
            return Product, False

        # Bản tạm đã dựng cho chính dòng này ⇒ dùng lại. Nhờ nhánh này hàm gọi
        # bao nhiêu lần cũng ra một kết quả, nên workspace mở lại / KTV bấm
        # "Quay lại đề xuất" đều không đẻ thêm sản phẩm.
        existing_draft = Product.search([
            ("is_rfq_provisional", "=", True),
            ("rfq_source_line_id", "=", self.id),
        ], order="id desc", limit=1)
        if existing_draft:
            return existing_draft, "created"

        # Sales đã chỉ đích danh Kiểu hàng ⇒ đó chính là sản phẩm, hết đoán.
        # Đúng cho cả hai loại: sản phẩm dùng chung của một họ tham số, và mặt
        # hàng cỡ cố định đã có định mức chuẩn.
        if self.reference_product_id:
            return self.reference_product_id, "sales_pick"

        name = (self.product_name or "").strip()
        if not name:
            return Product, False

        # Soi trùng trên CẢ bán thành phẩm: `_check_dlm_name_duplicate` chặn tạo
        # sản phẩm gia công trùng tên với BTP, nên nếu bỏ qua thì nấc 3 sẽ nổ.
        matches = Product._dlm_find_name_matches(
            name, kinds=("manufactured", "material_processed"),
            extra_domain=[("is_rfq_provisional", "=", False)])
        if matches["exact"]:
            usable = matches["exact"].filtered(
                lambda p: p.product_kind == "manufactured")
            # Trùng tên nhưng cái đang có là BTP: không dùng làm sản phẩm của
            # dòng được (khách không đặt bán thành phẩm) mà cũng không tạo mới
            # được. Trả tay cho KTV — đây là ca hiếm và cần người gỡ.
            return (usable[:1], "name_match") if usable else (Product, False)

        product = Product.create({
            "name": name,
            "categ_id": self.product_category_id.id,
            "product_kind": "manufactured",
            # Nháp cho tới khi đơn chốt — giống hệt đường tạo tay trước đây.
            "dlm_lifecycle_state": "draft",
            "is_rfq_provisional": True,
            "rfq_source_line_id": self.id,
        })
        return product, "created"

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

    supplement_note = fields.Text(
        string="Nội dung cần bổ sung",
        help="KTV ghi chú thông tin cần Sales bổ sung cho dòng này.",
    )

    # Per-line: Sales đã bổ sung xong dòng này (đặt tự động khi Sales sửa nội
    # dung yêu cầu của một dòng đang "Chờ bổ sung"). Nhờ vậy action_resubmit chỉ
    # gửi lại đúng các dòng Sales THỰC SỰ đã bổ sung, không xóa mù cờ của những
    # dòng còn chờ — tránh bỏ sót khi RFQ nhiều dòng.
    supplement_done = fields.Boolean(
        string="Đã bổ sung",
        default=False,
        copy=False,
        help="Sales đã bổ sung thông tin cho dòng đang chờ; chờ Kỹ thuật xem lại.",
    )

    # Sales sửa yêu cầu (số lượng / kích thước / đính kèm) SAU KHI Kỹ thuật đã
    # xác định SP+BOM → kết quả cũ có thể không còn khớp. Đánh dấu để Kỹ thuật
    # xem lại: dòng tạm coi như CHƯA xử lý xong (xem _is_resolved) nên RFQ tự
    # lùi khỏi "Chờ tạo báo giá", KTV phải mở lại và Xác nhận lần nữa.
    needs_review = fields.Boolean(
        string="Cần Kỹ thuật xem lại",
        default=False,
        copy=False,
        help="Sales đã sửa yêu cầu sau khi Kỹ thuật xác định — kết quả cần xem lại.",
    )

    technical_status = fields.Selection(
        [
            ("pending", "Chưa xử lý"),
            ("waiting", "Chờ bổ sung"),
            ("supplemented", "Đã bổ sung"),
            ("processing", "Đang xử lý"),
            ("review", "Cần xem lại"),
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
        "supplement_note",
        "supplement_done",
        "needs_review",
    )
    def _compute_technical_status(self):
        for rec in self:
            if rec.product_type == "trading":
                rec.technical_status = "not_required"
            elif rec.is_infeasible:
                rec.technical_status = "infeasible"
            elif rec.resolved_product_id and rec.resolved_bom_id:
                rec.technical_status = "review" if rec.needs_review else "done"
            elif rec.supplement_note:
                rec.technical_status = "supplemented" if rec.supplement_done else "waiting"
            elif rec.supplement_done:
                # Sales đã bổ sung + gửi lại (supplement_note đã xóa nhưng cờ
                # supplement_done giữ lại): dòng chờ KTV XỬ LÝ LẠI — hiện "Đã bổ
                # sung" cho dễ nhận biết thay vì lẫn với dòng "Chưa xử lý".
                rec.technical_status = "supplemented"
            elif rec.resolved_product_id or rec.resolved_bom_id:
                rec.technical_status = "processing"
            else:
                rec.technical_status = "pending"

    resolved_summary = fields.Char(
        string="Kết quả kỹ thuật",
        compute="_compute_resolved_summary",
    )

    @api.depends("product_type", "resolved_product_id", "is_infeasible",
                 "infeasible_reason", "supplement_note", "supplement_done",
                 "needs_review")
    def _compute_resolved_summary(self):
        # Kèm lý do/nội dung rút gọn ngay trong cột kết quả để Sales lướt list
        # là thấy, khỏi phải mở từng dòng đọc lý do.
        def _short(text):
            text = " ".join((text or "").split())
            return text[:57] + "..." if len(text) > 60 else text

        for rec in self:
            if rec.product_type == "trading":
                rec.resolved_summary = ""
            elif rec.is_infeasible:
                reason = _short(rec.infeasible_reason)
                rec.resolved_summary = (
                    "Không khả thi — %s" % reason if reason else "Không khả thi")
            elif rec.resolved_product_id:
                name = rec.resolved_product_id.display_name
                rec.resolved_summary = (
                    "Cần xem lại (Sales đã sửa yêu cầu) — %s" % name
                    if rec.needs_review else name)
            elif rec.supplement_note:
                prefix = ("Đã bổ sung, chờ Kỹ thuật xem lại"
                          if rec.supplement_done else "Chờ Sales bổ sung")
                rec.resolved_summary = "%s — %s" % (
                    prefix, _short(rec.supplement_note))
            elif rec.supplement_done:
                rec.resolved_summary = "Đã bổ sung — chờ Kỹ thuật xử lý"
            else:
                rec.resolved_summary = "Chưa chọn sản phẩm"

    # EX-13 / RES-022 — dòng đã xác định nhưng định mức còn vật tư THÔ chưa có
    # giá NCC đã duyệt ⇒ Sales sẽ chưa tạo được báo giá (QTE-003). Hiện SỚM ngay
    # trên dòng để Sales chủ động hối Mua hàng, thay vì đâm tường ở khâu sau.
    # compute_sudo để đọc supplierinfo; chỉ lộ cờ + TÊN vật tư, không lộ giá.
    pricing_blocked = fields.Boolean(
        string="Thiếu giá nhà cung cấp", compute="_compute_pricing_blocked",
        compute_sudo=True)
    pricing_block_summary = fields.Char(
        string="Vật tư thiếu giá nhà cung cấp", compute="_compute_pricing_blocked",
        compute_sudo=True)

    @api.depends("resolved_bom_id",
                 "resolved_bom_id.line_ids.material_id",
                 "resolved_bom_id.line_ids.material_id.dlm_supplier_price_state")
    def _compute_pricing_blocked(self):
        for rec in self:
            missing = rec.resolved_bom_id._dlm_unpriced_raw_materials()
            rec.pricing_blocked = bool(missing)
            rec.pricing_block_summary = ", ".join(
                missing.mapped("display_name")) if missing else False

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
        BOM tham chiếu — §3 màn Nhận RFQ).

        Dòng gia công đang "Cần Kỹ thuật xem lại" (Sales đã sửa yêu cầu sau khi
        xác định) tạm coi như CHƯA xong — buộc KTV mở lại và Xác nhận lần nữa."""
        self.ensure_one()
        if self.is_infeasible:
            return True
        if not self.resolved_product_id:
            return False
        if self.needs_review:
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

    @api.onchange("quantity")
    def _onchange_quantity_positive(self):
        """Bắt số lượng ≤ 0 ngay khi rời ô trong dialog dòng — trước lúc lưu.

        _check_quantity chỉ nổ khi ghi xuống DB (bấm Lưu cả hồ sơ); dòng x2many
        sửa trong dialog chỉ nằm trong bộ nhớ nên số âm lọt vào bảng mà chưa bị
        chặn. Onchange chạy lúc blur: đưa về 1 và cảnh báo tại chỗ."""
        for rec in self:
            if rec.quantity <= 0:
                rec.quantity = 1.0
                return {
                    "warning": {
                        "title": _("Số lượng không hợp lệ"),
                        "message": _("Số lượng phải lớn hơn 0. Đã đặt lại về 1."),
                    }
                }

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

    @api.constrains("product_type", "product_category_id")
    def _check_category_required(self):
        """Dòng gia công BẮT BUỘC có Nhóm sản phẩm.

        Nhóm là chìa khoá định tuyến của cả luồng: nó quyết định form hỏi Sales
        thông số gì, bộ dò khớp so với họ sản phẩm nào, và Kỹ thuật mở ra thấy
        mẫu nào. Dòng không nhóm thì Sales không được hỏi thông số, mà Kỹ thuật
        cũng không có mẫu để sinh định mức — rơi thẳng xuống làm tay.

        Không dùng `required=True` ở field vì `product_category_id` dùng chung
        với dòng THƯƠNG MẠI (đã định danh bằng Product cụ thể, không cần nhóm) —
        đặt required ở tầng field sẽ chặn oan cả dòng thương mại lẫn dòng cũ."""
        for rec in self:
            if rec.product_type != "manufactured":
                continue
            if not rec.product_category_id:
                raise ValidationError(_(
                    "Dòng gia công \"%s\" chưa chọn Nhóm sản phẩm. Nhóm quyết "
                    "định hệ thống hỏi thông số gì và Kỹ thuật dùng mẫu nào."
                ) % (rec.product_name or ""))

    @api.constrains("product_type", "dimension_note", "attachment_ids",
                    "param_ids", "product_category_id")
    def _check_manufactured_spec(self):
        """Dòng gia công phải mang đủ ĐỀ BÀI cho Kỹ thuật — hai nhánh theo nhóm.

        Nhóm CÓ mẫu tham số: phải điền đủ thông số bắt buộc, HOẶC đính kèm bản
        vẽ. Bản vẽ vẫn được chấp nhận thay vì bắt gõ số, vì khách gửi bản vẽ đầy
        đủ là ca hợp lệ và Sales không phải người đọc bản vẽ ra số.

        Nhóm CHƯA có mẫu: giữ luật cũ — Mô tả HOẶC Đính kèm.

        Chung một lý do: không có gì đo được thì dòng đó chỉ là một cái tên, Kỹ
        thuật buộc phải trả lại ngay — mất một vòng qua lại.

        Luật nằm ở constrains chứ không chỉ ở form Sales: import Excel và RPC
        đều lọt qua required chéo của view."""
        for rec in self:
            if rec.product_type != "manufactured":
                continue
            if rec.attachment_ids:
                continue
            if rec.has_parametric_template:
                if rec.has_missing_params:
                    raise ValidationError(_(
                        "Dòng gia công \"%(name)s\" còn thiếu thông số: "
                        "%(missing)s. Điền đủ hoặc đính kèm bản vẽ.",
                        name=rec.product_name or "",
                        missing=rec.missing_param_names))
            elif not (rec.dimension_note or "").strip():
                raise ValidationError(_(
                    "Dòng gia công \"%s\" phải có Mô tả kích thước hoặc Đính "
                    "kèm bản vẽ. Kỹ thuật không xử lý được dòng chỉ có mỗi tên."
                ) % (rec.product_name or ""))

    @api.constrains("uom_id", "quantity")
    def _check_uom_integer(self):
        """Đơn vị đếm được (bộ/cái) thì số lượng phải nguyên.

        "2,5 bộ bàn ghế" là lỗi gõ, nhưng nó đi thẳng vào báo giá rồi xuống lệnh
        làm hàng mà không chỗ nào chặn. Đơn vị đo được (mét, kg) thì để nguyên —
        100,5 mét máng điện là con số hợp lệ."""
        for rec in self:
            uom = rec.uom_id
            if not uom or uom.category_id != self.env.ref(
                    "uom.product_uom_categ_unit", raise_if_not_found=False):
                continue
            if float_compare(rec.quantity, round(rec.quantity),
                             precision_digits=3) != 0:
                raise ValidationError(_(
                    "Số lượng của \"%(name)s\" là %(qty)s %(uom)s — đơn vị đếm "
                    "được thì số lượng phải là số nguyên.",
                    name=rec.product_name or "",
                    qty=rec.quantity, uom=uom.name))

    @api.constrains("product_type", "product_name")
    def _check_unique_name_in_request(self):
        """Trong cùng một RFQ, không cho hai dòng gia công trùng tên sản phẩm
        (dễ nhầm khi Kỹ thuật xử lý / tạo Product). So khớp bỏ khoảng trắng
        đầu-cuối và không phân biệt hoa-thường; dòng thương mại được miễn (đã
        định danh bằng Product cụ thể)."""
        for rec in self:
            if rec.product_type != "manufactured":
                continue
            name = (rec.product_name or "").strip().lower()
            if not name:
                continue
            dup = rec.quotation_request_id.line_ids.filtered(
                lambda l: l.id != rec.id
                and l.product_type == "manufactured"
                and (l.product_name or "").strip().lower() == name)
            if dup:
                raise ValidationError(_(
                    "Dòng gia công trùng tên sản phẩm \"%s\" trong cùng yêu "
                    "cầu báo giá. Mỗi dòng gia công phải có tên khác nhau.",
                    rec.product_name))

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

    @api.model
    def _dlm_normalize_line_vals(self, vals):
        """Gộp khoảng trắng thừa trong Tên sản phẩm và Mô tả kích thước.

        Lý do phải chuẩn hóa tại điểm ghi chứ không chỉ khi so sánh:
        _check_unique_name_in_request có strip().lower() nên vẫn BẮT được trùng,
        nhưng giá trị lưu xuống DB là chuỗi thô người dùng gõ. Hệ quả là "Bàn
        thao tác" và "Bàn  thao tác " nằm trong DB thành hai chuỗi khác nhau —
        tìm kiếm, gom nhóm và bộ dò khớp sản phẩm đã từng gia công (§3.6) đều
        chạy trên giá trị lưu nên đều lệch. Cùng cách làm với res.partner."""
        for fname in ("product_name", "dimension_note"):
            value = vals.get(fname)
            if isinstance(value, str):
                vals[fname] = _MULTI_SPACE_RE.sub(" ", value).strip()
        return vals

    @api.constrains("product_type", "product_name")
    def _check_product_name_length(self):
        """Tên sản phẩm gia công phải đủ dài để còn gọi được là một cái tên.

        Chặn tên một ký tự lọt qua khi nhập vội hay import hàng loạt — dòng như
        vậy Kỹ thuật mở ra không biết khách muốn gì, mà nó vẫn chiếm một chỗ
        trong RFQ và trong báo giá về sau."""
        for rec in self:
            if rec.product_type != "manufactured":
                continue
            name = (rec.product_name or "").strip()
            # Rỗng đã có _check_product_type_required lo, ở đây chỉ xét độ dài.
            if name and len(name) < _MIN_PRODUCT_NAME_LEN:
                raise ValidationError(_(
                    "Tên sản phẩm \"%(name)s\" quá ngắn — cần ít nhất "
                    "%(n)s ký tự.", name=rec.product_name,
                    n=_MIN_PRODUCT_NAME_LEN))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._dlm_normalize_line_vals(vals)
            self._dlm_seed_param_vals(vals)
        records = super().create(vals_list)
        records._stamp_attachments()
        # Trước _recompute_status_from_lines: dòng tự chốt xong thì RFQ mới
        # tổng kết đúng (có thể lên thẳng "Chờ tạo báo giá").
        records._dlm_try_autoresolve()
        records.mapped("quotation_request_id")._recompute_status_from_lines()
        return records

    @api.model
    def _dlm_seed_param_vals(self, vals):
        """Dựng sẵn ô thông số vào ``vals`` khi người gọi chưa truyền.

        🔴 Phải làm ở ĐÂY, trước `super().create()`, không phải sau. Bộ tham số
        là thứ `_check_manufactured_spec` soi; dựng sau khi bản ghi đã tạo thì
        Odoo validate lúc ô chưa tồn tại (lọt cổng), rồi lệnh ghi ô rỗng ngay
        sau đó lại kích constrain lần nữa và nổ — dòng hợp lệ cũng không tạo nổi.

        Dòng vào bằng import/RPC không chạy onchange nên không tự có ô; dựng ở
        đây để chúng chịu đúng một luật với dòng nhập trên form."""
        if vals.get("product_type", "manufactured") != "manufactured":
            return vals
        # `vals.get` chứ không `in vals`: người gọi truyền param_ids RỖNG cũng
        # phải được dựng ô, nếu không đó lại thành đường né cổng chặn.
        if vals.get("param_ids") or not vals.get("reference_product_id"):
            return vals
        product = self.env["product.product"].browse(
            vals["reference_product_id"])
        template = product._dlm_parametric_template()
        if template:
            vals["param_ids"] = self._dlm_template_param_commands(template)
        return vals

    def write(self, vals):
        self._dlm_normalize_line_vals(vals)
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
                'Thông tin yêu cầu (tên / nhóm sản phẩm / số lượng / mô tả / đính kèm) '
                'do Sales quản lý — Kỹ thuật không được chỉnh sửa.'))

        # Sales sửa nội dung yêu cầu → chốt lại trạng thái theo dòng (tính TRƯỚC
        # super để đọc đúng state cũ của từng dòng):
        #  - dòng đang "Chờ bổ sung" → đánh dấu "Đã bổ sung" (supplement_done).
        #  - dòng đã có kết quả kỹ thuật, Sales đổi field ảnh hưởng xử lý (SL /
        #    kích thước / đính kèm) → đánh dấu "Cần Kỹ thuật xem lại".
        auto_supplement_done = self.browse()
        auto_needs_review = self.browse()
        if not self.env.su and sales_gated and _user_is_sales(self.env):
            # param_ids nằm trong danh sách này vì thông số là ĐỀ BÀI ĐO ĐƯỢC:
            # Sales sửa "Dài 1200 → 1500" sau khi Kỹ thuật đã chốt định mức thì
            # định mức cũ sai hẳn, còn nặng hơn sửa câu mô tả.
            tech_relevant = bool(
                {"quantity", "uom_id", "dimension_note", "attachment_ids",
                 "param_ids"} & vals.keys())
            for rec in self:
                if rec.supplement_note and not rec.supplement_done:
                    auto_supplement_done |= rec
                elif (tech_relevant
                      and rec.product_type == "manufactured"
                      and rec.resolved_product_id
                      and not rec.is_infeasible
                      and not rec.needs_review):
                    auto_needs_review |= rec

        res = super().write(vals)

        # Đổi Kiểu hàng (hoặc loại dòng) → bộ ô thông số phải theo mẫu của kiểu
        # hàng mới. Onchange chỉ lo được form; đây là đường cho import/RPC/code.
        if {"reference_product_id", "product_type"} & vals.keys():
            self._dlm_sync_params()

        # Làn tự động phải soi lại sau MỌI thay đổi yêu cầu — cả chiều chốt lẫn
        # chiều bỏ chốt. `dlm_skip_autoresolve` cắt đệ quy khi chính nó đang ghi.
        if not self.env.context.get("dlm_skip_autoresolve"):
            self._dlm_try_autoresolve()

        if "attachment_ids" in vals:
            self._stamp_attachments()

        if auto_supplement_done:
            auto_supplement_done.write({"supplement_done": True})
        if auto_needs_review:
            auto_needs_review._flag_needs_review()

        if {"resolved_product_id", "resolved_bom_id", "is_infeasible",
                "supplement_note", "supplement_done", "needs_review"} & set(vals.keys()):
            self.mapped("quotation_request_id")._recompute_status_from_lines()

        return res

    def _flag_needs_review(self):
        """Đặt cờ "cần xem lại" + notify Kỹ thuật đang phụ trách RFQ. Tách riêng
        khỏi write() gốc để lần write này (chỉ đổi needs_review) không rơi vào
        gate quyền và tự kích hoạt recompute trạng thái RFQ."""
        self.write({"needs_review": True})
        for rec in self:
            request = rec.quotation_request_id
            name = rec.product_name or rec.display_name
            request.message_post(body=_(
                "Sales đã sửa yêu cầu dòng <b>%s</b> sau khi Kỹ thuật đã xác "
                "định — cần xem lại kết quả (Sản phẩm/BOM có thể không còn khớp)."
            ) % name)
            if request.received_by:
                request.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Xem lại dòng %s (Sales đã sửa yêu cầu)") % name,
                    user_id=request.received_by.id,
                )

    def unlink(self):
        # Chặn Sales xóa THẲNG dòng đã có kết quả kỹ thuật (đã xác định SP/BOM,
        # đang chờ xem lại, hoặc đã kết luận không khả thi) — mất công Kỹ thuật
        # mà không ghi nhận. Loại dòng phải đi qua "Loại khỏi phạm vi"
        # (action_remove_from_scope) để có chatter + notify KTV. RFQ Mới/Đã hủy
        # thì cho xóa tự do (chưa có gì để mất).
        if not self.env.su and not self.env.context.get("dl_rfq_scope_removal"):
            for rec in self:
                request = rec.quotation_request_id
                if request.status in ("new", "cancelled"):
                    continue
                if rec.is_infeasible or rec.resolved_product_id:
                    raise UserError(_(
                        "Dòng “%s” đã có kết quả kỹ thuật. Dùng nút “Loại khỏi "
                        "phạm vi” để loại dòng (có ghi nhận và thông báo Kỹ "
                        "thuật), không xóa trực tiếp.")
                        % (rec.product_name or rec.display_name))

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

    def _ensure_tech_processable(self):
        """Cổng chung cho mọi thao tác kỹ thuật trên dòng (workspace + kết luận
        nhanh): tự tiếp nhận RFQ Mới/Đã bổ sung, chặn trạng thái đã đóng."""
        self.ensure_one()
        request = self.quotation_request_id
        if request.status in ("new", "supplemented"):
            request.action_receive()
        if request.status not in ("processing", "confirmed", "returned"):
            raise UserError(_(
                "RFQ ở trạng thái hiện tại không thể xử lý kỹ thuật."))

    def _check_tech_result_writable(self):
        """Chốt kiểm LẠI trước khi ghi bất kỳ kết luận kỹ thuật nào (RES-002).

        Wizard/workspace mở lâu; giữa chừng Sales có thể hủy RFQ hoặc đã tạo
        báo giá. Kiểm lúc mở là chưa đủ — không kiểm lại thì kết luận rơi vào
        một RFQ đã đóng."""
        self.ensure_one()
        request = self.quotation_request_id
        if request.status == "cancelled":
            raise UserError(_(
                "Yêu cầu báo giá %s đã bị hủy — không thể ghi kết luận kỹ thuật.")
                % request.name)
        if request.status == "quoted":
            raise UserError(_(
                "Yêu cầu báo giá %s đã được tạo báo giá — không thể đổi kết "
                "luận kỹ thuật. Hãy làm phiên bản báo giá mới.") % request.name)

    def _mark_supplement(self, note):
        """Đánh dấu dòng cần Sales bổ sung + notify (chatter + activity cho
        người tạo RFQ) — dùng chung cho workspace và wizard kết luận nhanh."""
        self.ensure_one()
        self._check_tech_result_writable()
        note = (note or "").strip()
        if not note:
            raise UserError(_("Vui lòng nhập nội dung cần Sales bổ sung."))
        if self.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý kỹ thuật."))
        # supplement_done=False: câu hỏi bổ sung MỚI, chờ Sales xử lý (kể cả khi
        # dòng vừa được Sales bổ sung xong mà Kỹ thuật vẫn thấy thiếu).
        self.write({"supplement_note": note, "supplement_done": False})
        request = self.quotation_request_id
        request.message_post(body=_(
            "Kỹ thuật yêu cầu bổ sung cho dòng <b>%s</b>: %s"
        ) % (self.product_name or "", note))
        if request.created_by:
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Bổ sung thông tin dòng %s") % (
                    self.product_name or request.name),
                note=note,
                user_id=request.created_by.id,
            )

    def _mark_infeasible(self, reason):
        """Kết luận dòng không khả thi + notify — trước đây kết luận này hoàn
        toàn im lặng (Sales chỉ phát hiện khi RFQ sang Đã xử lý xong), giờ
        notify như supplement vì Sales cần biết sớm để trao đổi lại với khách."""
        self.ensure_one()
        self._check_tech_result_writable()
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("Vui lòng nhập lý do không khả thi."))
        if self.product_type == "trading":
            raise UserError(_(
                "Dòng Sản phẩm thương mại không xử lý kỹ thuật."))
        self.write({
            "is_infeasible": True,
            "infeasible_reason": reason,
            "resolved_product_id": False,
            "resolved_bom_id": False,
            "supplement_note": False,
            "supplement_done": False,
            "needs_review": False,
        })
        self._cleanup_rfq_provisional_records()
        request = self.quotation_request_id
        request.message_post(body=_(
            "Kỹ thuật kết luận dòng <b>%s</b> không khả thi: %s"
        ) % (self.product_name or "", reason))
        if request.created_by:
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Dòng %s không khả thi — trao đổi lại với khách") % (
                    self.product_name or request.name),
                note=reason,
                user_id=request.created_by.id,
            )

    def _action_open_quick_wizard(self, wizard_model, name):
        """Mở wizard kết luận nhanh (modal chỉ hỏi lý do) cho dòng này."""
        self._ensure_tech_processable()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": wizard_model,
            "view_mode": "form",
            "target": "new",
            "context": {"default_rfq_line_id": self.id},
        }

    def action_open_supplement_wizard(self):
        """Kết luận nhanh "cần Sales bổ sung" — quyết định nông, không bắt KTV
        đi qua workspace 3 bước."""
        return self._action_open_quick_wizard(
            "dl.rfq.line.supplement.wizard",
            _("Yêu cầu bổ sung — %s") % (self.product_name or ""))

    def action_open_infeasible_wizard(self):
        """Kết luận nhanh "không khả thi" ngay tại nơi KTV vừa đọc thông tin."""
        return self._action_open_quick_wizard(
            "dl.rfq.line.infeasible.wizard",
            _("Không khả thi — %s") % (self.product_name or ""))

    def action_open_resolve_wizard(self):
        """Mở workspace Product + BOM và tự tiếp nhận RFQ khi cần.

        Với RFQ Mới/Đã bổ sung, chính thao tác Xử lý là ý định nhận việc rõ
        ràng nên hệ thống ghi người + thời điểm trước khi mở workspace. RFQ đã
        Đang xử lý/Đã xử lý xong chỉ được mở lại, không đổi người phụ trách.
        """
        self._ensure_tech_processable()
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

    def action_remove_from_scope(self):
        """Sales loại một dòng đã có kết quả kỹ thuật khỏi phạm vi RFQ — đây là
        con đường DUY NHẤT để bỏ dòng như vậy (unlink thẳng bị chặn), có ghi
        chatter + notify người phụ trách để công Kỹ thuật không biến mất âm thầm.
        Dùng chung cho dòng không khả thi (loại trước khi Tạo báo giá) lẫn dòng
        đã xác định (khách đổi ý)."""
        self.ensure_one()
        request = self.quotation_request_id
        if request.status in ("quoted", "cancelled"):
            raise UserError(_(
                "Không thể thay đổi phạm vi RFQ đã tạo báo giá hoặc đã hủy."))
        name = self.product_name or self.display_name
        had_tech_work = bool(self.resolved_product_id or self.is_infeasible)
        request.message_post(body=_(
            "Sales loại dòng <b>%s</b> khỏi phạm vi RFQ.") % name)
        if had_tech_work and request.received_by:
            request.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Dòng %s đã bị loại khỏi RFQ (Sales)") % name,
                user_id=request.received_by.id,
            )
        self.with_context(dl_rfq_scope_removal=True).unlink()
        return {"type": "ir.actions.client", "tag": "soft_reload"}


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


class DlQuotationRequestLineParam(models.Model):
    """Giá trị tham số Sales nhập cho một dòng RFQ gia công.

    Song sinh BỀN của `dl.rfq.resolve.param` (bản tạm trong workspace Kỹ thuật).
    Tồn tại vì đề bài phải đi cùng yêu cầu: Sales gõ "Dài 1200 / Rộng 400 /
    Cao 670" vào ô có nhãn do chính BOM mẫu định nghĩa, thay vì viết vào văn bản
    tự do rồi để hệ thống regex đoán lại.

    Các field mô tả (`code`, `name`, `dim_role`, miền hợp lệ) được CHÉP từ
    `dl.bom.template.param` chứ không related: mẫu có thể lên phiên bản mới hoặc
    đổi miền hợp lệ sau khi Sales đã gửi RFQ, và khi đó đề bài khách đưa vẫn
    phải đọc được nguyên trạng như lúc nhận."""

    _name = "dl.quotation.request.line.param"
    _description = "Tham số dòng yêu cầu báo giá"
    _order = "sequence, id"

    _sql_constraints = [
        ("line_code_uniq", "unique(line_id, code)",
         "Mỗi tham số chỉ được khai một lần trên cùng một dòng yêu cầu."),
    ]

    line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ",
        required=True,
        ondelete="cascade",
        index=True,
    )
    template_param_id = fields.Many2one(
        "dl.bom.template.param",
        string="Tham số mẫu",
        ondelete="set null",
    )
    sequence = fields.Integer(string="Thứ tự", default=10)
    code = fields.Char(string="Mã", required=True)
    name = fields.Char(string="Tham số")
    # Chép từ mẫu để bộ dò khớp đọc được kích thước mà không phải join ngược lên
    # template_param_id (bản ghi mẫu có thể đã bị đổi/xoá sau khi RFQ gửi đi).
    dim_role = fields.Selection(
        [
            ("length", "Chiều dài"),
            ("width", "Chiều rộng"),
            ("height", "Chiều cao"),
            ("thickness", "Độ dày"),
            ("side", "Cạnh"),
            ("none", "— (không tự đọc)"),
        ],
        string="Vai trò kích thước", default="none",
    )
    value = fields.Float(string="Giá trị")
    value_min = fields.Float(string="Tối thiểu")
    value_max = fields.Float(string="Tối đa")
    required = fields.Boolean(string="Bắt buộc", default=True)

    range_hint = fields.Char(string="Miền hợp lệ", compute="_compute_range_hint")

    @api.depends("value_min", "value_max")
    def _compute_range_hint(self):
        for rec in self:
            if rec.value_min and rec.value_max:
                rec.range_hint = "%g – %g" % (rec.value_min, rec.value_max)
            elif rec.value_min:
                rec.range_hint = "≥ %g" % rec.value_min
            elif rec.value_max:
                rec.range_hint = "≤ %g" % rec.value_max
            else:
                rec.range_hint = ""

    # Ngoài miền hợp lệ là CẢNH BÁO MỀM, không phải lỗi: khách đặt cỡ đặc biệt
    # là chuyện có thật, và Sales không được quyền phán cỡ nào làm được. Dòng
    # ngoài miền tự rớt xuống làn "chưa từng làm" để Kỹ thuật xem tận nơi.
    out_of_range = fields.Boolean(
        string="Ngoài miền hợp lệ", compute="_compute_out_of_range")

    @api.depends("value", "value_min", "value_max")
    def _compute_out_of_range(self):
        for rec in self:
            if not rec.value:
                rec.out_of_range = False
                continue
            below = rec.value_min and rec.value < rec.value_min
            above = rec.value_max and rec.value > rec.value_max
            rec.out_of_range = bool(below or above)

    def write(self, vals):
        """Đổi một con số ⇒ soi lại làn tự động của DÒNG cha.

        Form Sales sửa ô thông số bằng lệnh o2m nên đã đi qua `write()` của
        dòng, nhưng ghi thẳng vào bản ghi tham số (RPC, import, code) thì không
        — mà đó chính là đường làm lệch đề bài mà không ai báo động. Đây là
        chốt chặn cho mọi đường ghi."""
        res = super().write(vals)
        if "value" in vals:
            self.mapped("line_id")._dlm_try_autoresolve()
        return res

    @api.constrains("value")
    def _check_value_not_negative(self):
        """Kích thước âm không có nghĩa gì, và nếu lọt xuống bộ sinh định mức thì
        ra định mức âm — báo giá âm tiền mà không chỗ nào nổ."""
        for rec in self:
            if rec.value < 0:
                raise ValidationError(_(
                    "Tham số \"%s\" không được là số âm.") % (rec.name or rec.code))
