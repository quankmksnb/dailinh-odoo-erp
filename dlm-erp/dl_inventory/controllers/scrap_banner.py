# -*- coding: utf-8 -*-
"""K7 — Dải chú thích cố định trên hai màn Phế liệu.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §7.2, §11.8.

🔴 Vì sao dòng chữ này bắt buộc phải có, và phải **không đóng được**: giá trị
phế liệu ĐÃ được trừ vào giá vốn từ lúc báo giá. Người đọc màn tồn phế liệu
thấy "8.500 kg × 8.000đ = 68 triệu" mà không có lời nhắc thì gần như chắc chắn
sẽ cộng số đó vào lãi của kỳ — **tính hai lần**.

Dùng `banner_route` native của Odoo (`web/static/src/views/onboarding_banner.js`)
thay vì tự viết OWL component: nó nhận HTML từ route này và gắn lên đầu mọi loại
view. Dải chỉ ẩn đi khi HTML có phần tử mang `data-o-hide-banner` — ở đây cố ý
KHÔNG có, nên không ai tắt được.
"""

from odoo import _, http

_DLM_SCRAP_NOTE = """
<div class="alert alert-info mb-0 rounded-0 border-0 border-bottom" role="note">
    <strong>%(title)s</strong> %(body)s
</div>
"""


def dlm_scrap_banner_html():
    """Nội dung dải chú thích.

    Tách khỏi endpoint để test gọi được thẳng: hàm không đụng `request` nên
    kiểm chứng "dải luôn có và không đóng được" không cần dựng cả một phiên HTTP
    giả — thứ mà nếu phải dựng thì test sẽ bị bỏ qua, đúng lúc đây là bất biến
    QUAN TRỌNG NHẤT của màn phế liệu.
    """
    return _DLM_SCRAP_NOTE % {
        "title": _("Tiền bán phế liệu không phải lợi nhuận tăng thêm."),
        "body": _(
            "Giá trị phế liệu đã được trừ vào giá vốn ngay khi báo giá cho "
            "khách, nên khoản thu này là <b>thu về phần đã tính trước</b>. "
            "Cân được ít hơn dự toán nghĩa là giá vốn thực đang cao hơn giá "
            "đã báo."),
    }


class DlScrapBanner(http.Controller):

    @http.route("/dl_inventory/scrap_banner", type="json", auth="user")
    def scrap_banner(self, **kwargs):
        return {"html": dlm_scrap_banner_html()}
