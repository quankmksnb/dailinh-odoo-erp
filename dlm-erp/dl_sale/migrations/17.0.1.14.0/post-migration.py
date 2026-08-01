def migrate(cr, version):
    """Chuẩn hóa tiền tệ của báo giá và đơn bán cũ sang VND."""
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = 'base' AND name = 'VND'
         LIMIT 1
        """
    )
    row = cr.fetchone()
    if not row:
        return
    for table in ("dl_quotation", "dl_sale_order"):
        cr.execute(
            "SELECT to_regclass(%s)",
            [table],
        )
        if cr.fetchone()[0]:
            cr.execute(f'UPDATE "{table}" SET currency_id = %s', [row[0]])
