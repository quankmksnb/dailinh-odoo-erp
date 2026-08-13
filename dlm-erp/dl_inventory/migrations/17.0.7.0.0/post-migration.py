# -*- coding: utf-8 -*-
"""K16 — Đổi tên loại hoạt động [8] và tắt phiếu bù.

Vì sao phải có migration chứ không sửa seed là xong: `_dlm_setup_picking_types`
CỐ Ý chỉ ghi lại `sequence_code` cho loại hoạt động ĐÃ TỒN TẠI (người dùng có
thể đã đổi tên cho hợp cách gọi ở xưởng). Đổi tên trong hằng số
`_DLM_NEW_PICKING_TYPES` vì thế chỉ áp cho DB cài mới — cùng cái bẫy đã gặp với
tên vị trí ở 17.0.5.0.0.

🔴 Ghi tên cho TỪNG ngôn ngữ đang bật: `write` lúc nạp module chạy với `en_US`,
mà mọi user của Đại Linh dùng `vi_VN` — ghi một lần thì không ai thấy tên mới
(bài học đã trả giá ở `_dlm_setup_picking_types`).
"""

from odoo import SUPERUSER_ID, api

_NEW_NAME = "Nhập kho từ xưởng"


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    picking_type = env.ref(
        "dl_inventory.picking_type_mo_receipt", raise_if_not_found=False)
    if not picking_type:
        return

    for lang_code, _lang_name in env["res.lang"].get_installed():
        translated = picking_type.with_context(lang=lang_code)
        if translated.name != _NEW_NAME:
            translated.write({"name": _NEW_NAME})

    # Phiếu [8] không bao giờ sinh phiếu bù: khai 100 nhận 98 thì 2 cái còn nằm
    # ở xưởng, mẻ sau khai tiếp. Mặc định 'ask' của Odoo sẽ bật wizard tiếng Anh
    # ngay lần nhận thiếu đầu tiên — nằm ngoài toàn bộ thiết kế của phân hệ.
    if picking_type.create_backorder != "never":
        picking_type.create_backorder = "never"
