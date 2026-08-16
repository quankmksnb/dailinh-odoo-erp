# -*- coding: utf-8 -*-
"""Kiem ke bang vat ly tu SOURCE (survey_src.json) -> table_inventory.json + ban in.

Phan loai:
  NEW      bang moi do dl_* tao (models.Model co _name khong trung core)
  EXT      bang loi Odoo duoc _inherit va CO them cot luu tru (dlm_*)
  REF      bang loi Odoo chi duoc tham chieu qua FK (khong ve cot moi)
  M2M      bang quan he many2many
  TRANS    TransientModel (wizard) - KHONG co bang thuong tru
  ABS      AbstractModel (mixin) - KHONG co bang
"""
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
D = os.path.dirname(os.path.abspath(__file__))
RECS = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def stored(f):
    """Field co sinh cot trong bang khong?"""
    kw = f['kw']
    if f['type'] == 'One2many':
        return False
    if f['type'] == 'Many2many':
        return False          # sinh bang rel rieng
    if kw.get('compute') and not kw.get('store'):
        return False
    if kw.get('related') and not kw.get('store'):
        return False
    return True


MIXINS = {'mail.thread', 'mail.activity.mixin', 'portal.mixin', 'image.mixin',
          'mail.thread.blacklist', 'avatar.mixin'}

# ---------------------------------------------------------------- gom theo model
model_defs = defaultdict(list)      # model name -> [rec]
for r in RECS:
    inh = as_list(r['inherit'])
    if r['name']:
        key = r['name']
    elif len(inh) == 1:
        key = inh[0]
    else:
        continue
    model_defs[key].append(r)

rows = []
m2m_tables = {}

for model, defs in sorted(model_defs.items()):
    kinds = {d['kind'] for d in defs}
    owns = any(d['name'] and (not as_list(d['inherit']) or
                              d['name'] not in as_list(d['inherit'])) for d in defs)
    # kind
    if 'Abstract' in kinds:
        cat = 'ABS'
    elif 'Transient' in kinds:
        cat = 'TRANS'
    elif owns:
        cat = 'NEW'
    else:
        cat = 'EXT'

    table = None
    for d in defs:
        if d['table']:
            table = d['table']
    if not table:
        table = model.replace('.', '_')

    ncols = 0
    added = []
    for d in defs:
        for f in d['fields']:
            if stored(f):
                ncols += 1
                added.append(f['name'])
            if f['type'] == 'Many2many':
                kw, pos = f['kw'], f['pos']
                comodel = kw.get('comodel_name') or (pos[0] if pos else None)
                if kw.get('compute') and not kw.get('store'):
                    continue                       # compute khong store -> khong co bang
                rel = kw.get('relation') or (pos[1] if len(pos) > 1 else None)
                if not isinstance(rel, str):       # Odoo tu sinh ten: sap xep 2 bang
                    if not isinstance(comodel, str):
                        continue
                    a, b = sorted([model.replace('.', '_'), comodel.replace('.', '_')])
                    rel = '%s_%s_rel' % (a, b)
                m2m_tables[rel] = (model, comodel, f['name'], d['file'])
    rows.append({
        'model': model, 'table': table, 'cat': cat,
        'modules': sorted({d['module'] for d in defs}),
        'files': sorted({'%s:%d' % (d['file'], d['line']) for d in defs}),
        'ncols': ncols, 'cols': added,
        'mixins': sorted({i for d in defs for i in as_list(d['inherit']) if i in MIXINS}),
        'inherits': next((d['inherits'] for d in defs if d['inherits']), None),
        'sql': [c for d in defs for c in (d['sql_constraints'] or [])],
    })

# ---------------------------------------------------------------- FK -> bang loi
core_ref = defaultdict(set)
own_models = {r['model'] for r in rows}
for r in RECS:
    src = r['name'] or (as_list(r['inherit'])[0] if len(as_list(r['inherit'])) == 1 else '?')
    for f in r['fields']:
        if f['type'] in ('Many2one', 'Many2many'):
            co = f['kw'].get('comodel_name') or (f['pos'][0] if f['pos'] else None)
            if isinstance(co, str) and not co.startswith('dl.'):
                core_ref[co].add(src)

# ---------------------------------------------------------------- in bao cao
def show(cat, title):
    sel = [r for r in rows if r['cat'] == cat]
    print('\n=== %s  (%d) ===' % (title, len(sel)))
    for r in sorted(sel, key=lambda x: (x['modules'][0], x['table'])):
        mix = ' +' + ','.join(m.split('.')[1] for m in r['mixins']) if r['mixins'] else ''
        print('%-38s %-34s %-11s %3d cot%s' % (
            r['table'], r['model'], r['modules'][0], r['ncols'], mix))
        print('%-38s   %s' % ('', '; '.join(r['files'])))


show('NEW', 'BANG MOI (custom storage)')
show('EXT', 'BANG LOI ODOO DUOC MO RONG (them cot dlm_*)')
show('TRANS', 'TRANSIENT / WIZARD - KHONG CO BANG THUONG TRU')
show('ABS', 'ABSTRACT MIXIN - KHONG CO BANG')

print('\n=== BANG QUAN HE M2M (%d) ===' % len(m2m_tables))
for t, (a, b, fld, f) in sorted(m2m_tables.items()):
    print('%-42s %s.%s  <->  %s   [%s]' % (t, a, fld, b, f))

print('\n=== BANG LOI ODOO CHI THAM CHIEU (%d) ===' % len(core_ref))
ext_models = {r['model'] for r in rows if r['cat'] == 'EXT'}
for co in sorted(core_ref):
    if co in ext_models:
        continue
    print('%-30s <- %s' % (co.replace('.', '_'), ', '.join(sorted(core_ref[co])[:4])))

json.dump({'tables': rows, 'm2m': m2m_tables,
           'core_ref': {k: sorted(v) for k, v in core_ref.items()}},
          open(os.path.join(D, 'table_inventory.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\n-> table_inventory.json')
