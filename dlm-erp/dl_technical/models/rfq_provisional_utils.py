import logging


_logger = logging.getLogger(__name__)


# Kiểm tra 1 bản ghi có đang bị bản ghi khác trỏ tới không — dùng trước khi tự động dọn dữ liệu tạm (RFQ/BOM provisional).
def has_stored_many2one_reference(record, ignored=None):
    record.ensure_one()
    ignored = set(ignored or ())
    field_records = record.env["ir.model.fields"].sudo().search([
        ("relation", "=", record._name),
        ("ttype", "=", "many2one"),
    ])
    for field_record in field_records:
        key = (field_record.model, field_record.name)
        if key in ignored or not field_record.store:
            continue
        if field_record.model not in record.env.registry:
            continue
        model = record.env[field_record.model].sudo().with_context(active_test=False)
        if getattr(model, "_abstract", False) or getattr(model, "_transient", False):
            continue
        if field_record.name not in model._fields:
            continue
        try:
            with record.env.cr.savepoint():
                if model.search_count(
                        [(field_record.name, "=", record.id)], limit=1):
                    return True
        except Exception:
            _logger.exception(
                "Không thể kiểm tra tham chiếu %s.%s tới %s(%s); giữ lại bản ghi để an toàn.",
                field_record.model,
                field_record.name,
                record._name,
                record.id,
            )
            return True
    return False
