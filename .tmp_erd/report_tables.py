# -*- coding: utf-8 -*-
"""Tổng hợp danh sách BẢNG VẬT LÝ từ survey_src.json."""
import io, os, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

D = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))

STORED_SKIP = ('compute', 'related')


def is_stored(f):
    kw = f['kw']
    if kw.get('store') is True:
        return True
    if any(k in kw for k in STORED_SKIP):
        return kw.get('store') is True
    if kw.get('compute') or kw.get('related'):
        return kw.get('store') is True
    return True


own = defaultdict(list)      # model -> [rec] có _name
ext = defaultdict(list)      # model lõi -> [rec] chỉ _inherit
abst = []

for r in recs:
    if r['kind'] == 'Abstract':
        abst.append(r)
        continue
    if r['name']:
        own[r['name']].append(r)
    else:
        inh = r['inherit']
        if not inh:
            continue
        names = inh if isinstance(inh, list) else [inh]
        for n in names:
            if n in ('mail.thread', 'mail.activity.mixin'):
                continue
            ext[n].append(r)

# model do dl_* khai sinh (không kể _name trùng model lõi = kỹ thuật _inherit đầy đủ)
CORE_PREFIX = ('res.', 'product.', 'stock.', 'uom.', 'ir.', 'mail.', 'account.')
print('=' * 100)
print('A. BẢNG DO dl_* KHAI SINH (_name mới)')
print('=' * 100)
n_model = n_trans = 0
for m in sorted(own):
    rs = own[m]
    if m.startswith(CORE_PREFIX):
        continue
    kind = rs[0]['kind']
    tbl = rs[0]['table'] or m.replace('.', '_')
    nf = sum(len(x['fields']) for x in rs)
    if kind == 'Transient':
        n_trans += 1
    else:
        n_model += 1
    print('  %-9s %-42s %-42s fields=%-4d %s' %
          (kind, m, tbl, nf, ', '.join(sorted({x['module'] for x in rs}))))
print('  --> Model luu tru = %d ; Transient = %d' % (n_model, n_trans))

print()
print('=' * 100)
print('B. MODEL LÕI ODOO ĐƯỢC MỞ RỘNG (_inherit thuần / _name == core)')
print('=' * 100)
core_ext = defaultdict(list)
for m in own:
    if m.startswith(CORE_PREFIX):
        core_ext[m].extend(own[m])
for m in ext:
    if m.startswith(CORE_PREFIX):
        core_ext[m].extend(ext[m])
for m in sorted(core_ext):
    rs = core_ext[m]
    nf = sum(len(x['fields']) for x in rs)
    ns = sum(sum(1 for f in x['fields'] if is_stored(f)) for x in rs)
    print('  %-30s -> %-30s field=%-4d (uoc luong stored=%-3d)  [%s]' %
          (m, m.replace('.', '_'), nf, ns,
           ', '.join('%s/%s' % (x['module'], os.path.basename(x['file'])) for x in rs)))

print()
print('=' * 100)
print('C. MODEL dl_* ĐƯỢC MODULE KHÁC MỞ RỘNG (không tạo bảng mới)')
print('=' * 100)
for m in sorted(ext):
    if m.startswith(CORE_PREFIX):
        continue
    rs = ext[m]
    nf = sum(len(x['fields']) for x in rs)
    print('  %-42s field them=%-4d  [%s]' %
          (m, nf, ', '.join('%s/%s' % (x['module'], os.path.basename(x['file'])) for x in rs)))

print()
print('=' * 100)
print('D. ABSTRACT (KHÔNG tạo bảng)')
print('=' * 100)
for r in abst:
    print('  %-42s fields=%-4d  %s:%d' % (r['name'], len(r['fields']), r['file'], r['line']))

print()
print('=' * 100)
print('E. MANY2MANY -> bảng quan hệ')
print('=' * 100)


def own_table(r):
    if r['table']:
        return r['table']
    if r['name']:
        return r['name'].replace('.', '_')
    inh = r['inherit']
    n = inh[0] if isinstance(inh, list) else inh
    return (n or '?').replace('.', '_')


m2m = []
for r in recs:
    for f in r['fields']:
        if f['type'] != 'Many2many':
            continue
        kw = f['kw']
        pos = f['pos']
        comodel = kw.get('comodel_name') or (pos[0] if pos else None)
        rel = kw.get('relation') or (pos[1] if len(pos) > 1 else None)
        c1 = kw.get('column1') or (pos[2] if len(pos) > 2 else None)
        c2 = kw.get('column2') or (pos[3] if len(pos) > 3 else None)
        m2m.append((own_table(r), r['module'], f['name'], comodel, rel, c1, c2,
                    '%s:%d' % (r['file'], r['line'])))
for t in sorted(m2m):
    print('  %-34s %-14s %-30s -> %-28s rel=%-40s' % (t[0], t[1], t[2], t[3], t[4] or '(auto)'))
    if t[5] or t[6]:
        print('        col1=%s col2=%s' % (t[5], t[6]))
print('  --> tong m2m field = %d' % len(m2m))
