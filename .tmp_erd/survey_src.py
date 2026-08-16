# -*- coding: utf-8 -*-
"""Khảo sát model/bảng vật lý từ SOURCE (không cần DB)."""
import ast, io, os, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dlm-erp')
FIELD_TYPES = {'Char', 'Text', 'Html', 'Boolean', 'Integer', 'Float', 'Monetary', 'Date',
               'Datetime', 'Binary', 'Image', 'Selection', 'Many2one', 'One2many',
               'Many2many', 'Reference', 'Many2oneReference', 'Json', 'Properties'}


def lit(n):
    try:
        return ast.literal_eval(n)
    except Exception:
        return None


recs = []
for mod in sorted(os.listdir(ROOT)):
    md = os.path.join(ROOT, mod)
    if not os.path.isdir(md):
        continue
    for dp, dn, fn in os.walk(md):
        dn[:] = [d for d in dn if d not in ('__pycache__', 'static', 'i18n')]
        for f in sorted(fn):
            if not f.endswith('.py'):
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            try:
                tree = ast.parse(open(path, encoding='utf-8').read())
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = [ast.unparse(b) for b in node.bases]
                if any('TransientModel' in b for b in bases):
                    kind = 'Transient'
                elif any('AbstractModel' in b for b in bases):
                    kind = 'Abstract'
                elif any('models.Model' in b for b in bases):
                    kind = 'Model'
                else:
                    continue
                info = {'module': mod, 'file': rel, 'line': node.lineno, 'cls': node.name,
                        'kind': kind, 'name': None, 'inherit': None, 'inherits': None,
                        'table': None, 'auto': True, 'order': None,
                        'fields': [], 'sql_constraints': []}
                for st in node.body:
                    if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                            and isinstance(st.targets[0], ast.Name)):
                        continue
                    t = st.targets[0].id
                    if t == '_name':
                        info['name'] = lit(st.value)
                    elif t == '_inherit':
                        info['inherit'] = lit(st.value)
                    elif t == '_inherits':
                        info['inherits'] = lit(st.value)
                    elif t == '_table':
                        info['table'] = lit(st.value)
                    elif t == '_auto':
                        info['auto'] = lit(st.value)
                    elif t == '_order':
                        info['order'] = lit(st.value)
                    elif t == '_sql_constraints':
                        info['sql_constraints'] = lit(st.value)
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
                                info['fields'].append({'name': t, 'type': ft,
                                                       'pos': [lit(a) for a in st.value.args],
                                                       'kw': kw})
                recs.append(info)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'survey_src.json')
json.dump(recs, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('records: %d -> %s' % (len(recs), out))
