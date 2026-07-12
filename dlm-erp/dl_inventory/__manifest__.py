{
    "name": "DL-Inventory",
    "version": "17.0.1.0.0",
    "summary": "Quản lý xuất nhập kho",
    "author": "Dai Linh",
    "category": "Hidden",
    "depends": ["dl_base", "dl_product", "dl_partner", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/rbac_features.xml",
        "views/inventory_home.xml",
        "views/picking_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # ...
        ]
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
