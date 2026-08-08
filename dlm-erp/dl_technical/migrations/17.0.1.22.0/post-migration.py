import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# M8 (§12 A2 của Thiet_ke_hang_cau_hinh_hang_tieu_chuan_va_ton_kho.md) — mẫu tham
# số nay trỏ tới SẢN PHẨM DÙNG CHUNG. Seed demo có noupdate="1" nên bản ghi đã
# tạo trước đó không tự nhận field mới ⇒ nối lại cho mẫu demo "Bàn thép khung hộp".
_SEED_LINKS = (
    ("dl_technical.demo_bom_tmpl_ban_thep", "dl_technical.demo_product_ban_thep"),
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    linked = 0
    for template_xmlid, product_xmlid in _SEED_LINKS:
        template = env.ref(template_xmlid, raise_if_not_found=False)
        product = env.ref(product_xmlid, raise_if_not_found=False)
        # Không ghi đè nếu ai đó đã gán sản phẩm dùng chung khác.
        if template and product and not template.generic_product_id:
            template.generic_product_id = product
            linked += 1
    _logger.info("M8 backfill: %s mẫu tham số được nối sản phẩm dùng chung.", linked)
