import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K13 — Đầu ra cho nhánh gia công (docs/Thiet_ke_phan_he_kho.md §5.1, §9.1, §11.13).
#
# Loại hoạt động [8] `NTP` thì seed lo (`_dlm_setup_picking_types` idempotent), và
# KHÔNG sinh lùi phiếu giao cho đơn Hạng A đã chốt trước bản này — chứng từ giao
# hàng phải khớp một lần giao hàng có thật.
#
# 🔴 Nhưng CÓ một thứ bắt buộc phải chạm: `dlm_has_deliverable` và
# `dlm_delivery_state` là computed **STORED**. K13 đổi THÂN hàm tính
# (`_dlm_deliverable_lines` nay nhận cả dòng `consu`) mà KHÔNG đổi định nghĩa
# field ⇒ Odoo không có lý do gì để tính lại, và mọi đơn Hạng A đã tồn tại giữ
# nguyên `dlm_has_deliverable = False`. Hệ quả im lặng: nút [Tạo phiếu giao] ẩn
# vĩnh viễn trên đúng những đơn mà cả K13 sinh ra để phục vụ. Trên màn hình
# không có gì báo lỗi — chỉ là một cái nút không bao giờ xuất hiện.
#
# Đây cũng là lý do file này tồn tại dù §12.2 (viết trước khi thực thi) kết luận
# "không migration": nhận định đó chỉ đúng cho phần CHỨNG TỪ.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Order = env["dl.sale.order"]
    orders = Order.search([])
    if not orders:
        _logger.info("K13: chưa có đơn bán hàng nào — không phải tính lại gì.")
        return

    truoc = len(orders.filtered("dlm_has_deliverable"))
    for field_name in ("dlm_has_deliverable", "dlm_delivery_state"):
        env.add_to_compute(Order._fields[field_name], orders)
    orders.flush_recordset()

    sau = len(orders.filtered("dlm_has_deliverable"))
    _logger.info(
        "K13: tính lại tình trạng giao hàng cho %s đơn. Số đơn có hàng cần "
        "giao: %s → %s (chênh lệch là các đơn Hạng A trước đây không tạo được "
        "phiếu giao).", len(orders), truoc, sau)
