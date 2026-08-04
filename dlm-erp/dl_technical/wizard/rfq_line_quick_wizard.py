from odoo import api, fields, models


class DlRfqLineQuickWizardBase(models.AbstractModel):
    """Phần chung của 2 wizard kết luận nhanh trên dòng RFQ (modal chỉ hỏi
    lý do) — đường tắt cho quyết định NÔNG mà KTV đưa ra ngay khi vừa đọc
    thông tin dòng, không bắt đi qua workspace 3 bước. Quyết định sâu (chọn/
    tạo Product + BOM) vẫn đi qua dl.rfq.resolve.wizard."""

    _name = "dl.rfq.line.quick.wizard.base"
    _description = "Kết luận nhanh dòng RFQ — phần chung"

    rfq_line_id = fields.Many2one(
        "dl.quotation.request.line",
        string="Dòng RFQ",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    # Bối cảnh chỉ đọc — nhắc lại yêu cầu Sales ngay trong modal để KTV viết
    # lý do/nội dung sát với thông tin đang thiếu.
    request_product_name = fields.Char(
        related="rfq_line_id.product_name", string="Tên sản phẩm", readonly=True)
    request_dimension_note = fields.Text(
        related="rfq_line_id.dimension_note", string="Kích thước / Yêu cầu",
        readonly=True)

    def _action_return_to_rfq(self):
        """Đóng modal và nạp lại form RFQ để badge/tiến độ/alert cập nhật."""
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


class DlRfqLineSupplementWizard(models.TransientModel):
    _name = "dl.rfq.line.supplement.wizard"
    _inherit = "dl.rfq.line.quick.wizard.base"
    _description = "Yêu cầu Sales bổ sung thông tin cho dòng RFQ"

    supplement_note = fields.Text(string="Nội dung cần bổ sung")

    @api.model
    def default_get(self, fields_list):
        # Mở lại dòng đã có yêu cầu bổ sung → nạp nội dung cũ để sửa tiếp.
        res = super().default_get(fields_list)
        line_id = res.get("rfq_line_id") or self.env.context.get("default_rfq_line_id")
        if line_id and "supplement_note" in fields_list:
            line = self.env["dl.quotation.request.line"].browse(line_id)
            if line.exists() and line.supplement_note:
                res["supplement_note"] = line.supplement_note
        return res

    def action_confirm(self):
        self.ensure_one()
        self.rfq_line_id._mark_supplement(self.supplement_note)
        return self._action_return_to_rfq()


class DlRfqLineInfeasibleWizard(models.TransientModel):
    _name = "dl.rfq.line.infeasible.wizard"
    _inherit = "dl.rfq.line.quick.wizard.base"
    _description = "Kết luận không khả thi cho dòng RFQ"

    infeasible_reason = fields.Text(string="Lý do không khả thi")
    # Cảnh báo khi dòng đã có kết quả Product/BOM — xác nhận sẽ xóa kết quả đó.
    resolved_product_id = fields.Many2one(
        related="rfq_line_id.resolved_product_id",
        string="Sản phẩm đã xác định", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_id = res.get("rfq_line_id") or self.env.context.get("default_rfq_line_id")
        if line_id and "infeasible_reason" in fields_list:
            line = self.env["dl.quotation.request.line"].browse(line_id)
            if line.exists() and line.infeasible_reason:
                res["infeasible_reason"] = line.infeasible_reason
        return res

    def action_confirm(self):
        self.ensure_one()
        self.rfq_line_id._mark_infeasible(self.infeasible_reason)
        return self._action_return_to_rfq()
