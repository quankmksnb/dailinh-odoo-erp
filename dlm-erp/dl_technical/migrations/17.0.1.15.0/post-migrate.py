"""Tách trục: gỡ cờ "phiên bản hiện hành" khỏi BOM báo giá (instance).

Thiết kế §3/§7.4c (docs/Thiet_ke_xu_ly_dong_RFQ_ky_thuat.md):

BOM `bom_type='quotation'` là ĐỊNH MỨC CỦA MỘT ĐƠN, không phải một phiên bản
mới của sản phẩm. Trước đây `_do_confirm()` của workspace RFQ gọi
`_set_current_version()` nên mỗi lần Kỹ thuật hoàn tất một dòng, BOM riêng của
đơn đó lại trở thành "phiên bản hiện hành" — một đơn lẻ (vd bàn 1400x830) ghi
đè định mức chuẩn của sản phẩm (bàn 1200x800).

Migration này dọn hậu quả đã tích luỹ trong dữ liệu:
  1. Gỡ `is_current` khỏi MỌI BOM `bom_type='quotation'`.
  2. Trả cờ về BOM chuẩn (`bom_type='template'`) mới nhất còn hiệu lực
     (confirmed/locked) của từng sản phẩm — nếu sản phẩm đó có.

Sản phẩm CHƯA TỪNG có BOM chuẩn thì sau migration không có bản nào is_current.
Đó là trạng thái ĐÚNG (chưa ai lập định mức chuẩn cho nó), không phải lỗi —
luồng báo giá không phụ thuộc `is_current` mà đọc thẳng `resolved_bom_id`.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Bom = env["dl.bom"].with_context(active_test=False, tracking_disable=True)

    # 1) Instance không bao giờ là phiên bản hiện hành.
    stale = Bom.search([("bom_type", "=", "quotation"), ("is_current", "=", True)])
    if stale:
        stale.write({"is_current": False})
    _logger.info(
        "[17.0.1.4.0] Gỡ cờ phiên bản hiện hành khỏi %s BOM báo giá.", len(stale))

    # 2) Trả cờ về BOM chuẩn mới nhất còn hiệu lực của từng sản phẩm.
    standards = Bom.search([
        ("bom_type", "=", "template"),
        ("status", "in", ("confirmed", "locked")),
    ])
    best_by_product = {}
    for bom in standards:
        product_id = bom.product_id.id
        current_best = best_by_product.get(product_id)
        if current_best is None or bom.version > current_best.version:
            best_by_product[product_id] = bom

    restored = 0
    for bom in best_by_product.values():
        if not bom.is_current:
            bom.is_current = True
            restored += 1
    _logger.info(
        "[17.0.1.4.0] Đặt lại phiên bản hiện hành cho %s sản phẩm (%s bản được bật cờ).",
        len(best_by_product), restored)

    # 3) Dọn cờ thừa: BOM chuẩn không phải bản mới nhất mà vẫn đang mang cờ.
    keep_ids = {bom.id for bom in best_by_product.values()}
    extra = Bom.search([
        ("bom_type", "=", "template"),
        ("is_current", "=", True),
        ("id", "not in", list(keep_ids)),
    ])
    if extra:
        extra.write({"is_current": False})
    _logger.info("[17.0.1.4.0] Dọn %s cờ hiện hành thừa trên BOM chuẩn.", len(extra))
