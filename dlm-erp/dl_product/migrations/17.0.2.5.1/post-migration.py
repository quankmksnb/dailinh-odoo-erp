def migrate(cr, version):
    """Giữ nguyên số tiền nghiệp vụ đang lưu và chuẩn hóa ký hiệu sang VND."""
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
        cr.execute("UPDATE product_supplierinfo SET currency_id = %s", [row[0]])
