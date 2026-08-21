from . import test_rfq_views
from . import test_child_bom_selection
# from . import test_operation_cost
# ⚠️ test_operation_cost.py KHÔNG tồn tại trong repo (chưa từng được commit).
# Dòng import này làm bộ nạp test của Odoo chết ngay lúc load module ⇒ KHÔNG
# chạy được bất kỳ test nào của cả dự án. Tạm tắt; bật lại khi khôi phục file.
from . import test_quotation_validity
from . import test_quotation_uom
