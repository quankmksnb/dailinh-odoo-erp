# -*- coding: utf-8 -*-
"""Dựng đồ thị BẢNG + FOREIGN KEY vật lý từ survey_src.json, rồi thử phân nhóm."""
import io, os, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

D = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))

VIEW_MODELS = {r['name'] for r in recs if r['name'] and r['auto'] is False}
TRANSIENT = {r['name'] for r in recs if r['kind'] == 'Transient' and r['name']}


def host_model(r):
    if r['name']:
        return r['name']
    inh = r['inherit']
    if isinstance(inh, list):
        inh = [x for x in inh if x not in ('mail.thread', 'mail.activity.mixin')]
        return inh[0] if inh else None
    return inh


def tbl(m):
    return m.replace('.', '_') if m else None


def stored(f):
    kw = f['kw']
    if kw.get('related'):
        return kw.get('store') is True
    if kw.get('compute'):
        return kw.get('store') is True
    return True


# ---- gom field theo model ----
model_fields = defaultdict(list)
model_kind = {}
for r in recs:
    if r['kind'] == 'Abstract':
        continue
    m = host_model(r)
    if not m:
        continue
    model_kind.setdefault(m, r['kind'])
    if r['name']:
        model_kind[m] = r['kind']
    for f in r['fields']:
        model_fields[m].append((f, r['module']))

# ---- Abstract mixin: đổ field xuống model con ----
abstracts = {r['name']: r for r in recs if r['kind'] == 'Abstract' and r['name']}
for r in recs:
    if r['kind'] == 'Abstract':
        continue
    inh = r['inherit']
    names = inh if isinstance(inh, list) else ([inh] if inh else [])
    m = host_model(r)
    for n in names:
        if n in abstracts and n != m:
            for f in abstracts[n]['fields']:
                model_fields[m].append((f, abstracts[n]['module'] + '(mixin)'))

# ---- FK ----
fks = []          # (src_table, column, dst_table, ondelete, required, index)
for m, fl in model_fields.items():
    for f, mod in fl:
        if f['type'] != 'Many2one' or not stored(f):
            continue
        kw = f['kw']
        co = kw.get('comodel_name') or (f['pos'][0] if f['pos'] else None)
        if not co or not isinstance(co, str):
            continue
        fks.append((tbl(m), f['name'], tbl(co), kw.get('ondelete'),
                    kw.get('required'), kw.get('index'), co, m))

print('=' * 96)
print('SỐ LIỆU TỔNG')
print('=' * 96)
own = [r for r in recs if r['name'] and not r['name'].startswith(
    ('res.', 'product.', 'stock.', 'ir.', 'mail.', 'uom.'))]
storage = [r for r in own if r['kind'] == 'Model' and r['auto'] is not False]
views = [r for r in own if r['auto'] is False]
trans = [r for r in own if r['kind'] == 'Transient']
print('  bang custom luu tru : %d' % len(storage))
print('  SQL VIEW (_auto=False): %d  -> %s' % (len(views), [r['name'] for r in views]))
print('  bang transient      : %d' % len(trans))
print('  tong FK (m2o stored): %d' % len(fks))

# ---- nhóm chủ đề ----
GROUPS = {
    'A. Doi tac & Nguoi dung': ['res_partner', 'res_users', 'res_company', 'res_country',
                                'res_groups', 'dl_rbac_feature', 'dl_rbac_operation'],
    'B. San pham & Vat tu': ['product_product', 'product_template', 'product_category',
                             'product_supplierinfo', 'uom_uom', 'dl_measurement_type',
                             'dl_measurement_shape', 'dl_measurement_shape_param'],
    'C. Ky thuat (BOM, Ban ve, RFQ)': [
        'dl_drawing', 'dl_bom', 'dl_bom_line', 'dl_bom_operation_line', 'dl_bom_template',
        'dl_bom_template_line', 'dl_bom_template_param', 'dl_bom_template_line_param_map',
        'dl_quotation_request', 'dl_quotation_request_line', 'dl_quotation_request_line_image',
        'dl_rfq_line_ir_attachment_rel', 'dl_bom_line_dl_bom_operation_line_rel'],
    'D. Ban hang (Bao gia, Don hang)': ['dl_quotation', 'dl_quotation_line',
                                        'dl_quotation_price_component', 'dl_sale_order',
                                        'dl_sale_order_line'],
    'E. Cau hinh gia & Phe duyet': [
        'dl_pricing_config', 'dl_pricing_waste', 'dl_approval_level', 'dl_config_audit_log',
        'dl_pricing_complexity_level', 'dl_pricing_waste_rule', 'dl_pricing_operation',
        'dl_pricing_operation_rule', 'dl_pricing_cost_adjustment_rule', 'dl_pricing_profit_rule',
        'dl_pricing_discount_rule', 'dl_pricing_approval_matrix', 'dl_pricing_approval_setting',
        'dl_pricing_approval_request'],
    'F. Kho': ['stock_picking', 'stock_picking_type', 'stock_move', 'stock_move_line',
               'stock_quant', 'stock_lot', 'stock_location', 'stock_warehouse',
               'procurement_group', 'dl_scrap_recovery_report'],
}
where = {}
for g, ts in GROUPS.items():
    for t in ts:
        where[t] = g

TRANS_T = {tbl(r['name']) for r in trans}
print()
print('=' * 96)
print('PHAN BO BANG / FK THEO NHOM  (bo qua bang transient)')
print('=' * 96)
intra = defaultdict(int)
cross = defaultdict(int)
unassigned = defaultdict(list)
for s, col, d, od, req, idx, co, m in fks:
    if s in TRANS_T:
        continue
    gs, gd = where.get(s), where.get(d)
    if gs is None:
        unassigned[s].append(col)
        continue
    if gd is None:
        cross[(gs, 'ODOO CORE khac: ' + d)] += 1
    elif gs == gd:
        intra[gs] += 1
    else:
        cross[(gs, gd)] += 1

for g in GROUPS:
    n_tbl = len(GROUPS[g])
    print('  %-34s bang=%-3d FK noi bo=%-3d' % (g, n_tbl, intra[g]))
print()
print('  --- FK LIEN NHOM (canh phai cat khi tach trang) ---')
for (a, b), n in sorted(cross.items(), key=lambda x: -x[1]):
    print('    %-34s -> %-38s %d' % (a, b, n))
print()
print('  --- bang chua gan nhom ---')
for t, cols in sorted(unassigned.items()):
    print('    %-34s %s' % (t, cols))
