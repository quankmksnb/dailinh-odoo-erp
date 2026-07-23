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
    q_component_ids = fields.One2many(related="quotation_id.component_ids",
                                      string="Cấu phần giá")
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
