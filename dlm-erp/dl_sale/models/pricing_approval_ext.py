from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .dl_quotation import _COST_GROUPS


class DlPricingApprovalRequest(models.Model):
    """Nhồi toàn bộ số liệu báo giá vào form màn Phê duyệt báo giá.

    Người duyệt (Trưởng KD/Giám đốc) nhìn một màn là thấy đủ: dòng hàng, giá
    thành, markup, giá sàn, chiết khấu, cấu phần — khỏi phải mở ngược sang báo
    giá. Model yêu cầu duyệt gốc nằm ở dl_config, không biết tới dl.quotation,
    nên phần nối này phải đặt ở dl_sale."""

    _inherit = "dl.pricing.approval.request"

    # store=True vì res_model/res_id không đổi sau khi tạo nên lưu an toàn, và
    # ORM cần field này searchable để nối được đám related q_* bên dưới.
    quotation_id = fields.Many2one(
        "dl.quotation", string="Báo giá", compute="_compute_quotation_id",
        store=True, ondelete="set null")

    # --- Chiếu số của báo giá sang màn duyệt (chỉ đọc) ---
    q_partner_id = fields.Many2one(related="quotation_id.partner_id",
                                   string="Khách hàng")
    q_currency_id = fields.Many2one(related="quotation_id.currency_id")
    q_date_order = fields.Date(related="quotation_id.date_order",
                               string="Ngày báo giá")
    q_state = fields.Selection(related="quotation_id.state",
                               string="Trạng thái báo giá")
    q_line_ids = fields.One2many(related="quotation_id.line_ids",
                                 string="Dòng báo giá")
    q_amount_untaxed = fields.Float(related="quotation_id.amount_untaxed")
    q_discount_pct = fields.Float(related="quotation_id.discount_pct",
                                  string="Chiết khấu (%)")
    q_discount_amount = fields.Float(related="quotation_id.discount_amount")
    q_amount_before_vat = fields.Float(related="quotation_id.amount_before_vat")
    q_vat_pct = fields.Float(related="quotation_id.vat_pct", string="VAT (%)")
    q_vat_amount = fields.Float(related="quotation_id.vat_amount")
    q_amount_total = fields.Float(related="quotation_id.amount_total")
    q_discount_default_rate = fields.Float(
        related="quotation_id.discount_default_rate")
    q_discount_max_rate = fields.Float(related="quotation_id.discount_max_rate")
    q_discount_above_default = fields.Boolean(
        related="quotation_id.discount_above_default")
    q_discount_above_max = fields.Boolean(
        related="quotation_id.discount_above_max")
    q_partner_group = fields.Selection(related="quotation_id.partner_group",
                                       string="Nhóm khách hàng")

    # --- Nhóm giá vốn: giữ nguyên hàng rào groups như trên báo giá, không để
    #     lộ giá vốn cho người không được xem ---
    q_total_cost = fields.Float(related="quotation_id.total_cost",
                                groups=_COST_GROUPS)
    q_target_markup = fields.Float(related="quotation_id.target_markup",
                                   groups=_COST_GROUPS)
    q_effective_markup = fields.Float(related="quotation_id.effective_markup",
                                      groups=_COST_GROUPS)
    q_floor_amount = fields.Float(related="quotation_id.floor_amount",
                                  groups=_COST_GROUPS)
    q_below_floor = fields.Boolean(related="quotation_id.below_floor",
                                   groups=_COST_GROUPS)
    # Đúng bộ số của trang Phân tích giá thành bên form Báo giá: lãi gộp, cơ
    # cấu 3 lớp chi phí, markup niêm yết/tại giá sàn, và bảng công thức theo
    # từng sản phẩm — để người duyệt đọc giá cấu thành từ đâu ngay tại chỗ.
    q_gross_profit = fields.Float(related="quotation_id.gross_profit",
                                  groups=_COST_GROUPS)
    q_list_markup = fields.Float(related="quotation_id.list_markup",
                                 groups=_COST_GROUPS)
    q_floor_markup = fields.Float(related="quotation_id.floor_markup",
                                  groups=_COST_GROUPS)
    q_cost_material_total = fields.Float(
        related="quotation_id.cost_material_total", groups=_COST_GROUPS)
    q_cost_operation_total = fields.Float(
        related="quotation_id.cost_operation_total", groups=_COST_GROUPS)
    q_cost_adjustment_total = fields.Float(
        related="quotation_id.cost_adjustment_total", groups=_COST_GROUPS)
    # sanitize=False y như field nguồn: HTML do server tự dựng, không phải
    # người dùng nhập; bật sanitize sẽ cắt mất cấu trúc <details>/<summary>.
    q_cost_breakdown_html = fields.Html(
        related="quotation_id.cost_breakdown_html", sanitize=False,
        groups=_COST_GROUPS)

    # Cột "Chờ (ngày)" trên danh sách Phê duyệt báo giá — để người duyệt biết
    # yêu cầu nào để lâu mà ưu tiên. Sắp theo cột này tương đương sắp theo ngày
    # gửi.
    waiting_days = fields.Integer(
        string='Chờ (ngày)', compute='_compute_waiting_days')

    @api.depends('create_date', 'state', 'resolved_at')
    def _compute_waiting_days(self):
        """Số ngày đang chờ; đã xử lý xong thì về 0."""
        now = fields.Datetime.now()
        for req in self:
            if req.state == 'pending' and req.create_date:
                req.waiting_days = (now - req.create_date).days
            else:
                req.waiting_days = 0

    # Cột "Rủi ro" trên danh sách Phê duyệt — nói thẳng vì sao phải duyệt
    # (vượt trần chiết khấu / dưới giá sàn) thay cho "Cấp duyệt" chung chung.
    # Đọc qua sudo vì below_floor bị chắn theo _COST_GROUPS; cột này cũng gắn
    # groups=_COST_GROUPS nên không lộ ra ngoài phạm vi được xem giá vốn.
    risk_summary = fields.Char(
        string='Rủi ro', compute='_compute_risk_summary')

    @api.depends('quotation_id.below_floor', 'quotation_id.discount_above_max')
    def _compute_risk_summary(self):
        """Ghép nhãn rủi ro: vượt trần chiết khấu và/hoặc dưới giá sàn."""
        for req in self:
            q = req.quotation_id.sudo()
            parts = []
            if q and q.discount_above_max:
                parts.append(_('Vượt trần chiết khấu'))
            if q and q.below_floor:
                parts.append(_('Dưới giá sàn'))
            req.risk_summary = ' · '.join(parts)

    # Cờ "trong ngưỡng an toàn" để hiện badge xanh cho MỌI người duyệt, nên
    # KHÔNG gắn groups. Nó gộp cả "dưới giá sàn" (vốn bị chắn) qua sudo, nhưng
    # chỉ phơi ra dạng đúng/sai — không lộ con số giá sàn. Phải có field riêng
    # thế này vì nếu view không-gated tham chiếu thẳng q_below_floor thì Odoo
    # báo lỗi kiểm tra view.
    q_in_safe_range = fields.Boolean(
        string='Trong ngưỡng an toàn', compute='_compute_q_in_safe_range')

    @api.depends('quotation_id.below_floor', 'quotation_id.discount_above_max')
    def _compute_q_in_safe_range(self):
        """An toàn = không vượt trần chiết khấu và không dưới giá sàn."""
        for req in self:
            q = req.quotation_id.sudo()
            req.q_in_safe_range = bool(q) and not q.discount_above_max \
                and not q.below_floor

    @api.depends("res_model", "res_id")
    def _compute_quotation_id(self):
        Quotation = self.env["dl.quotation"]
        for req in self:
            req.quotation_id = (
                Quotation.browse(req.res_id).exists()
                if req.res_model == "dl.quotation" and req.res_id else Quotation
            )

    def action_open_quotation(self):
        """Nút mở báo giá gắn với yêu cầu duyệt này."""
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_("Yêu cầu này không gắn với báo giá nào."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Báo giá"),
            "res_model": "dl.quotation",
            "view_mode": "form",
            "res_id": self.quotation_id.id,
            "target": "current",
        }
