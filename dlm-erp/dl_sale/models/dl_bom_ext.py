from odoo import _, models
from odoo.exceptions import UserError


class DlBom(models.Model):
    """Chặn hạ-nháp/sửa một BOM đã có báo giá đồng ý hoặc đơn hàng dùng.

    Đơn cũ phải luôn tra được đúng BOM đã làm, nên BOM đã "bị dùng" thì đóng
    lại; muốn đổi thiết kế thì tạo phiên bản mới. Việc nối BOM ↔ báo giá/đơn
    nằm ở dl_sale (module thấy được cả hai), nên chặn đặt ở đây."""

    _inherit = "dl.bom"

    def _check_can_reset_draft(self):
        """Chặn nếu BOM đã bị đơn (đã xác nhận/hoàn tất) hoặc báo giá (khách đã
        đồng ý/đã lên đơn) dùng tới."""
        for rec in self:
            # Đơn bán đang hiệu lực dùng BOM này.
            order_line = self.env["dl.sale.order.line"].sudo().search(
                [
                    ("bom_id", "=", rec.id),
                    ("order_id.state", "in", ("confirmed", "done")),
                ],
                limit=1,
            )
            if order_line:
                raise UserError(_(
                    "BOM này đã được đơn hàng %s sử dụng — không thể sửa/hạ nháp. "
                    "Hãy tạo phiên bản mới để thay đổi thiết kế."
                ) % order_line.order_id.name)
            # Báo giá khách đã đồng ý / đã lên đơn dùng BOM này.
            quote_line = self.env["dl.quotation.line"].sudo().search(
                [
                    ("bom_id", "=", rec.id),
                    ("quotation_id.state", "in", ("accepted", "ordered")),
                ],
                limit=1,
            )
            if quote_line:
                raise UserError(_(
                    "BOM này đã được báo giá %s (khách đồng ý) sử dụng — không thể "
                    "sửa/hạ nháp. Hãy tạo phiên bản mới."
                ) % quote_line.quotation_id.name)
        return super()._check_can_reset_draft()
