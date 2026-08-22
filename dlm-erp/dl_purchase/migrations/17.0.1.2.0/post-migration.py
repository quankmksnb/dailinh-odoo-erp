import logging

_logger = logging.getLogger(__name__)

# Backfill mốc "đã gửi hỏi giá" cho các đơn hỏi giá sinh trước bản vá.
#
# `action_dlm_request_vendor_quote` tạo đơn THẲNG ở state `sent` nên không đi qua
# `action_dlm_send` — chỗ duy nhất đóng `date_sent`. Hệ quả: mọi đơn hỏi giá đều
# rỗng mốc gửi, và câu hỏi mà chính field này sinh ra để trả lời ("gửi ba ngày
# rồi nhà cung cấp chưa báo giá") không trả lời được.
#
# Với những đơn đó, LÚC TẠO chính là lúc gửi — không có bước nháp nào ở giữa —
# nên `create_date` là mốc đúng, không phải một con số bịa cho đẹp bảng.


def migrate(cr, version):
    cr.execute("""
        UPDATE dl_purchase_order
           SET date_sent = create_date
         WHERE dlm_quotation_id IS NOT NULL
           AND date_sent IS NULL
    """)
    _logger.info(
        "Mua hàng: điền mốc 'đã gửi hỏi giá' cho %s đơn hỏi giá cũ.", cr.rowcount)
