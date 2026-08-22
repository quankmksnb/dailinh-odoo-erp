{
    "name": "DL-Demo",
    "version": "17.0.1.0.1",
    "summary": "Dữ liệu demo/test liên kết chuẩn giữa các màn (RFQ→BOM→Báo giá→Đơn)",
    "description": """
Module CHỈ DÀNH CHO DEV/DEMO — nạp một bộ dữ liệu giao dịch phủ mọi trạng thái,
liên kết đúng chuỗi nghiệp vụ giữa các màn để test:

  - Khách hàng phủ 3 nhóm auto (mới / cũ / thân thiết) + NCC.
  - Giá NCC (product.supplierinfo) ở các trạng thái Nháp / Đã duyệt / Đang áp dụng.
  - RFQ Kỹ thuật đủ 7 trạng thái (mới → đang xử lý → trả lại → đã bổ sung →
    chờ báo giá → đã báo giá → đã hủy).
  - BOM (Nháp / Đã xác nhận / Đã khóa) + bản vẽ + BOM tham số D×R×C.
  - Báo giá đủ vòng đời (nháp → duyệt nội bộ → gửi khách → khách đồng ý →
    lên đơn, + từ chối / hết hiệu lực / bản mới).
  - Phiếu phê duyệt (dưới ngưỡng tự duyệt vs vượt ngưỡng chờ TrKD/CEO).
  - Đơn bán hàng sinh từ báo giá đã lên đơn.

KHÔNG cài module này trên môi trường thật — không cài = DB sạch kiểu production.
Master data tĩnh nạp qua XML; dữ liệu giao dịch (có state machine + engine giá)
dựng bằng ``post_init_hook`` để đi qua đúng logic nghiệp vụ.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    "depends": [
        "dl_base",
        "dl_config",
        "dl_partner",
        "dl_product",
        "dl_technical",
        "dl_sale",
        "dl_inventory",
        # Kịch bản giá-theo-tồn-kho cần đơn mua + giá đóng trên lô.
        "dl_purchase",
    ],
    "data": [
        "data/demo_partners.xml",
        "data/demo_products.xml",
        "data/demo_manufactured.xml",
        # Nạp CUỐI: <function> cần model + mọi seed master data ở trên.
        "data/demo_stock_pricing.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
