{
    "name": "DL-Purchase",
    "version": "17.0.1.3.0",
    "summary": "Mua hàng Đại Linh — đơn mua, hỏi giá, chốt giá theo lô, giá vốn FIFO",
    "description": """
Phân hệ Mua hàng (giai đoạn B1.5). Đặc tả:
docs/Thiet_ke_mua_hang_va_vong_cung_ung.md

Khép kín vòng cung ứng: đơn bán thiếu hàng → điều phối đẩy nhu cầu sang Mua hàng
→ hỏi giá NCC → chốt giá CHO LÔ HÀNG ĐÓ → NCC giao → thủ kho nhận & kiểm như
luồng đang chạy → vật tư vào kho → điều phối lại đơn cũ thấy đủ.

Gồm:
  • dl.purchase.order — MỘT chứng từ, 5 trạng thái, có nấc "Đã gửi hỏi giá".
    Tình trạng nhận hàng KHÔNG phải một trạng thái mà suy từ CHỨNG TỪ: NCC giao
    ba lần thì có ba phiếu nhận, và sự thật nằm ở đó.
  • Chốt đơn ⇒ sinh phiếu [1] Nhận hàng NCC. Luồng kiểm hàng (QC) KHÔNG sửa một
    dòng nào — đơn mua chỉ thêm một NGUỒN GỐC cho phiếu nhận vốn đang tạo tay.
  • Duyệt theo NGƯỠNG TIỀN, dùng lại hòm duyệt sẵn có của CEO
    (dl.pricing.approval.request) thay vì dựng hòm thứ hai.
  • Giá chốt đóng lên LÔ khi nhận hàng ⇒ giá vốn thực tế của đơn bán tính theo
    FIFO: lô cũ giá cũ dùng hết rồi mới sang lô mới giá mới.
  • PDF hai biến thể gửi NCC: "Yêu cầu báo giá" (không giá) và "Đơn đặt hàng"
    (có giá) — NCC không đăng nhập ERP của Đại Linh.
  • Hàng THƯƠNG MẠI là công dân hạng nhất: gần một nửa doanh thu của Đại Linh
    không có BOM (đồ chơi mầm non, phòng STEM, bảng từ) — mua chính mặt hàng đó.

🔴 KHÔNG cài `purchase`/`account` của Odoo: `stock_account` là auto_install ⇒
định giá tồn kho sống dậy ⇒ Odoo tranh quyền ghi standard_price với
_dlm_recompute_reference_cost ⇒ giá báo khách nhảy theo từng phiếu nhập. Đây là
cùng lý do dự án đã tự xây dl.sale.order.

🔴 FIFO ở đây là CHIẾN LƯỢC LẤY HÀNG (`stock.removal_fifo`, nằm trong module
`stock` lõi), KHÔNG phải định giá tồn kho. Hai thứ khác nhau, chỉ trùng tên.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    # dl_config khai TƯỜNG MINH (dùng dl.pricing.approval.request) — không lặp
    # lại nợ của dl_sale, module đang chạy nhờ phụ thuộc bắc cầu.
    "depends": ["dl_base", "dl_partner", "dl_product", "dl_config",
                "dl_sale", "dl_inventory"],
    "external_dependencies": {"python": ["reportlab"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/approval_setting.xml",
        "data/rbac_features.xml",
        # Mẫu thư gửi NCC — nạp TRƯỚC view: action_dlm_email tra bằng env.ref.
        "data/purchase_mail_template.xml",
        "wizard/purchase_price_update_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_lot_views_ext.xml",
        "views/sale_order_views_ext.xml",
        "views/quotation_views_ext.xml",
        # menus.xml nạp CUỐI: menuitem tham chiếu action khai ở trên.
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dl_purchase/static/src/js/nav_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
