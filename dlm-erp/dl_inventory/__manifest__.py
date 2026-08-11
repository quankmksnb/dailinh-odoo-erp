{
    "name": "DL-Inventory",
    "version": "17.0.1.0.1",
    "summary": "Quản lý xuất nhập kho — KHUNG RỖNG, chưa có nghiệp vụ",
    "description": """
⚠️ MODULE KHUNG — CHƯA CÓ NGHIỆP VỤ NÀO.

Mọi file trong đây hiện là chỗ đặt sẵn: XML rỗng, ACL chỉ có dòng header,
models/ chưa có model nào. Cài module này KHÔNG thêm bất cứ thứ gì vào hệ thống.

Giữ lại có chủ đích để nghiệp vụ Kho (xuất/nhập, phiếu kho trên stock.picking)
đổ vào đúng chỗ khi bắt đầu code. Nếu tới lúc làm Kho mà thấy cấu trúc này không
hợp, dựng lại từ đầu — đừng gò nghiệp vụ theo khung rỗng này.

KHÔNG dựng lại tầng "hub" (màn lưới thẻ trung chuyển): tầng đó đã bị gỡ khỏi cả
hệ thống, điều hướng đi thẳng qua submenu rail — xem dl_base/static/src/js/
nav_patch.js của các module khác để theo đúng khuôn.
""",
    "author": "Dai Linh",
    "category": "Hidden",
    "depends": ["dl_base", "dl_product", "dl_partner", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/rbac_features.xml",
        "views/picking_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
