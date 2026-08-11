{
    "name": "DL-Inventory",
    "version": "17.0.2.1.0",
    "summary": "Kho Đại Linh — 1 kho, 3 khu, nhận hàng 2 bước có kiểm hàng",
    "description": """
Phân hệ Kho (Giai đoạn B1). Đặc tả: docs/Thiet_ke_phan_he_kho.md

Đã có (K1–K3):
  • Vai trò THỦ KHO (dl_base.dl_group_warehouse) + ACL + record rule + RBAC.
  • Bố cục kho: MỘT stock.warehouse, ba khu (Nhập / Xưởng / Thành phẩm) và
    5 vị trí con; 8 loại hoạt động; nhận hàng 2 BƯỚC (về khu Chờ kiểm rồi mới
    cất) — nền cho bước QC.
  • Số lô do Đại Linh TỰ SINH (LO/2026/00001), tự điền khi nhận hàng.

Chưa có (K4–K8): màn Tồn kho / Nhận hàng / Kiểm hàng (QC) / Chuyển kho /
Giao hàng / Phế liệu / Lô / Kiểm kê, và các field QC trên stock.move.

KHÔNG dựng lại tầng "hub" (màn lưới thẻ trung chuyển): tầng đó đã bị gỡ khỏi cả
hệ thống, điều hướng đi thẳng qua submenu rail.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    "depends": ["dl_base", "dl_product", "dl_partner", "stock"],
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
        "views/stock_quant_views.xml",
        "views/stock_lot_views.xml",
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
