{
    'name': 'DLM-ERP Vật tư',
    'version': '17.0.1.0.0',
    'summary': 'Danh mục Vật tư & Bảng giá Vật tư theo thời gian (lịch sử, cảnh báo hết hạn)',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['dl_base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/material_views.xml',
        'views/material_price_views.xml',
        'views/res_config_settings_views.xml',
        'data/ir_cron_data.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
