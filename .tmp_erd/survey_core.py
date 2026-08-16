# -*- coding: utf-8 -*-
"""Khảo sát cột/FK của các model LÕI Odoo mà ERD vật lý cần vẽ (nhóm Kho + phụ trợ)."""
import ast, io, os, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDONS = [os.path.join(BASE, 'odoo-17.0', 'addons'),
          os.path.join(BASE, 'odoo-17.0', 'odoo', 'addons')]

WANT = sys.argv[1:] or [
    'stock.picking', 'stock.picking.type', 'stock.move', 'stock.move.line',
    'stock.quant', 'stock.lot', 'stock.location', 'stock.warehouse',
    'procurement.group', 'stock.scrap',
]
WANT = set(WANT)
FIELD_TYPES = {'Char', 'Text', 'Html', 'Boolean', 'Integer', 'Float', 'Monetary', 'Date',
               'Datetime', 'Binary', 'Image', 'Selection', 'Many2one', 'One2many',
               'Many2many', 'Reference', 'Many2oneReference', 'Json', 'Properties'}


def lit(n):
    try:
        return ast.literal_eval(n)
    except Exception:
        return None


agg = defaultdict(lambda: {'files': set(), 'fields': [], 'sql': [], 'inherits': None,
                           'table': None, 'auto': True})

for root in ADDONS:
    if not os.path.isdir(root):
        continue
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ('__pycache__', 'static', 'i18n', 'tests')]
        for f in fn:
            if not f.endswith('.py'):
                continue
            path = os.path.join(dp, f)
            try:
                src = open(path, encoding='utf-8').read()
            except Exception:
                continue
            if not any(("'%s'" % w) in src or ('"%s"' % w) in src for w in WANT):
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = [ast.unparse(b) for b in node.bases]
                if not any('models.' in b for b in bases):
                    continue
                mname = None
                buf = {'fields': [], 'sql': [], 'inherits': None, 'table': None, 'auto': True}
                for st in node.body:
                    if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                            and isinstance(st.targets[0], ast.Name)):
                        continue
                    t = st.targets[0].id
                    if t in ('_name', '_inherit'):
                        v = lit(st.value)
                        cand = v[0] if isinstance(v, list) and v else v
                        if isinstance(cand, str) and cand in WANT:
                            mname = cand
                        elif t == '_name' and isinstance(cand, str):
                            mname = mname or None
                    elif t == '_inherits':
                        buf['inherits'] = lit(st.value)
                    elif t == '_table':
                        buf['table'] = lit(st.value)
                    elif t == '_auto':
                        buf['auto'] = lit(st.value)
                    elif t == '_sql_constraints':
                        buf['sql'] = lit(st.value) or []
                    elif isinstance(st.value, ast.Call):
                        fn_ = ast.unparse(st.value.func)
                        if fn_.startswith('fields.'):
                            ft = fn_.split('.', 1)[1]
                            if ft in FIELD_TYPES:
                                kw = {}
                                for k in st.value.keywords:
                                    if not k.arg:
                                        continue
                                    kw[k.arg] = ('<expr>' if isinstance(k.value, (ast.Lambda, ast.Call))
                                                 else lit(k.value))
                                buf['fields'].append({'name': t, 'type': ft,
                                                      'pos': [lit(a) for a in st.value.args],
                                                      'kw': kw})
                if not mname:
                    continue
                a = agg[mname]
                a['files'].add(os.path.relpath(path, BASE).replace(os.sep, '/'))
                a['fields'].extend(buf['fields'])
                a['sql'].extend(buf['sql'])
                for k in ('inherits', 'table'):
                    if buf[k]:
                        a[k] = buf[k]
                if buf['auto'] is False:
                    a['auto'] = False


def stored(f):
    kw = f['kw']
    if kw.get('related'):
        return kw.get('store') is True
    if kw.get('compute'):
        return kw.get('store') is True
    return True


out = {}
for m in sorted(agg):
    a = agg[m]
    cols, fks = [], []
    seen = set()
    for f in a['fields']:
        if f['name'] in seen or not stored(f):
            continue
        seen.add(f['name'])
        if f['type'] in ('One2many', 'Many2many'):
            continue
        cols.append(f['name'])
        if f['type'] == 'Many2one':
            co = f['kw'].get('comodel_name') or (f['pos'][0] if f['pos'] else None)
            if isinstance(co, str):
                fks.append((f['name'], co, f['kw'].get('ondelete'),
                            f['kw'].get('required'), f['kw'].get('index')))
    out[m] = {'table': a['table'] or m.replace('.', '_'), 'inherits': a['inherits'],
              'ncol': len(cols), 'cols': cols, 'fks': fks, 'sql': a['sql'],
              'files': sorted(a['files'])}
    print('== %-22s table=%-22s cols=%-4d fk=%-3d inherits=%s' %
          (m, out[m]['table'], len(cols), len(fks), a['inherits']))
    for k in fks:
        print('     FK %-26s -> %-24s ondelete=%-10s required=%-5s index=%s' % k)

json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'survey_core.json'),
                    'w', encoding='utf-8'), ensure_ascii=False, indent=1)
