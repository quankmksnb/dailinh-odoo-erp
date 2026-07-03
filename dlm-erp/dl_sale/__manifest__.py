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
    'assets': {
        'web.assets_backend': [
            # SCSS — token & mixin dùng chung nằm ở dl_base (nạp trước theo
            # thứ tự phụ thuộc). Ở đây chỉ còn style theo màn của dl_sale.
            'dl_sale/static/src/scss/control_panel.scss',
            'dl_sale/static/src/scss/quotation_form.scss',
            'dl_sale/static/src/scss/quotation_list.scss',
            'dl_sale/static/src/scss/customer_list.scss',
            'dl_sale/static/src/scss/customer_kanban.scss',
            'dl_sale/static/src/scss/customer_form.scss',
            # Component — field widget dl_stepper (style co-located)
            'dl_sale/static/src/components/stepper/stepper_field.scss',
            'dl_sale/static/src/components/stepper/stepper_field.js',
            'dl_sale/static/src/components/stepper/stepper_field.xml',
            # JS — tiện ích dùng chung (menu ⋮ Thao tác)
            'dl_sale/static/src/js/actions_menu.js',
            # Views — list (lớp cơ sở nạp trước lớp con)
            'dl_sale/static/src/views/dl_list_controller.js',
            'dl_sale/static/src/views/quotation_list_controller.js',
            'dl_sale/static/src/views/customer_list_controller.js',
            # Views — form
            'dl_sale/static/src/views/quotation_form_controller.js',
            'dl_sale/static/src/views/customer_form_controller.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
