# -*- coding: utf-8 -*-
"""K19/K20 — Phiếu nhận hàng biết mình đến từ đơn mua nào, và đóng giá lên lô.

Thiết kế: ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §8.

⚠️ Phiếu nhận **vẫn tạo tay được** (NCC giao không đơn, hàng mẫu):
``dlm_purchase_order_id`` để trống và mọi lá chắn hiện có không đổi. Đơn mua chỉ
THÊM một nguồn gốc cho phiếu vốn đang tạo tay — không thay thế nó.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .dl_purchase_order import _DLM_BUY_PRICE_GROUPS


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dlm_purchase_order_id = fields.Many2one(
        "dl.purchase.order", string="Đơn mua nguồn", readonly=True, copy=False,
        index=True, ondelete="set null")
    dlm_purchase_name = fields.Char(
        string="Đơn mua", related="dlm_purchase_order_id.name", readonly=True,
        help="Nhân bản để thủ kho THẤY được số đơn mua mà không cần quyền đọc "
             "đơn mua — trên đó có giá.")

    def button_validate(self):
        """Xác nhận phiếu nhận ⇒ đóng giá mua lên từng lô vừa sinh ra.

        🔴 Đóng ở phiếu [1] chứ không phải [2] Kiểm & cất: lô SINH RA ở đây
        (``_dlm_autofill_lots`` chỉ chạy cho ``code == 'incoming'``). Đóng ở
        bước sau nghĩa là lô sống một quãng không có giá — và đúng quãng đó hàng
        có thể bị tách sang khu Chờ trả NCC.
        """
        result = super().button_validate()
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            picking._dlm_stamp_lot_costs()
        return result

    def _dlm_stamp_lot_costs(self):
        """Gán giá cho mọi lô của phiếu nhận này.

        Không có đơn mua ⇒ vẫn đóng giá, lấy từ bảng giá NCC và gắn cờ ƯỚC TÍNH
        (MH-16). Để trống thì báo cáo giá vốn im lặng tính lô đó bằng 0.
        """
        self.ensure_one()
        order = self.dlm_purchase_order_id.sudo()
        prices = {}
        if order:
            for line in order.line_ids:
                prices[line.product_id.id] = line.price_unit
        for move_line in self.move_line_ids:
            lot = move_line.lot_id
            if not lot:
                continue
            unit_cost = prices.get(move_line.product_id.id)
            if unit_cost:
                lot._dlm_stamp_cost(unit_cost, purchase_order=order)
            else:
                lot._dlm_stamp_cost(lot._dlm_fallback_cost())
        return True

    # ------------------------------------------------------------------
    # Điều hướng
    # ------------------------------------------------------------------
    def action_dlm_open_purchase_order(self):
        """Từ phiếu nhận về đơn mua — chỉ Mua hàng/CEO/Admin/Kế toán mở được.

        Nút này gated ở view; đây là lá chắn tầng server cho đường gọi khác.
        """
        self.ensure_one()
        if not self.dlm_purchase_order_id:
            raise UserError(_("Phiếu %s không gắn đơn mua nào.") % self.name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Đơn mua %s") % self.dlm_purchase_order_id.name,
            "res_model": "dl.purchase.order",
            "res_id": self.dlm_purchase_order_id.id,
            "view_mode": "form",
            "target": "current",
        }


class StockMove(models.Model):
    _inherit = "stock.move"

    # Cột chỉ dùng ở báo cáo giá vốn — khai ở đây để không phải join tay.
    dlm_lot_cost = fields.Float(
        string="Giá vốn lô", compute="_compute_dlm_lot_cost",
        digits="Product Price", groups=_DLM_BUY_PRICE_GROUPS)

    @api.depends("move_line_ids.quantity", "move_line_ids.lot_id")
    def _compute_dlm_lot_cost(self):
        for move in self:
            move.dlm_lot_cost = move._dlm_fifo_cost()

    def _dlm_fifo_cost(self):
        """Tiền của move này theo GIÁ CỦA CHÍNH LÔ đã lấy.

        🔴 Không có phép chia trung bình nào ở đây, và cũng không cần bộ chia
        FIFO nào: Odoo đã chọn lô theo `removal_strategy` lúc giữ chỗ, kết quả
        nằm sẵn ở ``move_line.lot_id``. Tự viết bộ chia là dựng nguồn sự thật
        thứ hai — bộ của mình nói lô A, phiếu lại giữ lô B, và không lỗi nào nổ.
        """
        total = 0.0
        for line in self.move_line_ids:
            lot = line.lot_id.sudo()
            unit = lot.dlm_unit_cost if lot else 0.0
            if not unit:
                # Hàng không theo lô, hoặc lô chưa kịp có giá: rơi về giá vốn
                # tham chiếu để báo cáo không âm thầm tính bằng 0.
                unit = line.product_id.sudo().standard_price or 0.0
            total += line.quantity * unit
        return total
