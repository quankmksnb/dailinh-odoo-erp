# -*- coding: utf-8 -*-
from . import stock_warehouse
from . import stock_move
from . import stock_picking
# Nạp SAU stock_picking: import hằng số mã loại phiếu từ đó.
from . import vendor_return_document
from . import stock_lot
from . import stock_quant
from . import product_product
# Nổ BOM ra nhu cầu vật tư — ở đây (không ở dl_technical) vì cần đọc tồn kho `stock`.
from . import dl_bom_ext
from . import dl_sale_order
# Nạp SAU dl_sale_order: dùng lại _dlm_remaining_qty / _dlm_delivery_picking_type.
from . import dl_sale_order_dispatch
