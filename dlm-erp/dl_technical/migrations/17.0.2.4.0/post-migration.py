# -*- coding: utf-8 -*-
"""Backfill `request_type` cho RFQ cũ — chốt 2026-08-18: một RFQ, một vòng đời.

Loại RFQ trước đây nằm ở TỪNG DÒNG (`product_type`), nên một RFQ có thể trộn cả
hàng gia công lẫn hàng thương mại. Cột mới ở header được Odoo điền `manufactured`
cho mọi bản ghi cũ (giá trị default), migration này sửa lại những RFQ thật ra là
thương mại thuần.

RFQ TRỘN chỉ được LIỆT KÊ, KHÔNG tự tách: tách tự động sẽ sinh mã RFQ mới và làm
lệch số liệu báo cáo — quyết định thuộc về người dùng. Chúng vẫn mở/đọc được;
chỉ khi ghi lại mới vướng `_check_line_type_matches_header`.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Thuần thương mại: có dòng, và không dòng nào là gia công.
    cr.execute("""
        UPDATE dl_quotation_request r
           SET request_type = 'trading'
         WHERE EXISTS (SELECT 1 FROM dl_quotation_request_line l
                        WHERE l.quotation_request_id = r.id)
           AND NOT EXISTS (SELECT 1 FROM dl_quotation_request_line l
                            WHERE l.quotation_request_id = r.id
                              AND l.product_type != 'trading')
    """)
    _logger.info("RFQ chuyển sang loại 'thương mại': %s", cr.rowcount)

    cr.execute("""
        SELECT r.name
          FROM dl_quotation_request r
         WHERE EXISTS (SELECT 1 FROM dl_quotation_request_line l
                        WHERE l.quotation_request_id = r.id
                          AND l.product_type = 'trading')
           AND EXISTS (SELECT 1 FROM dl_quotation_request_line l
                        WHERE l.quotation_request_id = r.id
                          AND l.product_type = 'manufactured')
         ORDER BY r.id
    """)
    mixed = [row[0] for row in cr.fetchall()]
    if mixed:
        _logger.warning(
            "%s RFQ TRỘN cả hai loại, đã tạm gán 'gia công' — cần tách tay "
            "thành RFQ riêng cho phần thương mại: %s",
            len(mixed), ", ".join(mixed))
