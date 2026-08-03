def migrate(cr, version):
    """Đưa mọi công ty hiện có về VND khi nâng cấp từ bản cũ."""
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = 'base' AND name = 'VND'
         LIMIT 1
        """
    )
    row = cr.fetchone()
    if row:
        cr.execute("UPDATE res_company SET currency_id = %s", [row[0]])
