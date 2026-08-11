{
    "name": "DL-Inventory",
    "version": "17.0.2.4.0",
    "summary": "Kho Đại Linh — 1 kho, 3 khu, nhận hàng 2 bước có kiểm hàng",
    "description": """
Phân hệ Kho (Giai đoạn B1). Đặc tả: docs/Thiet_ke_phan_he_kho.md

Đã có (K1–K5):
  • Vai trò THỦ KHO (dl_base.dl_group_warehouse) + ACL + record rule + RBAC.
  • Bố cục kho: MỘT stock.warehouse, ba khu (Nhập / Xưởng / Thành phẩm) và
    5 vị trí con; 8 loại hoạt động; nhận hàng 2 BƯỚC (về khu Chờ kiểm rồi mới
    cất) — nền cho bước QC.
  • Số lô do Đại Linh TỰ SINH (LO/2026/00001), tự điền khi nhận hàng; lô mang
    theo NCC + ngày nhập + phiếu nguồn.
  • Màn Tồn kho (chỉ-đọc, không có cột giá) và Lô hàng.
  • Kiểm hàng NCC: ghi Đạt/Loại + lý do ngay trên dòng phiếu, hàng loại sang
    khu Chờ trả NCC và sinh phiếu Trả hàng NCC ở trạng thái NHÁP giao cho Mua
    hàng. Tách bạch "NCC giao thiếu" (backorder) với "NCC giao hàng kém" (loại).

Thêm ở K6:
  • Chuyển kho nội bộ với 2 preset tuyến hay dùng (vật tư ra xưởng, hàng
    thương mại sang kho thành phẩm).
  • Giao hàng khách gắn với dl.sale.order: nút Tạo phiếu giao trên đơn (KHÔNG
    tự sinh lúc chốt đơn), chip tình trạng giao, và khoá đưa đơn về nháp khi
    đã phát sinh phiếu giao.
  • Màn Trả hàng NCC cho bộ phận Mua hàng, kèm lý do loại gộp từ các dòng.

Thêm ở K7:
  • Màn Phế liệu: cân thực tế (chế độ kiểm kê) + nút Bán phế liệu, luôn kèm
    dải chú thích "tiền bán phế liệu không phải lợi nhuận tăng thêm".
  • Báo cáo đối chiếu thu hồi theo tháng: dự toán (từ BOM) vs cân thực tế —
    vòng phản hồi cho biết định mức hao hụt đặt đúng hay sai.

Chưa có (K8): kiểm kê chung + hàng đợi phiếu cho thủ kho.

KHÔNG dựng lại tầng "hub" (màn lưới thẻ trung chuyển): tầng đó đã bị gỡ khỏi cả
hệ thống, điều hướng đi thẳng qua submenu rail.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    # ⚠️ dl_sale làm dl_inventory chuyển từ nhánh song song sang SAU dl_sale
    # trong thứ tự cài (K6 _inherit dl.sale.order). Khai tường minh, không dựa
    # vào phụ thuộc bắc cầu — xem bảng đồ thị phụ thuộc ở CLAUDE.md.
    "depends": ["dl_base", "dl_product", "dl_partner", "dl_sale", "stock"],
    "data": [
        # ACL phải nạp trước mọi thứ chạm dữ liệu.
        "security/ir.model.access.csv",
        "security/groups_stock_link.xml",
        # Seed bố cục kho — TẠO loại hoạt động (picking_type_qc, ...).
        "data/stock_inventory_layout.xml",
        # ⚠️ Nạp SAU seed: rule neo vào sequence_code của loại hoạt động ở trên.
        "security/ir_rule.xml",
        "data/rbac_features.xml",
        "views/picking_views.xml",
        "views/transfer_views.xml",
        "views/delivery_views.xml",
        "views/vendor_return_views.xml",
        "views/stock_quant_views.xml",
        "views/stock_lot_views.xml",
        "views/scrap_views.xml",
        # Kế thừa form dl.sale.order ⇒ nạp sau khi action phiếu giao đã có.
        "views/sale_order_views_ext.xml",
        # menus.xml nạp CUỐI: menuitem tham chiếu action khai ở các file trên.
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # SCSS — token & mixin dùng chung ở dl_base nạp trước theo thứ tự
            # phụ thuộc; đây chỉ còn style theo màn của dl_inventory.
            "dl_inventory/static/src/scss/stock_list.scss",
            "dl_inventory/static/src/js/nav_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
