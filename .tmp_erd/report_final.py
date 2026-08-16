# -*- coding: utf-8 -*-
"""Danh sách BẢNG VẬT LÝ cuối cùng: cột / FK / nhóm chủ đề. Nguồn = SOURCE."""
import io, os, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

D = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))

MAIL = ('mail.thread', 'mail.activity.mixin')
NO_COLUMN = ('One2many', 'Many2many')
CORE_PREFIX = ('res.', 'product.', 'stock.', 'ir.', 'mail.', 'uom.', 'procurement.')


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


def has_col(f):
    if f['type'] in NO_COLUMN:
        return False
    if f['type'] in ('Binary', 'Image') and f['kw'].get('attachment') is not False:
        return False          # attachment=True mặc định -> nằm ở ir_attachment
    return True


abstracts = {r['name']: r for r in recs if r['kind'] == 'Abstract' and r['name']}
model = defaultdict(lambda: {'kind': None, 'auto': True, 'table': None, 'modules': set(),
                             'fields': {}, 'mail': False, 'sql': []})

for r in recs:
    if r['kind'] == 'Abstract':
        continue
    m = host(r)
    if not m:
        continue
    e = model[m]
    e['modules'].add(r['module'])
    if r['name']:
        e['kind'] = r['kind']
        e['table'] = r['table'] or m.replace('.', '_')
        if r['auto'] is False:
            e['auto'] = False
    e['kind'] = e['kind'] or r['kind']
    e['table'] = e['table'] or m.replace('.', '_')
    e['sql'] += (r['sql_constraints'] or [])
    inh = r['inherit'] if isinstance(r['inherit'], list) else ([r['inherit']] if r['inherit'] else [])
    if any(x in MAIL for x in inh):
        e['mail'] = True
    for n in inh:
        if n in abstracts:
            for f in abstracts[n]['fields']:
                e['fields'][f['name']] = f
    for f in r['fields']:
        e['fields'][f['name']] = f

GROUPS = [
    ('A', 'Đối tác & Người dùng & Phân quyền',
     ['res.partner', 'res.users', 'res.company', 'res.country', 'dl.rbac.feature',
      'dl.rbac.operation']),
    ('B', 'Danh mục Sản phẩm & Vật tư',
     ['product.product', 'product.template', 'product.category', 'product.supplierinfo',
      'uom.uom', 'dl.measurement.type', 'dl.measurement.shape', 'dl.measurement.shape.param']),
    ('C', 'Kỹ thuật — Bản vẽ · BOM · RFQ',
     ['dl.drawing', 'dl.bom', 'dl.bom.line', 'dl.bom.operation.line', 'dl.bom.template',
      'dl.bom.template.line', 'dl.bom.template.param', 'dl.bom.template.line.param.map',
      'dl.quotation.request', 'dl.quotation.request.line', 'dl.quotation.request.line.image']),
    ('D', 'Kinh doanh — Báo giá & Đơn hàng',
     ['dl.quotation', 'dl.quotation.line', 'dl.quotation.price.component', 'dl.sale.order',
      'dl.sale.order.line']),
    ('E', 'Cấu hình giá & Phê duyệt',
     ['dl.pricing.config', 'dl.pricing.complexity.level', 'dl.pricing.waste.rule',
      'dl.pricing.operation', 'dl.pricing.operation.rule', 'dl.pricing.cost.adjustment.rule',
      'dl.pricing.profit.rule', 'dl.pricing.discount.rule', 'dl.pricing.approval.matrix',
      'dl.pricing.approval.setting', 'dl.pricing.approval.request', 'dl.config.audit.log',
      'dl.pricing.waste', 'dl.approval.level']),
    ('F', 'Kho — Nhập · Kiểm · Cắt · Giao · Phế liệu',
     ['stock.warehouse', 'stock.location', 'stock.picking.type', 'stock.picking',
      'stock.move', 'stock.move.line', 'stock.quant', 'stock.lot', 'procurement.group',
      'dl.scrap.recovery.report']),
]
core = json.load(open(os.path.join(D, 'survey_core.json'), encoding='utf-8'))
# số liệu THẬT lấy từ PG (bảng lõi) — xem report_pg.txt
PG = {'res_partner': (58, 11), 'res_users': (18, 5), 'res_company': (45, 13),
      'product_product': (22, 5), 'product_template': (33, 6), 'product_category': (15, 5),
      'product_supplierinfo': (23, 7), 'uom_uom': (11, 3), 'stock_picking': (29, 12),
      'stock_picking_type': (42, 9), 'stock_move': (45, 19), 'stock_move_line': (26, 14),
      'stock_quant': (20, 10), 'stock_lot': (13, 6), 'stock_location': (26, 7),
      'stock_warehouse': (28, 19), 'procurement_group': (8, 3), 'res_country': (14, 2)}
DLM_ADD = {'res_partner': 8, 'res_users': 1, 'product_product': 23, 'product_category': 3,
           'product_supplierinfo': 11, 'stock_picking': 4, 'stock_move': 3, 'stock_lot': 3}

placed = set()
tot_t = tot_c = tot_f = 0
print('| # | Nhóm | Bảng vật lý | Model Odoo | Loại | Cột | FK | Nguồn |')
print('|---|---|---|---|---|---|---|---|')
i = 0
for gid, gname, members in GROUPS:
    for m in members:
        i += 1
        placed.add(m)
        e = model.get(m)
        t = (e['table'] if e else m.replace('.', '_'))
        if m.startswith(CORE_PREFIX):
            ncol, nfk = PG.get(t, (0, 0))
            add = DLM_ADD.get(t, 0)
            kind = 'LÕI + mở rộng' if add else 'LÕI Odoo'
            colstr = '%d%s' % (ncol, (' (+%d dlm_)' % add) if add else '')
            src = ', '.join(sorted(e['modules'])) if e else 'odoo core'
        else:
            fs = [f for f in e['fields'].values() if stored(f) and has_col(f)]
            nfk = sum(1 for f in fs if f['type'] == 'Many2one')
            ncol = len(fs) + 5 + (1 if e['mail'] else 0)   # +id,create/write_uid/date
            if e['mail']:
                nfk += 1
            nfk += 2                                        # create_uid, write_uid
            kind = 'SQL VIEW' if e['auto'] is False else ('Transient' if e['kind'] == 'Transient' else 'Bảng custom')
            if e['auto'] is False:
                ncol, nfk = 4, 0
            colstr = str(ncol)
            src = ', '.join(sorted(e['modules']))
        tot_t += 1
        tot_c += (ncol if isinstance(ncol, int) else 0)
        tot_f += nfk
        print('| %d | %s | `%s` | `%s` | %s | %s | %d | %s |' %
              (i, gid, t, m, kind, colstr, nfk, src))

print()
print('TỔNG (chưa kể transient + m2m): %d bảng, ~%d cột, ~%d FK' % (tot_t, tot_c, tot_f))
print()
print('--- BẢNG CHƯA XẾP NHÓM (kiểm tra sót) ---')
for m in sorted(model):
    if m in placed:
        continue
    e = model[m]
    print('   %-40s kind=%-10s modules=%s' % (m, e['kind'], sorted(e['modules'])))
