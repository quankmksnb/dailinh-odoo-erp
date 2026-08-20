"""Gỡ ràng buộc duy nhất CŨ của BOM mẫu trước khi model dựng index bộ phận mới.

Mẫu tham số từ bản này neo theo SẢN PHẨM DÙNG CHUNG, không theo nhóm nữa. Ràng
buộc cũ `unique(product_category_id, version)` chặn đúng thứ ta muốn cho phép:
hai kết cấu khác nhau trong CÙNG một nhóm thương mại, mỗi cái một mẫu.

Phải chạy ở PRE: `init()` của model tạo hai index bộ phận thay thế ngay khi
registry nạp, mà ràng buộc cũ vẫn còn thì bản ghi thứ hai không ghi nổi.

Odoo tự dọn `ir.model.constraint` khi `_sql_constraints` không còn khai, nhưng
việc dọn đó chạy SAU khi model đã nạp — nên vẫn phải hạ tay ở đây.
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE dl_bom_template
        DROP CONSTRAINT IF EXISTS dl_bom_template_category_version_uniq
    """)
    cr.execute("""
        DELETE FROM ir_model_constraint
         WHERE name = 'dl_bom_template_category_version_uniq'
    """)
