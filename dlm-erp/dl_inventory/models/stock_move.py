# -*- coding: utf-8 -*-
"""K5 — Kết quả kiểm hàng ghi ngay trên dòng dịch chuyển.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §6.

Ba tình huống phải tách bạch, vì mỗi cái là một vấn đề NCC khác nhau:

    NCC giao thiếu   đặt 100, giao 95      ⇒ phiếu NHẬN ghi 95, Odoo sinh backorder
    NCC giao hàng lỗi  giao 100, 8 cây gỉ  ⇒ phiếu KIỂM ghi Loại 8, sang Chờ trả NCC
    NCC giao thừa    đặt 100, giao 103     ⇒ phiếu NHẬN ghi 103

Gộp "giao thiếu" vào "hàng lỗi" là mất đúng thông tin quý nhất của QC: NCC nào
giao thiếu, NCC nào giao hàng kém — hai cách xử lý hoàn toàn khác nhau.

KHÔNG có field "số đạt": số đạt CHÍNH LÀ ``quantity`` native (số thực hiện của
dòng), view chỉ đổi nhãn thành "Đạt". Thêm một field alias chỉ để đổi nhãn là
đẻ ra hai nguồn sự thật cho cùng một con số.
"""

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    dlm_qty_rejected = fields.Float(
        string="Số loại", digits="Product Unit of Measure", default=0.0,
        help="Số lượng KHÔNG đạt khi kiểm — sẽ chuyển sang khu Chờ trả NCC.")
    dlm_reject_reason = fields.Selection([
        ("defect", "Hàng lỗi / hư hỏng"),
        ("wrong_spec", "Sai quy cách"),
        ("wrong_item", "Giao sai mặt hàng"),
        ("other", "Khác"),
    ], string="Lý do loại")
    dlm_reject_note = fields.Char(string="Ghi chú loại")

    # QC-02 — Đạt + Loại không được vượt số hàng đang nằm ở khu Chờ kiểm.
    # Là field (không phải @api.constrains) để view tô đỏ dòng NGAY khi gõ:
    # ràng buộc sửa-được-trên-form phải báo INLINE, không bắn modal.
    dlm_qc_over = fields.Boolean(
        string="Vượt số nhận", compute="_compute_dlm_qc_over")

    @api.depends("quantity", "dlm_qty_rejected", "product_uom_qty", "product_uom",
                 "state")
    def _compute_dlm_qc_over(self):
        for move in self:
            if move.state in ("done", "cancel"):
                # QC-02 là luật lúc NHẬP LIỆU. Sau khi xác nhận, dòng gốc đã bị
                # thu hẹp nhu cầu về đúng số đạt (xem _dlm_split_rejected_moves)
                # nên phép so Đạt+Loại ≤ nhu cầu không còn nghĩa — để nguyên thì
                # phiếu đã xong lại hiện dải đỏ vô cớ.
                move.dlm_qc_over = False
                continue
            rounding = move.product_uom.rounding or 0.01
            move.dlm_qc_over = float_compare(
                move.quantity + move.dlm_qty_rejected, move.product_uom_qty,
                precision_rounding=rounding) > 0
