{
    'name': 'DL-CRM & Báo giá',
    'version': '17.0.1.12.0',
    'summary': 'Quản lý Khách hàng, NCC, RFQ và Báo giá — Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['dl_partner', 'dl_product', 'dl_technical', 'dl_base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/rbac_features.xml',
        'data/quotation_cron.xml',
        'wizard/quotation_reject_wizard_views.xml',
        'wizard/quotation_revision_wizard_views.xml',
        'views/customer_views_ext.xml',
        'views/quotation_views.xml',
        'views/quote_approval_views.xml',
        'views/sale_order_views.xml',
        'views/rfq_views_ext.xml',
        'views/quote_actions.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # SCSS — token & mixin dùng chung nằm ở dl_base (nạp trước theo
            # thứ tự phụ thuộc). Ở đây chỉ còn style theo màn của dl_sale.
            'dl_sale/static/src/scss/control_panel.scss',
            'dl_sale/static/src/scss/quotation_form.scss',
            'dl_sale/static/src/scss/quotation_list.scss',
            'dl_sale/static/src/scss/quote_approval_list.scss',
            'dl_sale/static/src/scss/quote_approval_form.scss',
            'dl_sale/static/src/scss/customer_list.scss',
            'dl_sale/static/src/scss/customer_kanban.scss',
            'dl_sale/static/src/scss/customer_form.scss',
            'dl_sale/static/src/scss/supplier_list.scss',
            'dl_sale/static/src/scss/supplier_form.scss',
            # Component — field widget dl_stepper (style co-located)
            'dl_sale/static/src/components/stepper/stepper_field.scss',
            'dl_sale/static/src/components/stepper/stepper_field.js',
            'dl_sale/static/src/components/stepper/stepper_field.xml',
            # Views — list (lớp cơ sở DlListBaseController + actions_menu nằm
            # ở dl_base, nạp trước theo thứ tự phụ thuộc)
            'dl_sale/static/src/views/quotation_list_controller.js',
            'dl_sale/static/src/views/quote_approval_list_controller.js',
            'dl_sale/static/src/views/quote_approval_form_controller.js',
            'dl_sale/static/src/views/customer_list_controller.js',
            'dl_sale/static/src/views/supplier_list_controller.js',
            'dl_sale/static/src/views/saleorder_list_controller.js',
            'dl_sale/static/src/views/customer_kanban_controller.js',
            # Views — form
            'dl_sale/static/src/views/quotation_form_controller.js',
            'dl_sale/static/src/views/customer_form_controller.js',
            'dl_sale/static/src/views/supplier_form_controller.js',
            'dl_sale/static/src/views/saleorder_form_controller.js',
            # JS — patch điều hướng
            'dl_sale/static/src/js/nav_patch.js',
            # Component — Hub Báo giá (Tạo RFQ · Quản lý RFQ · Báo giá · Đơn bán hàng)
            'dl_sale/static/src/components/quote_home/quote_home.scss',
            'dl_sale/static/src/components/quote_home/quote_home.js',
            'dl_sale/static/src/components/quote_home/quote_home.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
