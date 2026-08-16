import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K12 — cờ nhận diện phế liệu (docs/Thiet_ke_phan_he_kho.md §4.2, §12.2).
#
# `material_seed_data.xml` mang noupdate="1" nên `-u` KHÔNG ghi đè bản ghi đã có
# ⇒ DB cũ sẽ không tự bật cờ. Phải làm ở migration.
#
# 🔴 Tra theo `default_code`, KHÔNG theo XML ID: bản ghi seed có thể đã bị người
# dùng sửa hoặc nhân bản, và cái đáng tin là MÃ hàng chứ không phải mối nối
# ir_model_data (thứ từng biến mất một lần trong repo này — xem bẫy RBAC mồ côi).
#
# Không tìm thấy ⇒ LOG CẢNH BÁO, KHÔNG tạo mới: đẻ ra một sản phẩm phế liệu ma
# tệ hơn hẳn việc thiếu cờ — nó sẽ nhận hàng vào khu Phế liệu mà không ai bán
# được, còn thiếu cờ thì phiếu Hoá phế liệu chặn ngay và nói rõ lý do.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.product"].with_context(active_test=False)

    scrap = Product.search([("default_code", "=", "SCRAP-STEEL")])
    if not scrap:
        _logger.warning(
            "K12: KHÔNG tìm thấy sản phẩm phế liệu 'SCRAP-STEEL'. Cờ "
            "dlm_is_scrap chưa bật cho mặt hàng nào ⇒ phiếu Hoá phế liệu sẽ "
            "chặn và báo 'chưa khai mặt hàng phế liệu'. Bật tay cờ 'Là mặt "
            "hàng phế liệu' trên sản phẩm phế liệu của bạn.")
        return

    scrap.write({"dlm_is_scrap": True})
    _logger.info("K12: bật dlm_is_scrap cho %s mặt hàng phế liệu (%s).",
                 len(scrap), ", ".join(scrap.mapped("display_name")))

    # Mở rộng: mặt hàng nào đang được vật tư trỏ tới làm "sản phẩm phế liệu" thì
    # cũng bật cờ. Đây chính là tập mà `_dlm_is_scrap_product()` đang suy ngược —
    # chuyển nó thành dữ liệu THẬT ngay bây giờ, để vế suy ngược chỉ còn là lưới
    # an toàn chứ không phải nguồn sự thật song song.
    duoc_tro_toi = Product.search([
        ("id", "in", Product.search(
            [("dlm_scrap_product_id", "!=", False)]
        ).mapped("dlm_scrap_product_id").ids),
        ("dlm_is_scrap", "=", False),
    ])
    if duoc_tro_toi:
        duoc_tro_toi.write({"dlm_is_scrap": True})
        _logger.warning(
            "K12: bật thêm dlm_is_scrap cho %s mặt hàng đang được vật tư trỏ "
            "tới làm sản phẩm phế liệu: %s. Kiểm lại — nếu có cái nào KHÔNG "
            "phải phế liệu thì tắt cờ, vì cờ này quyết định hàng nào vào được "
            "khu Phế liệu chờ bán.",
            len(duoc_tro_toi), ", ".join(duoc_tro_toi.mapped("display_name")))
