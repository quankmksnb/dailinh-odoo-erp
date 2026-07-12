{
    "name": "DL-Product",
    "version": "17.0.1.0.0",
    "summary": "Danh mục sản phẩm, Bán thành phẩm, Vật tư - Tích hợp product.product",
    "author": "Dai Linh",
    "category": "Hidden",
    "depends": ["dl_base", "product", "stock", "uom", "dl_partner"],
    "data": [
        "security/ir.model.access.csv",
        "data/product_sequence.xml",
        "data/material_cron.xml",
        "data/material_category_data.xml",
        "views/product_views.xml",
        "views/material_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dl_product/static/src/scss/product_list.scss",
            "dl_product/static/src/scss/product_form.scss",
            "dl_product/static/src/views/product_list_controller.js",
            "dl_product/static/src/views/product_form_controller.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
