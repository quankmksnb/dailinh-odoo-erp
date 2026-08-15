# -*- coding: utf-8 -*-
"""Thêm loại yêu cầu "đơn mua vượt ngưỡng" vào hòm duyệt chung của Giám đốc."""

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
