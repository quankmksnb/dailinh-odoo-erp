import logging

_logger = logging.getLogger(__name__)

# Backfill dấu "nhà cung cấp đã báo giá" cho các đơn hỏi giá có TRƯỚC khi có dấu.
#
# Đơn hỏi giá cố ý nằm lại nấc `sent` cả sau khi đã ghi nhận giá ("chưa cam kết
# mua"), nên không có gì phân biệt đơn ĐANG chờ nhà cung cấp với đơn ĐÃ xong
# việc — hàng đợi cứ thế dày lên. Dấu mới tách hai thứ đó.
#
# Bằng chứng đơn đã có hồi âm nằm ở BẢNG GIÁ: `_dlm_upsert_price_row` ghi nguồn
# "PO:<số đơn>" lên từng dòng giá nó sinh ra. Lấy mốc SỚM NHẤT — lần ghi nhận
# đầu tiên mới là lúc nhà cung cấp trả lời; bấm lại lần hai chỉ là sửa con số.
#
# 🔴 Chỉ đụng đơn có `dlm_quotation_id`. Đơn mua thật cũng sinh dòng bảng giá
# mang nguồn "PO:..." nhưng nó chưa bao giờ nằm trong hàng đợi hỏi giá — đóng
# dấu lên nó là bịa ra một cuộc hỏi giá không có thật.


def migrate(cr, version):
    cr.execute("""
        UPDATE dl_purchase_order po
           SET dlm_vendor_replied_date = sub.moc
          FROM (
                SELECT substring(s.dlm_source_note FROM 4) AS po_name,
                       min(s.create_date)                  AS moc
                  FROM product_supplierinfo s
                 WHERE s.dlm_source_note LIKE 'PO:%%'
                 GROUP BY 1
               ) sub
         WHERE po.dlm_quotation_id IS NOT NULL
           AND po.dlm_vendor_replied_date IS NULL
           AND po.name = sub.po_name
    """)
    _logger.info(
        "Mua hàng: đóng dấu 'NCC đã báo giá' cho %s đơn hỏi giá cũ — chúng rời "
        "hàng đợi 'Hỏi giá chờ trả lời' (bỏ tick 'Chưa có hồi âm' để xem lại).",
        cr.rowcount)
