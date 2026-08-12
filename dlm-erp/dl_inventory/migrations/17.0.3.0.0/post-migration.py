import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Rút gọn luồng 2026-08-12 (docs/Thiet_ke_phan_he_kho.md §5.3, §12.2).
#
# Hàng thương mại đạt kiểm nay đi THẲNG vào Kho thành phẩm ở bước [2] Kiểm & cất,
# và khu DL/NHAN/KHO đổi tên "Vật tư & hàng thương mại" → "Kho vật tư" (chỉ còn
# chứa vật tư — tên do seed áp lại lúc nạp module). Nhưng hàng thương mại NHẬP
# TRƯỚC bản này có thể đang tồn ở đó theo luồng cũ, giờ nằm trong một khu mà luật
# mới không cho chứa nó nữa.
#
# KHÔNG tự chuyển sang Kho thành phẩm: ghi thẳng quant là dời hàng mà không chứng
# từ nào giải thích vì sao số ở hai khu đổi — đúng thứ RS-07 chặn ở màn Kiểm kê.
# Chỉ LOG danh sách để thủ kho tự làm một phiếu Chuyển kho có dấu vết.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    kho = env.ref(
        "dl_inventory.stock_location_nhan_kho", raise_if_not_found=False)
    if not kho:
        return
    quants = env["stock.quant"].search([
        ("location_id", "child_of", kho.id),
        ("product_id.product_kind", "=", "trading"),
        ("quantity", ">", 0),
    ])
    if not quants:
        return
    for quant in quants:
        _logger.warning(
            "Rút gọn luồng: '%s' (%s) còn %s %s ở '%s' theo luồng cũ — làm phiếu "
            "Chuyển kho sang Kho thành phẩm để giao được.",
            quant.product_id.display_name, quant.lot_id.name or "không lô",
            quant.quantity, quant.product_id.uom_id.name,
            quant.location_id.display_name)
    _logger.warning(
        "Rút gọn luồng: TỔNG %s dòng tồn hàng thương mại còn ở Kho vật tư — "
        "CHƯA tự chuyển. Thủ kho cần làm phiếu Chuyển kho sang Kho thành phẩm.",
        len(quants))
