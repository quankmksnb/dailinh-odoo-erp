{
    'name': 'DL-CRM & Báo giá',
    'version': '17.0.1.0.0',
    'summary': 'Quản lý Khách hàng, NCC, RFQ và Báo giá — Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['dl_base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/customer_views.xml',
        'views/supplier_views.xml',
        'views/quotation_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
