# -*- coding: utf-8 -*-
"""K16 — Gỡ giá trị thu hồi phế liệu khỏi giá vốn BOM đã lưu.

Người dùng chốt 2026-08-13: BỎ cách tính % thu hồi phế liệu. Hàm
`_dlm_recovery_value` nay trả 0, nhưng `recovery_value` và `subtotal` trên
`dl.bom.line` là **compute STORED** — Odoo chỉ tính lại khi một field trong
`depends` đổi, KHÔNG tính lại khi thân hàm đổi. Không có migration này thì mọi
BOM cũ giữ nguyên khoản giảm giá vốn cũ, còn BOM mới thì không có — hai đường
tính giá lệch nhau âm thầm, đúng kiểu lỗi tiền khó thấy nhất.

🔴 CHỌN HỒI TỐ, có cân nhắc: để lại là một khoản giảm giá vốn không màn nào còn
giải thích được (ô cấu hình đã gỡ khỏi UI). Báo giá ĐÃ CHỐT không bị ảnh hưởng —
chúng lưu cấu phần giá riêng lúc tính, không đọc lại BOM. Chỉ báo giá tính MỚI
từ BOM cũ mới thấy giá vốn cao lên.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["dl.bom.line"].sudo().search([("recovery_value", "!=", 0.0)])
    if not lines:
        return

    boms = lines.bom_id
    # Ghi thẳng thay vì gọi _compute_*: hàm compute đọc `_dlm_recovery_value`
    # (đã trả 0) nên kết quả y hệt, nhưng ghi thẳng thì không phụ thuộc vào việc
    # ai đó sau này lại đổi thân hàm compute.
    for line in lines:
        line.write({
            "recovery_value": 0.0,
            "subtotal": line.effective_qty * line.price_snapshot,
        })
    # `total_material_cost` của BOM là compute stored theo dòng ⇒ đánh dấu tính
    # lại; thiếu bước này thì tổng của BOM vẫn là số cũ.
    env.add_to_compute(env["dl.bom"]._fields["total_material_cost"], boms)
    env.flush_all()
    _logger.info(
        "K16: gỡ giá trị thu hồi khỏi %s dòng BOM thuộc %s định mức — "
        "giá vốn vật tư tăng tương ứng.", len(lines), len(boms))
