# -*- coding: utf-8 -*-
"""Khảo sát TẦNG RÀNG BUỘC từ source AST — phục vụ bảng Data Constraints & Conditions.

Bắt: _sql_constraints, @api.constrains (+ thông điệp ValidationError/UserError),
@api.onchange, @api.depends, default=, required=, selection, ondelete, index=True,
compute/store/related, digits, tracking, _order, _rec_name, _auto.
"""
import ast, io, os, sys, json, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dlm-erp')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cons_src.json')

FIELD_TYPES = {'Char', 'Text', 'Html', 'Boolean', 'Integer', 'Float', 'Monetary', 'Date',
               'Datetime', 'Binary', 'Image', 'Selection', 'Many2one', 'One2many',
               'Many2many', 'Reference', 'Many2oneReference', 'Json', 'Properties'}


def lit(n):
    try:
        return ast.literal_eval(n)
    except Exception:
        return None


def src_of(node, lines):
    """Lấy source text của 1 node."""
    try:
        return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    except Exception:
        return ''


def decorator_args(dec):
    """@api.constrains('a','b') -> ['a','b']"""
    out = []
    if isinstance(dec, ast.Call):
        for a in dec.args:
            v = lit(a)
            if isinstance(v, str):
                out.append(v)
    return out


def dec_name(dec):
    f = dec.func if isinstance(dec, ast.Call) else dec
    try:
        return ast.unparse(f)
    except Exception:
        return ''


def extract_messages(fn):
    """Mọi ValidationError/UserError raise trong 1 method -> list thông điệp (đã rút gọn)."""
    msgs = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Raise) or n.exc is None:
            continue
        exc = n.exc
        if not isinstance(exc, ast.Call):
            continue
        ename = ''
        try:
            ename = ast.unparse(exc.func)
        except Exception:
            pass
        if not any(k in ename for k in ('ValidationError', 'UserError')):
            continue
        for a in exc.args:
            txt = None
            v = lit(a)
            if isinstance(v, str):
                txt = v
            else:
                # _("...") hoặc "...".format(...) hoặc f-string
                if isinstance(a, ast.Call):
                    if a.args:
                        v2 = lit(a.args[0])
                        if isinstance(v2, str):
                            txt = v2
                        elif isinstance(a.args[0], ast.JoinedStr):
                            txt = joined(a.args[0])
                    if txt is None and isinstance(a.func, ast.Attribute) and a.func.attr == 'format':
                        v3 = lit(a.func.value)
                        if isinstance(v3, str):
                            txt = v3
                elif isinstance(a, ast.JoinedStr):
                    txt = joined(a)
                elif isinstance(a, ast.BinOp):
                    try:
                        txt = ast.unparse(a)
                    except Exception:
                        pass
            if txt:
                txt = re.sub(r'\s+', ' ', txt).strip()
                if txt and txt not in msgs:
                    msgs.append(txt[:400])
            break  # chỉ lấy arg đầu
    return msgs


def joined(js):
    out = []
    for v in js.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            out.append(v.value)
        else:
            out.append('{…}')
    return ''.join(out)


def field_info(st):
    """Assign node -> dict field, hoặc None."""
    if not (isinstance(st, ast.Assign) and len(st.targets) == 1
            and isinstance(st.targets[0], ast.Name)):
        return None
    call = st.value
    if not isinstance(call, ast.Call):
        return None
    fn = call.func
    if not (isinstance(fn, ast.Attribute) and fn.attr in FIELD_TYPES
            and isinstance(fn.value, ast.Name) and fn.value.id == 'fields'):
        return None
    kw = {}
    for k in call.keywords:
        if k.arg is None:
            continue
        v = lit(k.value)
        if v is None:
            try:
                v = '<expr:%s>' % ast.unparse(k.value)[:120]
            except Exception:
                v = '<expr>'
        kw[k.arg] = v
    pos = [lit(a) if lit(a) is not None else '<expr>' for a in call.args]
    return {'name': st.targets[0].id, 'type': fn.attr, 'pos': pos, 'kw': kw,
            'line': st.lineno}


recs = []
for mod in sorted(os.listdir(ROOT)):
    md = os.path.join(ROOT, mod)
    if not os.path.isdir(md):
        continue
    for dp, dn, fnames in os.walk(md):
        dn[:] = [d for d in dn if d not in ('__pycache__', 'static', 'i18n', 'tests')]
        for f in sorted(fnames):
            if not f.endswith('.py'):
                continue
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            try:
                text = open(path, encoding='utf-8').read()
                tree = ast.parse(text)
            except (SyntaxError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
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
                        'table': None, 'auto': True, 'order': None, 'rec_name': None,
                        'description': None,
                        'fields': [], 'sql_constraints': [], 'constrains': [],
                        'onchange': [], 'overrides': []}
                for st in node.body:
                    # ---- class attributes
                    if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                            and isinstance(st.targets[0], ast.Name):
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
                        elif t == '_rec_name':
                            info['rec_name'] = lit(st.value)
                        elif t == '_description':
                            info['description'] = lit(st.value)
                        elif t == '_sql_constraints':
                            v = lit(st.value)
                            if v:
                                info['sql_constraints'] = v
                        else:
                            fi = field_info(st)
                            if fi:
                                info['fields'].append(fi)
                    # ---- methods
                    elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        decs = [(dec_name(d), decorator_args(d)) for d in st.decorator_list]
                        for dname, dargs in decs:
                            if 'constrains' in dname:
                                info['constrains'].append({
                                    'method': st.name, 'fields': dargs,
                                    'messages': extract_messages(st),
                                    'line': st.lineno})
                            elif 'onchange' in dname:
                                info['onchange'].append({'method': st.name, 'fields': dargs})
                        # Mọi method có raise ValidationError/UserError đều là một
                        # luật nghiệp vụ mức HÀNH ĐỘNG (nút bấm / override CRUD).
                        msgs = extract_messages(st)
                        is_constrain = any('constrains' in d for d, _ in decs)
                        if msgs and not is_constrain:
                            info['overrides'].append({
                                'method': st.name,
                                'decorators': [d for d, _ in decs],
                                'messages': msgs,
                                'line': st.lineno})
                recs.append(info)

json.dump(recs, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

nm = sum(1 for r in recs if r['kind'] == 'Model')
nc = sum(len(r['constrains']) for r in recs)
ns = sum(len(r['sql_constraints']) for r in recs)
nf = sum(len(r['fields']) for r in recs)
print('classes=%d (Model=%d) fields=%d sql_constraints=%d api.constrains=%d'
      % (len(recs), nm, nf, ns, nc))
print('-> %s' % OUT)
