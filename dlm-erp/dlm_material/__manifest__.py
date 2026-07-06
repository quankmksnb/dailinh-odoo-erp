{
    'name': 'DLM-ERP Vật tư',
    'version': '17.0.1.0.0',
    'summary': 'Danh mục Vật tư & Bảng giá Vật tư theo thời gian (lịch sử, cảnh báo hết hạn)',
    'author': 'Dai Linh',
    'category': 'Hidden',
    # dl_sale: định nghĩa NCC (is_dlm_supplier) mà dl.material.price tham chiếu +
    # form NCC được inherit để thêm tab 'Giá vật tư' (S04 ↔ S06).
    'depends': ['dl_base', 'mail', 'dl_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/material_views.xml',
        'views/material_price_views.xml',
        'views/res_config_settings_views.xml',
        'views/supplier_price_inherit.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Đồng bộ UI danh sách/form Vật tư với các màn dl_sale.
            'dlm_material/static/src/scss/material_list.scss',
            'dlm_material/static/src/scss/material_form.scss',
            'dlm_material/static/src/views/material_list_controller.js',
            'dlm_material/static/src/views/material_form_controller.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
