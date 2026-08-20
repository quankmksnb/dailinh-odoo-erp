# -*- coding: utf-8 -*-
from . import dl_purchase_order
# Nạp SAU dl_purchase_order: import hằng số nhóm quyền giá mua từ đó.
from . import purchase_document
from . import pricing_approval_ext
from . import stock_lot
from . import stock_picking
from . import dl_sale_order_ext
# Ghi đè giá vật tư trong engine báo giá — cần cả tồn kho lẫn giá lô.
from . import quotation_pricing_ext
