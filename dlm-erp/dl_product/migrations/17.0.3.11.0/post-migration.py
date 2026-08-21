import logging

_logger = logging.getLogger(__name__)

# Backfill cờ `dlm_superseded` cho các dòng bảng giá đã bị thay thế TRƯỚC khi có
# cờ này. Trước đây "bị thay thế" chỉ được ghi bằng `date_end`, mà `date_end`
# không được nhỏ hơn `date_start` — nên giá hỏi lại trong CÙNG một ngày chỉ đóng
# về đúng hôm nay và vẫn lọt bộ lọc "Còn hiệu lực" cả ngày hôm đó.
#
# Định nghĩa dùng để dò ngược: dòng đã đóng ngày, không đang áp dụng, mà CÙNG
# vật tư + CÙNG nhà cung cấp còn một dòng đang áp dụng có ngày hiệu lực bằng
# hoặc muộn hơn ⇒ chính nó là dòng bị thay chỗ.
#
# 🔴 `>=` chứ không phải `>`: hai dòng cùng ngày là đúng cái ca hỏng đang phải
# vá — dùng `>` thì bỏ sót sạch.
#
# 🔴 Chỉ đụng dòng CÙNG nhà cung cấp. Giá của NCC khác là chào giá song song,
# đánh dấu bị thay thế là xoá mất lựa chọn thay thế khỏi màn hình.


def migrate(cr, version):
    cr.execute("""
        UPDATE product_supplierinfo r
           SET dlm_superseded = TRUE
         WHERE COALESCE(r.is_applied, FALSE) = FALSE
           AND r.date_end IS NOT NULL
           AND COALESCE(r.dlm_superseded, FALSE) = FALSE
           AND EXISTS (
                   SELECT 1
                     FROM product_supplierinfo n
                    WHERE n.product_tmpl_id = r.product_tmpl_id
                      AND n.partner_id      = r.partner_id
                      AND n.id             <> r.id
                      AND n.is_applied      = TRUE
                      AND n.date_start     >= r.date_start
               )
    """)
    _logger.info(
        "Bảng giá NCC: đánh dấu %s dòng giá cũ là 'Đã bị thay thế' — chúng sẽ "
        "rời bộ lọc 'Còn hiệu lực' và chỉ còn ở 'Đã hết hiệu lực (lịch sử giá)'.",
        cr.rowcount)
