from odoo import fields, models


class ProductCategory(models.Model):
    """PROD-01 — dl.product.category [kế thừa product.category].

    Nhóm sản phẩm cơ khí — kế thừa mở rộng ``product.category`` để giữ tương
    thích hệ sinh thái Odoo (Inventory, Accounting).

    Data Model §4.2 PROD-01 chỉ định nghĩa 2 field mở rộng: ``bom_template_id``
    (→ TECH-04 dl.bom.template) và ``active``.

    Ghi chú kiến trúc: field ``bom_template_id`` trỏ tới model dl.bom.template
    (TECH-04) thuộc module dl_technical — nằm ở LAYER TRÊN dl_product. Vì
    dl_product không (và không được) depends dl_technical, FK category→BOM mẫu
    được khai báo bên dl_technical (đúng chiều phụ thuộc), KHÔNG khai ở đây.
    ``category_kind`` của thiết kế cũ đã BỎ (không có trong Data Model mới —
    phân loại giờ nằm ở product_kind cấp sản phẩm, không cần cấp category).
    """

    _inherit = "product.category"

    active = fields.Boolean(string="Đang sử dụng", default=True)
