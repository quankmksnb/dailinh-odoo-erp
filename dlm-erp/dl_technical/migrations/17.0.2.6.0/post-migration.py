"""Điền nhóm cho BOM mẫu tham số theo sản phẩm dùng chung, và soát mẫu mồ côi.

Nhóm của mẫu nay là thông tin SUY RA từ `generic_product_id.categ_id`
(`_check_generic_product_category` giữ hai chỗ khớp nhau). Mẫu cũ có thể đang
khai nhóm khác nhóm của sản phẩm dùng chung — chưa sai lúc đó vì nhóm mới là
neo, nhưng từ nay là lệch.

Mẫu THAM SỐ đã duyệt mà KHÔNG có sản phẩm dùng chung nay là dữ liệu chết
(`_check_parametric_needs_generic` chặn): không ai tới được nó vì Sales chọn
Kiểu hàng chứ không chọn nhóm. Hạ về Nháp và ghi log để Kỹ thuật gán neo rồi
duyệt lại — KHÔNG tự đoán một sản phẩm để gán.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env["dl.bom.template"]

    realigned = 0
    for tmpl in Template.search([("generic_product_id", "!=", False)]):
        categ = tmpl.generic_product_id.categ_id
        if categ and tmpl.product_category_id != categ:
            tmpl.product_category_id = categ.id
            realigned += 1

    # Soi THẲNG vào param_ids, KHÔNG tin `is_parametric`: đó là field computed
    # STORE, mà DB nâng cấp từ bản cũ có thể còn giá trị chưa tính lại — lúc đó
    # mẫu mồ côi lọt lưới và nằm im ở trạng thái đã duyệt, không ai tới được.
    orphans = Template.search([
        ("param_ids", "!=", False),
        ("generic_product_id", "=", False),
        ("status", "in", ("confirmed", "locked")),
    ])
    if orphans:
        # 🔴 HẠ TRẠNG THÁI TRƯỚC, tính lại cờ SAU. Làm ngược lại thì chính
        # migration vấp `_check_parametric_needs_generic`: cờ vừa thành True
        # trong khi bản ghi còn "đã duyệt" và chưa có neo ⇒ ValidationError,
        # và cả lệnh nâng cấp đổ giữa chừng.
        orphans.write({"status": "draft"})
        for tmpl in orphans:
            tmpl.message_post(body=(
                "Hạ về Nháp khi nâng cấp: BOM mẫu có tham số nay bắt buộc gán "
                "<b>Sản phẩm dùng chung</b> — đó là thứ Sales chọn ở ô Kiểu "
                "hàng. Gán sản phẩm đại diện cho họ này rồi xác nhận lại."))

    # Cờ `is_parametric` (computed STORE) trên DB cũ có thể còn lệch — tính lại
    # sau khi đã hạ trạng thái nên không còn gì để vấp.
    Template.search([("param_ids", "!=", False)])._compute_is_parametric()

    env["ir.logging"].sudo().create({
        "name": "dl_technical.migration",
        "type": "server",
        "level": "INFO",
        "dbname": cr.dbname,
        "message": (
            "17.0.2.6.0 — BOM mẫu neo theo sản phẩm: căn lại nhóm cho %s mẫu, "
            "hạ về Nháp %s mẫu tham số chưa có sản phẩm dùng chung."
            % (realigned, len(orphans))),
        "path": "migrations/17.0.2.6.0/post-migration.py",
        "func": "migrate",
        "line": "0",
    })
