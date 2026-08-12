# -*- coding: utf-8 -*-
"""K7 — Đối chiếu phế liệu: dự toán khi báo giá vs cân thực tế.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §7.2, §7.4, §11.8.

Đây là **vòng phản hồi duy nhất** cho biết định mức hao hụt (`dlm_waste_rate`)
đặt đúng hay sai. Không có màn này thì hệ số hao hụt là con số ai đó gõ một lần
rồi không bao giờ ai kiểm lại — mà nó đi thẳng vào giá báo khách.

🔴 Đọc con số ở đây theo đúng nghĩa (§7.2): tiền bán phế liệu **KHÔNG phải lãi
thêm**. Giá trị thu hồi đã được trừ trước vào giá vốn lúc báo giá, nên:

    thu hồi ĐÚNG dự toán   → giá vốn thực = giá vốn đã báo
    thu hồi ÍT hơn dự toán → 🔴 giá vốn thực CAO HƠN đã báo, đang lỗ ngầm
    thu hồi NHIỀU hơn      → định mức hao hụt đang đặt quá tay

Model chỉ-đọc, không có bảng riêng (`_auto = False`).
"""

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools

# Chỉ đơn đã có cam kết mới sinh dự toán phế liệu. Đơn huỷ thì hàng không làm.
_DLM_LIVE_ORDER_STATES = ("confirmed", "done")


class DlScrapRecoveryReport(models.Model):
    _name = "dl.scrap.recovery.report"
    _description = "Đối chiếu thu hồi phế liệu"
    _auto = False
    _order = "period desc"
    _rec_name = "period"

    # 🔴 BẮT BUỘC với model đọc thẳng SQL: search() chỉ tự flush model của CHÍNH
    # nó, không biết view này đọc bảng nào. Thiếu khai báo thì phiếu vừa xác nhận
    # xong (còn trong cache ORM, chưa xuống DB) KHÔNG xuất hiện trong báo cáo —
    # sai âm thầm, và chỉ lộ ra khi có người bấm F5 mới thấy số nhảy.
    _depends = {
        "stock.move": ["date", "state", "product_qty",
                       "location_id", "location_dest_id"],
        "stock.location": ["parent_path", "usage"],
        "dl.sale.order": ["date_order", "state"],
    }

    period = fields.Date(string="Kỳ (tháng)", readonly=True)
    qty_in = fields.Float(
        string="Thực nhập (kg)", readonly=True, digits="Product Unit of Measure")
    qty_sold = fields.Float(
        string="Đã bán (kg)", readonly=True, digits="Product Unit of Measure")
    qty_estimated = fields.Float(
        string="Dự toán (kg)", compute="_compute_dlm_estimate",
        digits="Product Unit of Measure")
    qty_diff = fields.Float(
        string="Chênh lệch (kg)", compute="_compute_dlm_estimate",
        digits="Product Unit of Measure",
        help="Thực nhập − Dự toán. Âm = cân được ít hơn tính toán ⇒ giá vốn "
             "thực cao hơn giá đã báo khách.")
    diff_level = fields.Selection([
        ("short", "Hụt so với dự toán"),
        ("match", "Khớp dự toán"),
        ("over", "Vượt dự toán"),
    ], string="Đánh giá", compute="_compute_dlm_estimate")

    # ── Dự toán: tính bằng Python, không phải SQL ────────────────────────────
    # Công thức thu hồi nằm ở dl.bom.line (quy đổi ĐVT vật tư → kg qua
    # dlm_mass_per_unit rồi nhân tỉ lệ thu hồi). Chép nó sang SQL là tạo bản thứ
    # hai của một công thức TIỀN — hai bản sẽ lệch nhau ngay lần sửa đầu tiên.
    @api.depends("period")
    def _compute_dlm_estimate(self):
        Order = self.env["dl.sale.order"]
        for record in self:
            estimated = 0.0
            if record.period:
                orders = Order.sudo().search([
                    ("date_order", ">=", record.period),
                    ("date_order", "<", record.period + relativedelta(months=1)),
                    ("state", "in", _DLM_LIVE_ORDER_STATES),
                ])
                for line in orders.line_ids:
                    if line.bom_id:
                        estimated += (
                            line.bom_id._dlm_recovery_kg_per_unit() * line.qty)
            record.qty_estimated = estimated
            record.qty_diff = record.qty_in - estimated
            if not estimated:
                # Chưa có dự toán thì không kết luận gì được — "khớp" ở đây là
                # "không có gì để so", đừng tô đỏ làm người đọc tưởng có vấn đề.
                record.diff_level = "match"
            elif record.qty_diff < -0.001:
                record.diff_level = "short"
            elif record.qty_diff > 0.001:
                record.diff_level = "over"
            else:
                record.diff_level = "match"

    # ── SQL view ─────────────────────────────────────────────────────────────
    # Vị trí phế liệu tra qua ir_model_data NGAY TRONG SQL thay vì nhúng id lúc
    # tạo view: lần cài đầu tiên, `init()` chạy TRƯỚC khi data file seed vị trí,
    # nên env.ref() sẽ nổ. Tra trong SQL thì view vẫn tạo được, chỉ tạm rỗng.
    #
    # Hàng của báo cáo là HỢP của "tháng có phát sinh phế liệu" và "tháng có
    # đơn hàng": chỉ lấy tháng có move thì kỳ nguy hiểm nhất — dự toán 100kg mà
    # cân được 0kg — sẽ không có dòng nào và biến mất khỏi báo cáo.
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH scrap_tree AS (
                    SELECT child.id
                      FROM stock_location child
                      JOIN stock_location root
                        ON child.parent_path LIKE root.parent_path || '%%'
                      JOIN ir_model_data data
                        ON data.res_id = root.id
                       AND data.model = 'stock.location'
                     WHERE data.module = 'dl_inventory'
                       AND data.name = 'stock_location_xuong_pl'
                ),
                scrap_moves AS (
                    SELECT date_trunc('month', move.date)::date AS period,
                           SUM(CASE
                                 WHEN move.location_dest_id IN (SELECT id FROM scrap_tree)
                                  AND move.location_id NOT IN (SELECT id FROM scrap_tree)
                                 THEN move.product_qty ELSE 0 END) AS qty_in,
                           SUM(CASE
                                 WHEN move.location_id IN (SELECT id FROM scrap_tree)
                                  AND dest.usage = 'customer'
                                 THEN move.product_qty ELSE 0 END) AS qty_sold
                      FROM stock_move move
                      JOIN stock_location dest ON dest.id = move.location_dest_id
                     WHERE move.state = 'done'
                       AND (move.location_dest_id IN (SELECT id FROM scrap_tree)
                         OR move.location_id IN (SELECT id FROM scrap_tree))
                     GROUP BY 1
                ),
                periods AS (
                    SELECT period FROM scrap_moves
                    UNION
                    SELECT DISTINCT date_trunc('month', so.date_order)::date
                      FROM dl_sale_order so
                     WHERE so.state IN ('confirmed', 'done')
                )
                SELECT (EXTRACT(YEAR FROM p.period) * 100
                        + EXTRACT(MONTH FROM p.period))::int AS id,
                       p.period AS period,
                       COALESCE(m.qty_in, 0.0) AS qty_in,
                       COALESCE(m.qty_sold, 0.0) AS qty_sold
                  FROM periods p
                  LEFT JOIN scrap_moves m ON m.period = p.period
            )
        """ % self._table)
