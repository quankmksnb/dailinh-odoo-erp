# -*- coding: utf-8 -*-
"""K21 — Đơn mua vượt ngưỡng dùng chung HÒM DUYỆT của Giám đốc.

`dl.pricing.approval.request` vốn đã generic: nó lưu ``res_model``/``res_id`` và
gọi ngược ``_on_approval_approved`` / ``_on_approval_rejected`` trên bản ghi đích
(``dl_config/models/pricing_approval.py:390,441``). Cả `dl.quotation`,
`dl.pricing.commercial` và `dl.pricing.approval.matrix` đã đi đường này.

⇒ Chỉ cần thêm một giá trị vào selection. Dựng hòm duyệt thứ hai là bắt Giám đốc
nhớ có hai chỗ phải xem — và chỗ thứ hai sẽ là chỗ bị quên.

🔴 CỐ Ý **không** dùng lại `dl.pricing.approval.matrix`: ma trận đó là thang
nhiều bậc theo GIÁ TRỊ ĐƠN BÁN với hai cấp Trưởng KD/Giám đốc. Mua hàng cần MỘT
ngưỡng và MỘT người duyệt. Nhét vào cùng một bảng là hai nghiệp vụ khác nhau
tranh một hàng cấu hình.
"""

from odoo import fields, models


class DlPricingApprovalRequest(models.Model):
    _inherit = "dl.pricing.approval.request"

    request_type = fields.Selection(
        selection_add=[("purchase_over_threshold", "Đơn mua vượt ngưỡng")],
        ondelete={"purchase_over_threshold": "cascade"},
    )


class DlPricingApprovalSetting(models.Model):
    _inherit = "dl.pricing.approval.setting"

    request_type = fields.Selection(
        selection_add=[("purchase_over_threshold", "Đơn mua vượt ngưỡng")],
        ondelete={"purchase_over_threshold": "cascade"},
    )
