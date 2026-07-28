def migrate(cr, version):
    """Kích hoạt VND và áp dụng cho mọi công ty hiện có."""
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

    vnd_id = row[0]
    cr.execute("UPDATE res_currency SET active = TRUE WHERE id = %s", [vnd_id])
    cr.execute("UPDATE res_company SET currency_id = %s", [vnd_id])
