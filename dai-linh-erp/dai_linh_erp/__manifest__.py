{
    'name': 'Đại Linh ERP',
    'version': '17.0.1.0.0',
    'summary': 'Mini-ERP cho Công ty TNHH Đầu tư và Sản xuất Đại Linh',
    'author': 'Đại Linh ERP Team',
    'category': 'Manufacturing',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/customer_views.xml',
        'views/home_action.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dai_linh_erp/static/src/components/dlm_home/dlm_home.js',
            'dai_linh_erp/static/src/components/dlm_home/dlm_home.xml',
            'dai_linh_erp/static/src/css/dlm_home.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
