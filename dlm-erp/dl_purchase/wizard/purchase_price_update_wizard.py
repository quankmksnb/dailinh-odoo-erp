# -*- coding: utf-8 -*-
"""Chốt giá vừa mua thành giá hiện hành — một bước, ngay trên đơn mua."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class DlPurchasePriceUpdateWizard(models.TransientModel):
    _name = "dl.purchase.price.update.wizard"
    _description = "Cập nhật bảng giá từ giá vừa chốt"

    order_id = fields.Many2one("dl.purchase.order", required=True, readonly=True)
    line_ids = fields.One2many(
        "dl.purchase.price.update.wizard.line", "wizard_id", string="Mặt hàng")

    def action_confirm(self):
        """Ghi giá vào bảng giá nhà cung cấp theo lựa chọn từng dòng.

        Vì sao MỘT bước chứ không đẻ dòng nháp rồi bắt sang màn khác duyệt:
        người duyệt bảng giá nhà cung cấp CŨNG LÀ nhóm Mua hàng
        (`_check_price_manager`) — tức là người vừa chốt đơn tự duyệt chính
        mình. Ba cú bấm qua hai màn mà không thêm một lớp kiểm soát nào thì đó
        là nghi lễ, không phải quản trị.

        Cái §6.6 của doc cấm là ghi ngược TỰ ĐỘNG, âm thầm. Modal này bày ra
        giá cũ, giá mới, chênh lệch và số lượng chuyến hàng rồi mới ghi — đúng
        là "một quyết định kinh doanh", chỉ không bắt đi vòng."""
        self.ensure_one()
        Row = self.env["product.supplierinfo"]
        order = self.order_id
        ap_dung, luu_su = Row, Row
        for line in self.line_ids.filtered("selected"):
            row = Row.sudo().create({
                "partner_id": order.partner_id.id,
                "product_tmpl_id": line.product_id.product_tmpl_id.id,
                "product_id": line.product_id.id,
                "price": line.new_price,
                "date_start": fields.Date.context_today(self),
                "approval_state": "draft",
                "dlm_source_note": order._dlm_price_source_note(),
            })
            if line.apply_now:
                # Đi qua đúng action thật (kiểm quyền, đóng ngày giá cũ), không
                # ghi thẳng state — luồng duyệt là chỗ dễ vỡ, đi vòng qua nó thì
                # hỏng gì cũng không lộ ra.
                row.action_approve()
                if not row.is_applied:
                    row.action_set_applied()
                ap_dung |= row
            else:
                luu_su |= row
        if not (ap_dung or luu_su):
            raise UserError(_("Chưa chọn mặt hàng nào để cập nhật giá."))
        order.message_post(body=self._ghi_chu(ap_dung, luu_su))
        return {"type": "ir.actions.act_window_close"}

    def _ghi_chu(self, ap_dung, luu_su):
        phan = []
        if ap_dung:
            phan.append(_("<b>Áp dụng làm giá hiện hành:</b> %s") % ", ".join(
                "%s → %s" % (r.product_id.display_name,
                             "{:,.0f}".format(r.price).replace(",", "."))
                for r in ap_dung))
        if luu_su:
            phan.append(_("<b>Chỉ lưu lịch sử (chuyến mua cá biệt):</b> %s")
                        % ", ".join(luu_su.mapped("product_id.display_name")))
        return "<p>Cập nhật bảng giá từ đơn mua này.</p><p>%s</p>" % "</p><p>".join(phan)


class DlPurchasePriceUpdateWizardLine(models.TransientModel):
    _name = "dl.purchase.price.update.wizard.line"
    _description = "Dòng cập nhật bảng giá"

    wizard_id = fields.Many2one(
        "dl.purchase.price.update.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Mặt hàng", readonly=True)
    qty = fields.Float(string="SL chuyến này", readonly=True,
                       digits="Product Unit of Measure")
    old_price = fields.Float(string="Giá đang áp dụng", readonly=True,
                             digits="Product Price")
    new_price = fields.Float(string="Giá vừa chốt", readonly=True,
                             digits="Product Price")
    gap_pct = fields.Float(string="Chênh (%)", readonly=True, digits=(5, 1))
    selected = fields.Boolean(string="Cập nhật", default=True)
    # Mặc định ÁP DỤNG: giá từ một đơn mua đã chốt là bằng chứng mạnh nhất có
    # thể có. Bỏ tick khi chuyến này cá biệt (mua gấp, mua lẻ, số lượng nhỏ) —
    # lúc đó vẫn lưu vào bảng giá làm lịch sử nhưng không thành giá chào khách.
    apply_now = fields.Boolean(string="Áp dụng ngay", default=True)

    @api.depends("old_price", "new_price")
    def _compute_gap(self):
        for line in self:
            line.gap_pct = ((line.new_price - line.old_price) / line.old_price
                            * 100.0) if line.old_price else 0.0
