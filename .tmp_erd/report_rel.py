# -*- coding: utf-8 -*-
"""Sinh danh sách QUAN HỆ (FK) cho §3.2 Entity Relationships của TDS."""
import io, os, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

D = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))
MAIL = ('mail.thread', 'mail.activity.mixin')
SKIP_COL = {'create_uid', 'write_uid', 'message_main_attachment_id'}


def host(r):
    if r['name']:
        return r['name']
    inh = r['inherit']
    if isinstance(inh, list):
        inh = [x for x in inh if x not in MAIL]
        return inh[0] if inh else None
    return inh


def stored(f):
    kw = f['kw']
    if kw.get('related') or kw.get('compute'):
        return kw.get('store') is True
    return True


abstracts = {r['name']: r for r in recs if r['kind'] == 'Abstract' and r['name']}
transient = {r['name'] for r in recs if r['kind'] == 'Transient' and r['name']}
views = {r['name'] for r in recs if r['auto'] is False and r['name']}

fields = defaultdict(dict)
for r in recs:
    if r['kind'] == 'Abstract':
        continue
    m = host(r)
    if not m:
        continue
    inh = r['inherit'] if isinstance(r['inherit'], list) else ([r['inherit']] if r['inherit'] else [])
    for n in inh:
        if n in abstracts:
            for f in abstracts[n]['fields']:
                fields[m][f['name']] = f
    for f in r['fields']:
        fields[m][f['name']] = f

# one2many: dùng để suy cardinality 1-N phía cha
o2m = defaultdict(set)
for m, fl in fields.items():
    for f in fl.values():
        if f['type'] == 'One2many':
            co = f['kw'].get('comodel_name') or (f['pos'][0] if f['pos'] else None)
            inv = f['kw'].get('inverse_name') or (f['pos'][1] if len(f['pos']) > 1 else None)
            if co and inv:
                o2m[(co, inv)].add(m)

rows = []
for m in sorted(fields):
    if m in transient:
        continue
    for name, f in fields[m].items():
        if f['type'] != 'Many2one' or not stored(f) or name in SKIP_COL:
            continue
        co = f['kw'].get('comodel_name') or (f['pos'][0] if f['pos'] else None)
        if not isinstance(co, str) or co in transient:
            continue
        req = f['kw'].get('required') is True
        od = f['kw'].get('ondelete') or ('restrict' if req else 'set null')
        card = '1 : N' if (co, name) in o2m else 'N : 1'
        rows.append((m.replace('.', '_'), name, co.replace('.', '_'),
                     card, od.upper(), 'NOT NULL' if req else 'NULL',
                     'Y' if (f['kw'].get('index') is True) else ''))

print('total FK rows (bo create_uid/write_uid): %d' % len(rows))
print()
for r in rows:
    print('%-34s %-30s -> %-26s %-6s %-10s %-9s %s' % r)

json.dump(rows, open(os.path.join(D, 'rel_rows.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
