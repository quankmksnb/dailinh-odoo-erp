"""Điền Nhóm sản phẩm còn thiếu cho dòng RFQ gia công cũ.

Từ bản này, nhóm sản phẩm là CHÌA KHOÁ ĐỊNH TUYẾN của dòng gia công — nó quyết
định form hỏi Sales thông số gì và Kỹ thuật dùng mẫu nào. Dòng cũ không có nhóm
sẽ vấp `_check_category_required` ngay lần Sales sửa tiếp theo, mà lúc đó người
sửa không hiểu vì sao một dòng đang chạy bình thường bỗng bị chặn.

Suy nhóm từ Sản phẩm xác định / Sản phẩm tham khảo. Dòng không suy được thì để
nguyên — KHÔNG đoán bừa một nhóm, vì nhóm sai còn tệ hơn nhóm trống: Sales sẽ
được hỏi bộ thông số của một họ sản phẩm khác hẳn.

🔴 CỐ Ý KHÔNG dựng bộ ô thông số cho dòng cũ. Bản nháp đầu của script này có gọi
`_dlm_sync_params()` và đó là một cái bẫy: nó thêm ô RỖNG vào dòng cũ, rồi
`_check_manufactured_spec` thấy "thiếu thông số bắt buộc" và ném ValidationError
NGAY TRONG migration — cả lệnh `-u dl_technical` đổ, trên DB có dữ liệu thật.

Dòng cũ không có ô thông số vẫn hợp lệ (xem ghi chú ở `_compute_param_state`) và
vẫn được bộ dò khớp phục vụ qua đường đọc kích thước từ mô tả. Ô thông số được
dựng khi Sales mở dòng ra và đổi nhóm — tức khi có người thật đọc và điền được.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env["dl.quotation.request.line"]

    lines = Line.search([
        ("product_type", "=", "manufactured"),
        ("product_category_id", "=", False),
    ])
    if not lines:
        return

    filled = 0
    for line in lines:
        source = line.resolved_product_id or line.reference_product_id
        if source and source.categ_id:
            line.product_category_id = source.categ_id.id
            filled += 1

    env["ir.logging"].sudo().create({
        "name": "dl_technical.migration",
        "type": "server",
        "level": "INFO",
        "dbname": cr.dbname,
        "message": (
            "17.0.2.5.0 — %s dòng gia công thiếu Nhóm sản phẩm: điền được %s, "
            "còn %s dòng Sales phải tự chọn nhóm khi mở ra sửa."
            % (len(lines), filled, len(lines) - filled)),
        "path": "migrations/17.0.2.5.0/post-migration.py",
        "func": "migrate",
        "line": "0",
    })
