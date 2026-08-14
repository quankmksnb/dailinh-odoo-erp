from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .dl_quotation import _COST_GROUPS


class DlPricingApprovalRequest(models.Model):
    """Bridge dl_sale (cùng pattern §17.7): nhúng chi tiết báo giá vào form
    Yêu cầu phê duyệt để người duyệt (Trưởng KD/Giám đốc) thấy ngay báo giá
    cấu thành từ gì — dòng, giá thành, markup, giá sàn, chiết khấu, cấu phần
    snapshot — không phải tự lục nhiều màn. Model gốc (dl_config) không biết
    dl.quotation nên phần này phải nằm ở dl_sale.
    """

    _inherit = "dl.pricing.approval.request"

    # store=True: res_model/res_id bất biến sau khi tạo nên lưu an toàn; đồng
    # thời làm field searchable — ORM cần thế để resolve các related q_* dưới.
    quotation_id = fields.Many2one(
        "dl.quotation", string="Báo giá", compute="_compute_quotation_id",
        store=True, ondelete="set null")

    # --- Related readonly: bức tranh tiền của báo giá cho người duyệt ---
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

    # --- Nhóm chi phí nội bộ: giữ đúng hàng rào groups như trên báo giá ---
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
    # Cùng bộ số của trang "Phân tích giá thành" (form Báo giá): lãi gộp, cơ
    # cấu 3 lớp chi phí, markup niêm yết/tại giá sàn và bản diễn giải "công
    # thức" theo từng sản phẩm. Người duyệt cần đọc giá cấu thành từ đâu ngay
    # tại màn quyết định, không phải mở lại báo giá đầy đủ.
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
    # sanitize=False khớp field nguồn: nội dung do server dựng (Markup), không
    # phải người dùng nhập — sanitize sẽ cắt mất cấu trúc <details>/<summary>.
    q_cost_breakdown_html = fields.Html(
        related="quotation_id.cost_breakdown_html", sanitize=False,
        groups=_COST_GROUPS)

    # --- SLA: tuổi chờ duyệt cho hòm phê duyệt (review UX inbox #f1) ---
    # Người duyệt cần biết yêu cầu đã chờ bao lâu để ưu tiên; sắp theo "tuổi"
    # tương đương sắp theo cột "Ngày gửi" (create_date) sẵn có.
    waiting_days = fields.Integer(
        string='Chờ (ngày)', compute='_compute_waiting_days')

    @api.depends('create_date', 'state', 'resolved_at')
    def _compute_waiting_days(self):
        now = fields.Datetime.now()
        for req in self:
            if req.state == 'pending' and req.create_date:
                req.waiting_days = (now - req.create_date).days
            else:
                req.waiting_days = 0

    # --- Tóm tắt rủi ro dạng chip cho dòng danh sách (review UX inbox #f2) ---
    # Thay "Cấp duyệt" trơ bằng lý do cụ thể (vượt trần chiết khấu / dưới giá
    # sàn). Đọc qua sudo vì below_floor gated _COST_GROUPS — nhãn gộp này chỉ
    # hiện ở cột có groups=_COST_GROUPS trong tree nên không lộ ngoài phạm vi.
    risk_summary = fields.Char(
        string='Rủi ro', compute='_compute_risk_summary')

    @api.depends('quotation_id.below_floor', 'quotation_id.discount_above_max')
    def _compute_risk_summary(self):
        for req in self:
            q = req.quotation_id.sudo()
            parts = []
            if q and q.discount_above_max:
                parts.append(_('Vượt trần chiết khấu'))
            if q and q.below_floor:
                parts.append(_('Dưới giá sàn'))
            req.risk_summary = ' · '.join(parts)

    # --- Cờ "trong ngưỡng an toàn" KHÔNG gated để badge success hiện cho mọi
    # người duyệt. Gộp cả "dưới giá sàn" (gated _COST_GROUPS) qua sudo nên
    # badge phản ánh đúng, nhưng chỉ lộ ra dạng boolean an toàn/không — không
    # để lộ con số giá sàn ra ngoài phạm vi. Tránh tham chiếu q_below_floor
    # trực tiếp trong modifier của element không gated (gây lỗi validate view).
    q_in_safe_range = fields.Boolean(
        string='Trong ngưỡng an toàn', compute='_compute_q_in_safe_range')

    @api.depends('quotation_id.below_floor', 'quotation_id.discount_above_max')
    def _compute_q_in_safe_range(self):
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
