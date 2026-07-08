{
    'name': 'DLM-ERP Cấu hình (Master Data)',
    'version': '17.0.1.0.0',
    'summary': 'Cấu hình Hệ thống, User & Phân quyền, Đơn vị tính, Công ty — Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    # uom: chứa model uom.uom mà module dựng UI lên (không tạo model mới)
    'depends': ['dl_base', 'dl_sale', 'uom'],
    'data': [
        'security/ir.model.access.csv',
        'views/config_home.xml',
        'views/uom_views.xml',
        'views/company_views.xml',
        'views/user_admin_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dl_config/static/src/js/nav_patch.js',
            'dl_config/static/src/scss/control_panel.scss',
            'dl_config/static/src/components/config_home/config_home.scss',
            'dl_config/static/src/components/config_home/config_home.xml',
            'dl_config/static/src/components/config_home/config_home.js',
            # S01 — Quản lý User & Phân quyền (OWL mock)
            'dl_config/static/src/components/user_admin/user_admin.scss',
            'dl_config/static/src/components/user_admin/user_admin.xml',
            'dl_config/static/src/components/user_admin/user_admin.js',
            # S02 — Cấu hình Hệ thống (OWL mock)
            'dl_config/static/src/components/sys_config/sys_config.scss',
            'dl_config/static/src/components/sys_config/sys_config.xml',
            'dl_config/static/src/components/sys_config/sys_config.js',
            'dl_config/static/src/scss/uom_list.scss',
            'dl_config/static/src/scss/uom_form.scss',
            'dl_config/static/src/views/uom_list_controller.js',
            'dl_config/static/src/views/uom_form_controller.js',
            'dl_config/static/src/scss/company_list.scss',
            'dl_config/static/src/scss/company_form.scss',
            'dl_config/static/src/views/company_list_controller.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
