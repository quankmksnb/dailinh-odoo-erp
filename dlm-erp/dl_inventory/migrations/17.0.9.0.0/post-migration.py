# -*- coding: utf-8 -*-
"""Viết đầy đủ "NCC" trong TÊN vị trí và loại hoạt động.

Nhãn cột trên view sửa ở XML là xong, nhưng hai chỗ dưới đây là DỮ LIỆU — chữ
"NCC" nằm trong `name` của bản ghi, hiện lên ở cột "Vị trí" / "Loại phiếu" của
mọi màn Kho:

  DL/Khu nhập hàng/Chờ trả NCC   → Chờ trả nhà cung cấp
  Loại hoạt động "Trả hàng NCC"  → Trả hàng nhà cung cấp

Vì sao phải có migration chứ không sửa hằng số seed là xong: cả
`_dlm_setup_locations` lẫn `_dlm_setup_picking_types` CỐ Ý không ghi đè `name`
của bản ghi đã tồn tại (người dùng có thể đã đổi tên cho hợp cách gọi ở xưởng).
Sửa `_DLM_NEW_LOCATIONS` / `_DLM_NEW_PICKING_TYPES` vì thế chỉ áp cho DB cài
mới — đúng cái bẫy đã gặp ở 17.0.5.0.0 và 17.0.7.0.0.

Loại hoạt động NATIVE "Nhận hàng NCC" KHÔNG cần xử ở đây:
`_dlm_setup_picking_types` ghi đè tên của ba loại native mỗi lần `-u`.

🔴 Ghi tên cho TỪNG ngôn ngữ đang bật: `write` lúc nạp module chạy với `en_US`,
mà mọi user của Đại Linh dùng `vi_VN` — ghi một lần thì không ai thấy tên mới.

Chỉ đổi khi tên hiện tại ĐÚNG BẰNG tên cũ: người dùng đã tự đặt tên khác thì
tôn trọng, chỉ ghi log.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# (xml_id, tên cũ, tên mới)
_DOI_TEN = [
    ("dl_inventory.stock_location_nhan_tra",
     "Chờ trả NCC", "Chờ trả nhà cung cấp"),
    ("dl_inventory.picking_type_vendor_return",
     "Trả hàng NCC", "Trả hàng nhà cung cấp"),
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    langs = env["res.lang"].get_installed()

    for xml_id, ten_cu, ten_moi in _DOI_TEN:
        record = env.ref(xml_id, raise_if_not_found=False)
        if not record:
            continue
        # active_test không cần: env.ref trả bản ghi kể cả đã lưu trữ.
        if record.name not in (ten_cu, ten_moi):
            _logger.warning(
                "Nhãn: %s đang mang tên tự đặt '%s' — KHÔNG đổi.",
                xml_id, record.name)
            continue
        for lang_code, _lang_name in langs:
            translated = record.with_context(lang=lang_code)
            if translated.name != ten_moi:
                translated.write({"name": ten_moi})
        _logger.info("Nhãn: %s '%s' → '%s'.", xml_id, ten_cu, ten_moi)
