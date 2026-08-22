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

🔴 BẪY THỨ HAI (phát hiện sau): `_check_manufactured_spec` có
`product_category_id` trong danh sách `@api.constrains` của chính nó — nên chỉ
GHI field này thôi (dù không đụng gì tới dimension_note/attachment) cũng đủ
kích hoạt lại constraint đó, và dòng cũ thiếu mô tả/bản vẽ vẫn ném lỗi y hệt.
Ghi thẳng bằng SQL (`cr.execute`) thay vì qua ORM `write()`/field setter để né
toàn bộ constrains — đúng tinh thần migration backfill dữ liệu cũ, không phải
đường ghi nghiệp vụ thật.

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
            # SQL thẳng, không qua ORM write() — tránh kích hoạt lại
            # _check_manufactured_spec (product_category_id nằm trong
            # constrains của chính nó, xem chú thích đầu file).
            cr.execute(
                "UPDATE dl_quotation_request_line SET product_category_id = %s "
                "WHERE id = %s",
                (source.categ_id.id, line.id),
            )
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
