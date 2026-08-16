# -*- coding: utf-8 -*-
"""So bảng/cột trong ERD vật lý (phys_cols.json, nguồn §3.1 TDS) với SOURCE hiện tại.

Ra 3 danh sách:
  A. Bảng có trong source mà ERD chưa vẽ.
  B. Cột (lưu thật) có trong source mà §3.1 chưa ghi.
  C. Cột §3.1 ghi nhưng source không còn.
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))

src = json.load(open(os.path.join(HERE, 'survey_src.json'), encoding='utf-8'))
doc = json.load(open(os.path.join(HERE, 'phys_cols.json'), encoding='utf-8'))

ALIAS = {'dl_pricing_watse_rule': 'dl_pricing_waste_rule'}


def table_of(model):
    return model.replace('.', '_')


def stored(f):
    """Field có sinh cột trong Postgres không."""
    kw = f['kw']
    if kw.get('store') is True:
        return True
    if kw.get('compute') or kw.get('related'):
        return False
    if f['type'] == 'One2many':
        return False
    if f['type'] == 'Many2many':
        return 'rel-table'
    return True


# ── Gom field theo TÊN MODEL (gộp mọi class cùng model ở mọi module) ──────────
by_model = {}
model_kind = {}
for rec in src:
    if rec['kind'] != 'Model':
        continue
    name = rec['name']
    inh = rec['inherit']
    if not name:
        if isinstance(inh, str):
            name = inh
        elif isinstance(inh, list) and len(inh) == 1:
            name = inh[0]
        else:
            continue
    if rec['auto'] is False:
        model_kind[name] = 'SQL VIEW'
    own = bool(rec['name'])
    if own and not inh:
        model_kind.setdefault(name, 'own')
    elif own and inh:
        model_kind.setdefault(name, 'own+inherit')
    else:
        model_kind.setdefault(name, 'inherit')
    by_model.setdefault(name, []).append(rec)

# ── A. Bảng thiếu trong ERD ───────────────────────────────────────────────────
doc_tables = {ALIAS.get(k, k) for k in doc}
print('== A. Model trong source mà ERD chua co bang ==')
for model in sorted(by_model):
    tb = table_of(model)
    if tb in doc_tables or model in doc:
        continue
    kinds = model_kind.get(model)
    mods = sorted({r['module'] for r in by_model[model]})
    nfields = sum(len(r['fields']) for r in by_model[model])
    print('  %-38s %-12s fields=%-3s %s' % (model, kinds, nfields, ','.join(mods)))

print()
print('== B. Cot LUU THAT trong source ma §3.1 chua ghi ==')
m2m_extra = []
for model, recs in sorted(by_model.items()):
    tb = table_of(model)
    key = tb if tb in doc else next(
        (k for k in doc if ALIAS.get(k, k) == tb or k == model), None)
    if not key:
        continue
    documented = {c['name'].split(' ')[0] for c in doc[key]['cols']}
    missing = []
    for rec in recs:
        for f in rec['fields']:
            st = stored(f)
            if not st:
                continue
            if f['name'] in documented:
                continue
            where = '%s:%s' % (rec['file'], rec['line'])
            if st == 'rel-table':
                m2m_extra.append((model, f['name'], where))
                continue
            missing.append((f['name'], f['type'], where))
    if missing:
        print('  -- %s' % tb)
        for n, t, w in missing:
            print('     %-34s %-12s %s' % (n, t, w))

print()
print('== B2. Many2many luu that (bang trung gian) chua ghi ==')
for model, fname, where in m2m_extra:
    print('  %-30s %-34s %s' % (table_of(model), fname, where))

print()
print('== C. Cot dlm_/dl_ trong §3.1 ma source khong con ==')
for key, spec in sorted(doc.items()):
    tb = ALIAS.get(key, key)
    model = key.replace('_', '.') if key.startswith('stock_') else None
    cands = [m for m in by_model if table_of(m) == tb or m == key]
    if not cands:
        continue
    have = set()
    for m in cands:
        for rec in by_model[m]:
            have |= {f['name'] for f in rec['fields']}
    ghost = []
    for c in spec['cols']:
        n = c['name'].split(' ')[0]
        if not (n.startswith('dlm_') or n.startswith('dl_')):
            continue
        if n not in have:
            ghost.append(n)
    if ghost:
        print('  %-30s %s' % (tb, ', '.join(ghost)))
