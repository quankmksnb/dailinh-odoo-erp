import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K11 + K12 (docs/Thiet_ke_phan_he_kho.md §4.1.1, §6.4.1, §12.2).
#
# KHÔNG có gì để backfill cho loại [9]: nó chỉ sinh chứng từ MỚI từ lúc cài trở
# đi, và không được sinh lùi — chứng từ phải khớp một quyết định có thật.
#
# Nhưng PHẢI log đống hàng đang kẹt ở khu Chờ trả NCC thuộc các phiếu trả đã
# `cancel`: đó chính là hàng bị ngõ cụt của luật cũ giam lại, nay mới có lối ra.
# Log để thủ kho/Mua hàng biết mà xử lý, KHÔNG tự động chuyển — hoá phế liệu là
# quyết định có lý do, không phải một bước dọn dẹp thầm lặng.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tra = env.ref(
        "dl_inventory.stock_location_nhan_tra", raise_if_not_found=False)
    if not tra:
        return

    quants = env["stock.quant"].search([
        ("location_id", "child_of", tra.id),
        ("quantity", ">", 0),
    ])
    if not quants:
        _logger.info("K12: khu Chờ trả NCC đang trống — không có gì phải xử lý.")
        return

    for quant in quants:
        _logger.warning(
            "K12: '%s' (%s) còn %s %s kẹt ở '%s'. Nếu phiếu trả đã huỷ thì mở "
            "phiếu đó và bấm [Chuyển thành phế liệu] — nay đã có lối ra.",
            quant.product_id.display_name, quant.lot_id.name or "không lô",
            quant.quantity, quant.product_id.uom_id.name,
            quant.location_id.display_name)
    _logger.warning(
        "K12: TỔNG %s dòng tồn còn ở khu Chờ trả NCC. CHƯA tự xử lý — mỗi lô "
        "cần một quyết định (trả thật cho NCC, hay hoá phế liệu) và một lý do.",
        len(quants))
