import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K3 (docs/Thiet_ke_phan_he_kho.md §3.4) — bật THEO LÔ cho vật tư & bán thành
# phẩm đang có. Vật tư/BTP tạo trước bản này mang tracking='none' (mặc định
# Odoo); nhập kho khi chưa bật lô ⇒ hàng đó VĨNH VIỄN không có lô, thủng truy
# vết mà không vá được. Vì vậy backfill phải chạy TRƯỚC phiếu nhập đầu tiên.
_LOT_TRACKED_KINDS = ("material", "material_processed")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.product"].with_context(active_test=False)

    # SP phế liệu bị LOẠI TRỪ: tuy mang product_kind='material', phế liệu là vụn
    # gom từ nhiều lô khác nhau trong cùng thùng chứa — bắt thủ kho nhập số lô
    # mỗi lần cân là công vô ích và không truy vết được gì.
    scrap_ids = Product.search(
        [("dlm_scrap_product_id", "!=", False)]).mapped("dlm_scrap_product_id").ids

    to_lot = Product.search([
        ("product_kind", "in", _LOT_TRACKED_KINDS),
        ("detailed_type", "=", "product"),
        ("tracking", "=", "none"),
        ("id", "not in", scrap_ids),
    ])
    if to_lot:
        to_lot.product_tmpl_id.write({"tracking": "lot"})
        _logger.info(
            "K3 backfill: %s vật tư/BTP chuyển sang theo lô.", len(to_lot))

    # Gỡ theo lô khỏi SP phế liệu — bản trước bật nhầm cho cả nhóm này.
    to_none = Product.browse(scrap_ids).filtered(lambda p: p.tracking != "none")
    if to_none:
        to_none.product_tmpl_id.write({"tracking": "none"})
        _logger.info(
            "K3 backfill: %s sản phẩm phế liệu gỡ theo lô (%s).",
            len(to_none), ", ".join(to_none.mapped("display_name")))
