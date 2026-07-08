# -*- coding: utf-8 -*-


def migrate(cr, version):
    # Rename customer_type -> partner_type (TDS §3.3) — giữ dữ liệu Loại KH.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'res_partner'
          AND column_name IN ('customer_type', 'partner_type')
    """)
    type_cols = {r[0] for r in cr.fetchall()}
    if 'customer_type' in type_cols and 'partner_type' not in type_cols:
        cr.execute("ALTER TABLE res_partner RENAME COLUMN customer_type TO partner_type")

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'res_partner'
          AND column_name IN ('is_dlm_customer', 'is_dlm_supplier')
    """)
    cols = {r[0] for r in cr.fetchall()}
    if not {'is_dlm_customer', 'is_dlm_supplier'} <= cols:
        return

    cr.execute("ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS partner_role varchar")
    cr.execute("""
        UPDATE res_partner
           SET partner_role = CASE
               WHEN is_dlm_customer AND is_dlm_supplier THEN 'both'
               WHEN is_dlm_customer THEN 'customer'
               WHEN is_dlm_supplier THEN 'supplier'
           END
         WHERE partner_role IS NULL
           AND (is_dlm_customer IS TRUE OR is_dlm_supplier IS TRUE)
    """)
