{
    'name': 'DL-Partner — Khách hàng & NCC',
    'version': '17.0.1.0.0',
    'summary': 'Quản lý Khách hàng và Nhà cung cấp — kế thừa res.partner',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['dl_base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/partner_category_data.xml',
        'views/customer_views.xml',
        'views/supplier_views.xml',
        'views/partner_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
