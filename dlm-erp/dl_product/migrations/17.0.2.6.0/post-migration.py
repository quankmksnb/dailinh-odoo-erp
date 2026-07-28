def migrate(cr, version):
    """Bỏ cờ áp dụng khỏi các bảng giá chưa/không còn hiệu lực khi nâng cấp."""
    cr.execute(
        """
        UPDATE product_supplierinfo
           SET is_applied = FALSE
         WHERE is_applied = TRUE
           AND (
               date_start IS NULL
               OR date_start > CURRENT_DATE
               OR (date_end IS NOT NULL AND date_end < CURRENT_DATE)
           )
        """
    )
