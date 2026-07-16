# -*- coding: utf-8 -*-
"""Phân loại lại nhóm khách hàng cho dữ liệu cũ.

dlm_customer_group chuyển thành computed-stored — Odoo KHÔNG tự tính lại cho các
res.partner đã tồn tại trước khi có field. Migration post chạy sau khi cột +
compute đã sẵn sàng, tính lại cho toàn bộ khách hàng.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].search(
        [('partner_role', 'in', ('customer', 'both'))])
    if not partners:
        return
    partners._compute_dlm_customer_group()
    partners.flush_recordset(['dlm_customer_group'])
