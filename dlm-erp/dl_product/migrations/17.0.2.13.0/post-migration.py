import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# LK-14 (§6.1) — mở đường Kho. Chỉ SP seed đang storable; SP/vật tư/BTP tạo qua
# luồng app trước bản này rơi về mặc định Odoo 'consu' (không có stock.quant/
# stock.move ⇒ không nhập/xuất/tồn được). Backfill về storable cho 4 kind nghiệp
# vụ để sau này làm Kho không phải migrate đau.
_STORABLE_KINDS = ("manufactured", "material", "material_processed", "trading")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.product"].with_context(active_test=False)
    products = Product.search([
        ("product_kind", "in", _STORABLE_KINDS),
        ("detailed_type", "=", "consu"),
    ])
    templates = products.mapped("product_tmpl_id")
    if templates:
        templates.write({"detailed_type": "product"})
        _logger.info(
            "LK-14 backfill: %s sản phẩm (%s template) chuyển sang storable.",
            len(products), len(templates))
