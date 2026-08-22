from . import test_quotation_pricing_service_unit
from . import test_bom_reset_draft_guard
from . import test_res_partner_quote_stats_unit
from . import test_quotation_wizards_unit
from . import test_dl_quotation_unit
from . import test_dl_sale_order_unit
from . import test_rfq_views
from . import test_child_bom_selection
from . import test_cron_expire_quotations
# from . import test_operation_cost
# test_operation_cost.py không tồn tại trong repo (chưa từng được commit).
# Dòng import này làm bộ nạp test của Odoo chết ngay lúc load module, không
# chạy được bất kỳ test nào của cả dự án. Tạm tắt, bật lại khi khôi phục file.
from . import test_quotation_validity
from . import test_quotation_uom
from . import test_quotation_screen_access
