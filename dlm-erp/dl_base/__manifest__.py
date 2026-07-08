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
            # Design tokens + mixin — PHẢI nạp đầu tiên (nguồn dùng chung,
            # cả dl_sale cũng dựa vào — xem dl_sale/__manifest__.py).
            'dl_base/static/src/scss/variables.scss',
            'dl_base/static/src/scss/mixins.scss',
            # State dùng chung sidebar (Home nav + Rail) — nạp trước component
            'dl_base/static/src/js/sidebar_state.js',
            # Component — Home dashboard (client action ir.actions.client)
            'dl_base/static/src/components/home/home.scss',
            'dl_base/static/src/components/home/home.xml',
            'dl_base/static/src/components/home/home.js',
            # Component — Rail shell điều hướng (main_components)
            'dl_base/static/src/components/rail/rail.scss',
            'dl_base/static/src/components/rail/rail.xml',
            'dl_base/static/src/components/rail/rail.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
