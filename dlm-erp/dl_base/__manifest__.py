{
    'name': 'DLM-ERP Base',
    'version': '17.0.1.0.0',
    'summary': 'App gốc — định nghĩa Groups (CEO/Admin/BA/Tech) và menu chính 5 module Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/actions.xml',
        'views/menus.xml',
        'data/demo_users_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Design tokens + mixin — PHẢI nạp đầu tiên (nguồn dùng chung,
            # cả dl_sale cũng dựa vào — xem dl_sale/__manifest__.py).
            'dl_base/static/src/scss/variables.scss',
            'dl_base/static/src/scss/mixins.scss',
            # State dùng chung sidebar (Home nav + Rail) — nạp trước component
            'dl_base/static/src/js/sidebar_state.js',
            # JS — hạ tầng list/form dùng chung toàn hệ thống (menu ⋮ Thao
            # tác + DlListBaseController). Các module con (dl_sale, dl_product,
            # dl_bom, dl_config...) đều import từ đây, KHÔNG từ dl_sale, để
            # tránh phụ thuộc vòng (dl_sale lại depends dl_product).
            'dl_base/static/src/js/actions_menu.js',
            'dl_base/static/src/views/dl_list_controller.js',
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
