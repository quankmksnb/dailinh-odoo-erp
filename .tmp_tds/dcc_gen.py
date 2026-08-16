# -*- coding: utf-8 -*-
"""Sinh bảng 'Data Constraints & Conditions' cho từng bảng vật lý.

Nguồn: .tmp_tds/cons_src.json (AST của toàn bộ dlm-erp/).
Cột:  Field / Action | Type | Validation / Rule
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
CONS = json.load(open(os.path.join(HERE, 'cons_src.json'), encoding='utf-8'))

# model (_name hoặc _inherit) -> tên bảng vật lý
MODEL2TABLE = {
    'res.partner': 'res_partner', 'res.users': 'res_users',
    'res.company': 'res_company', 'res.country': 'res_country',
    'product.product': 'product_product', 'product.template': 'product_template',
    'product.category': 'product_category', 'product.supplierinfo': 'product_supplierinfo',
    'uom.uom': 'uom_uom',
    'stock.warehouse': 'stock_warehouse', 'stock.location': 'stock_location',
    'stock.picking.type': 'stock_picking_type', 'stock.picking': 'stock_picking',
    'stock.move': 'stock_move', 'stock.move.line': 'stock_move_line',
    'stock.quant': 'stock_quant', 'stock.lot': 'stock_lot',
    'procurement.group': 'procurement_group',
}


def table_of(rec):
    """Tên bảng vật lý của một class."""
    if rec.get('table'):
        return rec['table']
    n = rec.get('name')
    inh = rec.get('inherit')
    if n:
        if rec['kind'] == 'Abstract':
            return n                       # mixin giữ nguyên tên chấm
        return MODEL2TABLE.get(n, n.replace('.', '_'))
    if isinstance(inh, str):
        return MODEL2TABLE.get(inh, inh.replace('.', '_'))
    if isinstance(inh, list):
        for x in inh:
            if not x.startswith('mail.'):
                return MODEL2TABLE.get(x, x.replace('.', '_'))
    return None


# ───────────────────────────── làm sạch thông điệp ────────────────────────────

_STRIP_CALL = re.compile(r"^_\(\s*['\"](.*)['\"]\s*\)\s*%.*$", re.S)
_STRIP_PCT = re.compile(r"^['\"](.*)['\"]\s*%.*$", re.S)


def clean(msg):
    """Rút thông điệp lỗi về câu đọc được, bỏ vỏ _() và toán tử %."""
    m = msg.strip()
    for rx in (_STRIP_CALL, _STRIP_PCT):
        g = rx.match(m)
        if g:
            m = g.group(1)
            break
    else:
        if m.startswith('_(') and m.endswith(')'):
            m = m[2:-1].strip().strip('\'"')
    # placeholder -> ký hiệu gọn
    m = re.sub(r'%\((\w+)\)s', r'<\1>', m)
    m = re.sub(r'%s|%d|%\.\d+f|\{…\}', '…', m)
    m = m.replace('%%', '%').replace('\\n', ' ')
    m = re.sub(r'\s+', ' ', m).strip().strip('"\'')
    return m


def join_msgs(msgs, limit=3):
    out = [clean(x) for x in msgs]
    out = [x for x in out if x]
    if not out:
        return ''
    if len(out) > limit:
        out = out[:limit] + ['…']
    return ' / '.join(out)


# ───────────────────────────── phân loại luật ────────────────────────────────

FIELD_LABEL = {
    'create': 'create()', 'write': 'write()', 'unlink': 'unlink()',
    'copy': 'copy()', 'action_confirm': 'action_confirm()',
}


def kind_of_constrain(fields, rule):
    r = rule.lower()
    if any(k in r for k in ('đã tồn tại', 'trùng', 'duy nhất', 'đã có')):
        return 'Uniqueness'
    if any(k in r for k in ('không hợp lệ', 'định dạng', 'regex')):
        return 'Format'
    if any(k in r for k in ('không được âm', 'phải lớn hơn', 'trong khoảng',
                            'không được vượt', 'lớn hơn hoặc bằng')):
        return 'Range'
    if any(k in r for k in ('không được trước', 'không được sau', 'phải sau')):
        return 'Date order'
    if any(k in r for k in ('bắt buộc', 'vui lòng nhập', 'vui lòng chọn', 'hãy chọn',
                            'hãy nhập', 'phải có')):
        return 'Required'
    if len(fields) > 1:
        return 'Cross-field'
    return 'Validation'


def rows_for(table, extra=()):
    """Mọi luật của một bảng vật lý -> list [field/action, type, rule]."""
    rows = []
    seen = set()

    def add(f, t, r):
        key = (f, r)
        if not r or key in seen:
            return
        seen.add(key)
        rows.append([f, t, r])

    for rec in CONS:
        if table_of(rec) != table:
            continue
        src = rec['module']
        # 1) ràng buộc SQL
        for c in rec['sql_constraints']:
            name, defn = c[0], c[1]
            msg = clean(c[2]) if len(c) > 2 else ''
            cols = re.sub(r'^\s*unique\s*\(|\)\s*$', '', defn, flags=re.I)
            cols = ', '.join(x.strip() for x in cols.split(','))
            add(cols, 'Uniqueness',
                'DB-level: %s. %s' % (defn.upper(), msg or 'Enforced by a PostgreSQL UNIQUE index.'))
        # 2) @api.constrains
        for c in rec['constrains']:
            rule = join_msgs(c['messages'])
            if not rule:
                continue
            f = ', '.join(c['fields']) or c['method']
            add(f, kind_of_constrain(c['fields'], rule), rule)
        # 3) luật mức hành động
        for o in rec['overrides']:
            rule = join_msgs(o['messages'])
            if not rule:
                continue
            name = o['method']
            label = FIELD_LABEL.get(name, name + '()')
            t = 'CRUD guard' if name in ('create', 'write', 'unlink', 'copy') else 'Action guard'
            add(label, t, rule)
    for r in extra:
        add(*r)
    return rows


def field_rules(table):
    """Luật khai báo ở tầng field: required / default / ondelete restrict."""
    out = []
    for rec in CONS:
        if table_of(rec) != table:
            continue
        for f in rec['fields']:
            kw = f['kw']
            bits = []
            if kw.get('required') is True:
                bits.append('NOT NULL')
            if 'default' in kw and not str(kw['default']).startswith('<expr'):
                bits.append('default = %s' % kw['default'])
            if kw.get('ondelete') in ('restrict', 'cascade', 'set null'):
                bits.append('ON DELETE %s' % str(kw['ondelete']).upper())
            if bits:
                out.append([f['name'], 'Field-level', ' · '.join(bits)])
    return out


if __name__ == '__main__':
    want = sys.argv[1:] or ['res_partner', 'dl_bom', 'stock_picking',
                            'dl_quotation_request_line', 'product_supplierinfo']
    for t in want:
        rs = rows_for(t)
        print('=' * 78)
        print('%s  -> %d rule' % (t, len(rs)))
        for f, k, r in rs:
            print('  %-30s %-13s %s' % (f[:30], k, r[:105]))
