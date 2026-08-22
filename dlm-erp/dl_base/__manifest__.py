{
    'name': 'DLM-ERP Base',
    'version': '17.0.1.16.0',
    'summary': 'App gốc — định nghĩa Groups (CEO/Admin/BA/Tech) và menu chính 5 module Phase 1',
    'author': 'Dai Linh',
    'category': 'Hidden',
    'depends': ['base', 'web', 'mail', 'uom'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/language_data.xml',
        'data/currency_data.xml',
        'data/company_data.xml',
        'views/webclient_templates.xml',
        'views/login_templates.xml',
        'views/actions.xml',
        'views/menus.xml',
        'data/demo_users_data.xml',
        'data/demo_user_language_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Design tokens + mixin — PHẢI nạp đầu tiên (nguồn dùng chung,
            # cả dl_sale cũng dựa vào — xem dl_sale/__manifest__.py).
            'dl_base/static/src/scss/variables.scss',
            'dl_base/static/src/scss/mixins.scss',
            'dl_base/static/src/scss/global_form.scss',
            'dl_base/static/src/scss/global_list.scss',
            'dl_base/static/src/scss/global_cp.scss',
            'dl_base/static/src/scss/global_dialog.scss',
            # Spinner tải dữ liệu — thay chỉ báo "Loading" gốc bằng spinner
            # xoay ở giữa màn hình (override template web.LoadingIndicator).
            'dl_base/static/src/components/loading_indicator/loading_indicator.scss',
            'dl_base/static/src/components/loading_indicator/loading_indicator.xml',
            # Lỗi nghiệp vụ → toast thay vì hộp thoại "Ôi!". Chỉ khai registry,
            # không phụ thuộc file nào nên nạp sớm; áp cho TOÀN hệ thống.
            'dl_base/static/src/js/error_toast.js',
            # Tiêu đề tab trình duyệt: "Odoo - <màn>" → "Đại Linh - <màn>".
            'dl_base/static/src/js/brand_title.js',
            # Chữ cái + màu avatar đối tác — dùng chung danh sách KH và NCC.
            'dl_base/static/src/js/avatar_letter.js',
            # State dùng chung sidebar (Home nav + Rail) — nạp trước component
            'dl_base/static/src/js/sidebar_state.js',
            # API gắn submenu vào rail cho module nghiệp vụ (thay vì mỗi module
            # copy lại hàm wireRailChildren — xem chú thích trong file).
            'dl_base/static/src/js/rail_children.js',
            # JS — hạ tầng list/form dùng chung toàn hệ thống (menu ⋮ Thao
            # tác + DlListBaseController). Các module con (dl_sale, dl_product,
            # dl_bom, dl_config...) đều import từ đây, KHÔNG từ dl_sale, để
            # tránh phụ thuộc vòng (dl_sale lại depends dl_product).
            'dl_base/static/src/js/actions_menu.js',
            'dl_base/static/src/views/dl_list_controller.js',
            'dl_base/static/src/views/dl_form_controller.js',
            # Field widget dùng chung — stepper trạng thái (thay statusbar mặc
            # định trên MỌI form dl.*). Đặt ở dl_base vì mọi module con đều dùng.
            'dl_base/static/src/components/stepper/stepper_field.scss',
            'dl_base/static/src/components/stepper/stepper_field.js',
            'dl_base/static/src/components/stepper/stepper_field.xml',
            # Bỏ đuôi ",00" cho mọi số nguyên — vá FloatField + formatter
            # "float" (dòng Tổng của list). Áp cho TOÀN hệ thống.
            'dl_base/static/src/js/float_trim.js',
            # Field widget dùng chung — tiền (group hàng nghìn LIVE khi gõ).
            # money_format.js là util dùng chung cho cả widget lẫn input OWL.
            'dl_base/static/src/js/money_format.js',
            'dl_base/static/src/components/money/money_field.js',
            'dl_base/static/src/components/money/money_field.xml',
            # Field widget dùng chung — số lượng (cắt đuôi số 0 thừa khi hiện).
            'dl_base/static/src/components/qty/qty_field.js',
            # Component — Home dashboard (client action ir.actions.client)
            'dl_base/static/src/components/home/home.scss',
            'dl_base/static/src/components/home/home.xml',
            'dl_base/static/src/components/home/home.js',
            # Component — Rail shell điều hướng (main_components)
            'dl_base/static/src/components/rail/rail.scss',
            'dl_base/static/src/components/rail/rail.xml',
            'dl_base/static/src/components/rail/rail.js',
        ],
        # Trang public (đăng nhập / đặt lại mật khẩu) — style riêng, scope
        # qua class .dl-login-* trong views/login_templates.xml.
        'web.assets_frontend': [
            'dl_base/static/src/scss/login.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
}
