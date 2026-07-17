# -*- coding: utf-8 -*-
"""Tách trạng thái báo giá: 'approved' (cũ = khách đã chốt) → 'accepted'.

Model cũ dùng 'approved' làm trạng thái thắng đơn cuối cùng. Model mới tách
'approved' = duyệt nội bộ và 'accepted' = khách đồng ý. Bản ghi cũ đang ở
'approved' thực chất là khách đã đồng ý → map sang 'accepted', rồi phân loại
lại nhóm khách hàng theo tín hiệu mới (accepted/ordered).
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    cr.execute(
        "UPDATE dl_quotation SET state = 'accepted' WHERE state = 'approved'")
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].search(
        [('partner_role', 'in', ('customer', 'both'))])
    if partners:
        partners._compute_dlm_customer_group()
        partners.flush_recordset(['dlm_customer_group'])
