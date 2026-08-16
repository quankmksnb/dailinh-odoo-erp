# -*- coding: utf-8 -*-
"""Ô chọn mặt hàng NÓI RA "hết hàng" thay vì giấu mặt hàng đi.

Danh sách mặt hàng của phiếu chuyển kho từng lọc bỏ mọi thứ tồn = 0 (SM-03 bản
đầu). Đúng nghiệp vụ nhưng sai UX: thủ kho gõ tên vật tư mình BIẾT là kho có
ghi nhận, không thấy gì hiện ra, và không có cách nào phân biệt "khu đó hết
hàng" với "hệ thống tìm không ra". Dropdown câm là câu trả lời tệ nhất cho một
câu hỏi có thật.

Nay danh sách hiện đủ, và mặt hàng đã hết được đánh dấu NGAY TRONG dropdown —
người dùng biết trước khi chọn, chứ không phải chọn xong mới biết.
"""

from odoo import _, api, models
from odoo.tools.float_utils import float_compare


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Gắn hậu tố "hết hàng" cho mặt hàng không còn tồn ở nơi lấy.

        Chỉ chạy khi ô chọn truyền `dlm_src_location_id` qua context (khai ở
        field trên form phiếu) — mọi màn khác giữ nguyên tên gốc.

        ⚠️ Hậu tố chỉ sống trong dropdown: lưu xong, tên hiện lại là tên gốc vì
        display_name tính không có context này. Đó là ý muốn — hậu tố là gợi ý
        lúc CHỌN, còn số tồn thật thì nằm ở cột "Tồn ở nơi lấy" của dòng.
        """
        res = super().name_search(
            name=name, args=args, operator=operator, limit=limit)
        location_id = self.env.context.get("dlm_src_location_id")
        if not location_id or not res:
            return res
        on_hand = self._dlm_qty_by_product(
            location_id, [row[0] for row in res])
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure")
        return [
            (product_id, label
             if float_compare(on_hand.get(product_id, 0.0), 0.0,
                              precision_digits=precision) > 0
             else _("%s — hết hàng ở nơi lấy") % label)
            for product_id, label in res
        ]

    @api.model
    def _dlm_qty_by_product(self, location_id, product_ids):
        """Tổng tồn theo mặt hàng tại/dưới một vị trí — MỘT truy vấn gộp.

        Gộp bằng `_read_group` chứ không lặp từng mặt hàng: đây là đường chạy
        mỗi lần người dùng gõ một ký tự vào ô chọn.

        sudo(): chỉ đọc SỐ LƯỢNG, không đụng tới giá (§8.3 doc kho).
        """
        groups = self.env["stock.quant"].sudo()._read_group(
            [("location_id", "child_of", location_id),
             ("product_id", "in", product_ids)],
            groupby=["product_id"], aggregates=["quantity:sum"])
        return {product.id: quantity for product, quantity in groups}
