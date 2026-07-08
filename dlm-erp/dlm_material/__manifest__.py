{
    'name': 'DLM-ERP Vật tư',
    'version': '17.0.2.0.0',
    'summary': 'Danh mục Vật tư & Bảng giá Vật tư theo thời gian (lịch sử, cảnh báo hết hạn)',
    'author': 'Dai Linh',
    'category': 'Hidden',
    # product: dl.material dùng _inherits = {'product.product': 'product_id'}.
    # dl_sale: định nghĩa NCC (partner_role='supplier') mà dl.material.price tham chiếu,
    # và JS controller Vật tư tái dùng DlListBaseController/actions_menu của dl_sale.
    # (Tab 'Giá vật tư' trong form NCC do dlm_supplier đảm nhiệm, không lặp lại ở đây.)
    'depends': ['dl_base', 'mail', 'product', 'dl_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/rbac_features.xml',
        'views/material_views.xml',
        'views/material_price_views.xml',
        'views/res_config_settings_views.xml',
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
