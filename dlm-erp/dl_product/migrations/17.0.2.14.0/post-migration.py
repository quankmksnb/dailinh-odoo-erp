import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# M7 (§12 A1 của Thiet_ke_hang_cau_hinh_hang_tieu_chuan_va_ton_kho.md) — khối
# lượng riêng chuyển từ HÌNH DẠNG sang VẬT TƯ. Seed vật tư có noupdate="1" nên
# lần -u này KHÔNG tự điền dlm_density cho các bản ghi đã seed trước đó ⇒ backfill.
#
# ⚠️ CHỈ đụng product.product. TUYỆT ĐỐI không cập nhật measurement_coefficient
# đã lưu trên dl.bom.line — làm vậy sẽ đổi giá thành của báo giá/đơn hàng lịch sử.
_STEEL_SEED_XMLIDS = (
    "dl_product.seed_mat_tt_ct3_2",
    "dl_product.seed_mat_tt_ct3_5",
    "dl_product.seed_mat_tt_ss400_10",
    "dl_product.seed_mat_th_40",
    "dl_product.seed_mat_th_50",
    "dl_product.seed_mat_th_100x50",
    "dl_product.seed_mat_to_34",
    "dl_product.seed_mat_to_49",
)
_STEEL_DENSITY = 7850.0


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    filled = 0
    for xmlid in _STEEL_SEED_XMLIDS:
        product = env.ref(xmlid, raise_if_not_found=False)
        # Không ghi đè nếu ai đó đã khai tay giá trị khác.
        if product and not product.dlm_density:
            product.dlm_density = _STEEL_DENSITY
            filled += 1
    _logger.info(
        "M7 backfill: %s vật tư thép seed được điền khối lượng riêng %s kg/m³.",
        filled, _STEEL_DENSITY)
