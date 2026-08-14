{
    'name': 'DL-Partner — Khách hàng & NCC',
    'version': '17.0.1.11.0',
    'summary': 'Quản lý Khách hàng và Nhà cung cấp — kế thừa res.partner',
    'author': 'Dai Linh',
    'category': 'Hidden',
    # product: để form NCC nhúng được tab "Bảng giá cung cấp" (product.supplierinfo).
    # Giữ MỌI thứ liên quan tới đối tác trong dl_partner thay vì để dl_product
    # _inherit ngược lại res.partner — đổi lại dl_partner phải phụ thuộc product.
    # Không tạo vòng: dl_product depends dl_partner, còn product là module lõi.
    'depends': ['dl_base', 'mail', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/partner_category_data.xml',
        'views/customer_views.xml',
        'views/supplier_views.xml',
        'views/res_country_views.xml',
        'views/partner_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Widget nhập MST — lọc ký tự + báo lỗi định dạng phía frontend.
            'dl_partner/static/src/fields/tax_code_field.js',
            'dl_partner/static/src/fields/tax_code_field.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
