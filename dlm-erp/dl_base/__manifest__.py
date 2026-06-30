{
    'name': 'DLM-ERP Base',
    'version': '17.0.1.0.0',
    'summary': 'App gốc — định nghĩa Groups (CEO/Admin/BA/Tech) và menu chính 5 module Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['base', 'web'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/actions.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dl_base/static/src/components/dlm_home/dlm_home.scss',
            'dl_base/static/src/components/dlm_home/dlm_home.xml',
            'dl_base/static/src/components/dlm_home/dlm_home.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
