from odoo import _, models
from odoo.exceptions import UserError


class DlBom(models.Model):
    """Mở rộng dl.bom TỪ dl_sale (chiều phụ thuộc đúng: dl_sale → dl_technical).

    Chặn cứng hạ-nháp/sửa một BOM đã được báo giá hoặc đơn hàng chốt tham chiếu
    — bảo toàn lịch sử: đơn cũ phải luôn truy được đúng BOM đã dùng (thiết kế
    BOM truy xuất §6/§9). Muốn đổi thiết kế → tạo phiên bản mới.
    """

    _inherit = "dl.bom"

    def _check_can_reset_draft(self):
        for rec in self:
            # Đơn bán hàng đang hiệu lực (đã xác nhận/hoàn tất) dùng BOM này.
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
