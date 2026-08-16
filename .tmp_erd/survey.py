# -*- coding: utf-8 -*-
"""Khảo sát schema vật lý dlm_dev: model -> bảng -> cột -> FK."""
import io, sys, json
import psycopg2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = psycopg2.connect(host='localhost', port=5432, dbname='dlm_dev',
                     user='odoo', password='123456')
cur = c.cursor()

def q(sql, args=None):
    if args:
        cur.execute(sql, args)
    else:
        cur.execute(sql)
    return cur.fetchall()

# ---- 1. Model do module dl_* KHAI SINH (owner) ----
rows = q("""
SELECT d.module, m.model, m.name, m.transient, m.id
FROM ir_model m
JOIN ir_model_data d ON d.model='ir.model' AND d.res_id=m.id
WHERE d.module LIKE 'dl\\_%'
ORDER BY d.module, m.model
""")
print("=== [1] MODEL DO dl_* KHAI SINH ===")
for r in rows:
    print("%-14s %-40s transient=%-5s | %s" % (r[0], r[1], r[2] and '', r[2]))
own_models = {}
for mod, model, name, transient, mid in rows:
    own_models.setdefault(model, []).append(mod)
    print("  %-14s %-38s transient=%s  %s" % (mod, model, transient, name))

print()
print("=== [2] MODULE dl_* CÓ FIELD TRÊN MODEL LÕI (extension) ===")
rows = q("""
SELECT d.module, f.model, count(*) AS nfield,
       count(*) FILTER (WHERE f.store) AS nstored
FROM ir_model_fields f
JOIN ir_model_data d ON d.model='ir.model.fields' AND d.res_id=f.id
WHERE d.module LIKE 'dl\\_%%'
GROUP BY 1,2 ORDER BY 1,2
""")
for r in rows:
    print("  %-14s %-40s fields=%-4s stored=%s" % r)

print()
print("=== [3] MAP model -> bảng vật lý (ir_model.model -> replace . by _) ===")
rows = q("""
SELECT m.model, m.transient,
       (SELECT string_agg(DISTINCT d.module, ',') FROM ir_model_data d
         WHERE d.model='ir.model' AND d.res_id=m.id) AS owner,
       t.table_name
FROM ir_model m
LEFT JOIN information_schema.tables t
       ON t.table_schema='public' AND t.table_name = replace(m.model,'.','_')
WHERE EXISTS (SELECT 1 FROM ir_model_data d
              WHERE d.model='ir.model' AND d.res_id=m.id AND d.module LIKE 'dl\\_%%')
ORDER BY 3,1
""")
for r in rows:
    print("  %-40s transient=%-5s owner=%-14s table=%s" % r)

c.close()
