import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K3 (docs/Thiet_ke_phan_he_kho.md §3.5) — SP dùng chung (generic) KHÔNG được
# tồn kho: Odoo giữ hàng theo product_id chứ không theo kích thước, nên một
# generic storable sẽ giữ nhầm hàng khác cỡ rồi báo "đủ hàng".
#
# LK-14 (dl_product 17.0.2.13.0) đã đẩy MỌI SP gia công sang storable — bản này
# là NGOẠI LỆ cho riêng generic.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = env["dl.bom.template"].with_context(active_test=False).search([
        ("generic_product_id", "!=", False),
    ])
    products = templates.mapped("generic_product_id").filtered(
        lambda p: p.detailed_type == "product")
    if not products:
        return

    # 🔴 KHÔNG đổi khi SP đang có tồn: 'product' → 'consu' làm số tồn biến mất
    # khỏi mọi báo cáo mà KHÔNG lỗi nào nổ. Ca này chỉ xảy ra nếu đã nhập kho
    # trước khi chạy migration — cảnh báo để người vận hành xử lý tay.
    quants = env["stock.quant"].read_group(
        [("product_id", "in", products.ids),
         ("location_id.usage", "in", ("internal", "transit"))],
        ["product_id"], ["product_id"])
    with_stock_ids = {group["product_id"][0] for group in quants}
    blocked = products.filtered(lambda p: p.id in with_stock_ids)
    if blocked:
        _logger.warning(
            "K3: BỎ QUA %s sản phẩm dùng chung đang CÓ TỒN (%s) — đổi sang "
            "'consu' sẽ làm mất số tồn. Xử lý tay: xuất hết tồn rồi đổi lại.",
            len(blocked), ", ".join(blocked.mapped("display_name")))

    to_convert = products - blocked
    if to_convert:
        to_convert.product_tmpl_id.write({"detailed_type": "consu"})
        _logger.info(
            "K3 backfill: %s sản phẩm dùng chung chuyển sang không tồn kho.",
            len(to_convert))
