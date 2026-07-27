"""Backfill người/ngày duyệt + phiên bản hiện hành cho BOM đã tồn tại.

Thiết kế BOM truy xuất §11:
- approved_by/approved_date: gán = người tạo / ngày tạo cho BOM đã xác nhận/khóa
  (dữ liệu cũ không có mốc duyệt riêng — dùng create_uid/create_date là xấp xỉ
  hợp lý nhất).
- is_current: mỗi phạm vi (dl.bom theo product+bom_type; dl.bom.template theo
  nhóm SP) đánh dấu bản version cao nhất còn hiệu lực (confirmed/locked) là
  phiên bản hiện hành.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill(env, "dl.bom", ("bom_type", "product_id"))
    _backfill(env, "dl.bom.template", ("product_category_id",))


def _scope_key(rec, scope_fields):
    key = []
    for f in scope_fields:
        val = rec[f]
        key.append(val.id if hasattr(val, "id") else val)
    return tuple(key)


def _backfill(env, model_name, scope_fields):
    Model = env[model_name].with_context(active_test=False, tracking_disable=True)
    records = Model.search([])
    approved = records.filtered(lambda r: r.status in ("confirmed", "locked"))

    # 1) Người/ngày duyệt cho bản đã xác nhận/khóa.
    for rec in approved:
        vals = {}
        if not rec.approved_by:
            vals["approved_by"] = rec.create_uid.id
        if not rec.approved_date:
            vals["approved_date"] = rec.create_date
        if vals:
            rec.write(vals)

    # 2) Phiên bản hiện hành = version cao nhất còn hiệu lực mỗi phạm vi.
    current_by_scope = {}
    for rec in approved:
        key = _scope_key(rec, scope_fields)
        best = current_by_scope.get(key)
        if best is None or rec.version > best.version:
            current_by_scope[key] = rec
    current_ids = {rec.id for rec in current_by_scope.values()}

    for rec in records:
        should = rec.id in current_ids
        if rec.is_current != should:
            rec.is_current = should
