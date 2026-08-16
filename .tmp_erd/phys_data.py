# -*- coding: utf-8 -*-
"""Mô hình dữ liệu cho ERD vật lý: bảng → cột, và danh sách khoá ngoại.

Thứ tự ưu tiên nguồn cột:
  1. §3.1 của TDS (phys_cols.json)  — để bản vẽ và tài liệu không lệch nhau;
  2. AST source (survey_src.json)   — cho 7 bảng custom §3.1 còn thiếu;
  3. khai báo tay bên dưới          — cho bảng lõi Odoo chỉ được tham chiếu.

Cạnh (FK) dùng ĐÚNG danh sách đã in ở §3.2: rel_rows.json + CORE_STOCK_FK + M2M_FK.
"""
import json
import os
import re
import sys
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(D), '.tmp_tds'))

# ─────────────────────────────── nhóm chủ đề ────────────────────────────────

GROUPS = [
    ('A', 'Partners, Users, RBAC',
     ['res_partner', 'res_users', 'res_company', 'res_country',
      'dl_rbac_feature', 'dl_rbac_operation']),
    ('B', 'Product & Material catalogue',
     ['product_product', 'product_template', 'product_category', 'product_supplierinfo',
      'uom_uom', 'dl_measurement_type', 'dl_measurement_shape', 'dl_measurement_shape_param']),
    ('C', 'Engineering: drawings, BOM, RFQ',
     ['dl_drawing', 'dl_bom', 'dl_bom_line', 'dl_bom_operation_line', 'dl_bom_template',
      'dl_bom_template_line', 'dl_bom_template_param', 'dl_bom_template_line_param_map',
      'dl_quotation_request', 'dl_quotation_request_line', 'dl_quotation_request_line_image',
      'dl_rfq_line_ir_attachment_rel', 'dl_bom_line_dl_bom_operation_line_rel']),
    ('D', 'Sales: quotations & orders',
     ['dl_quotation', 'dl_quotation_line', 'dl_quotation_price_component',
      'dl_sale_order', 'dl_sale_order_line']),
    ('E', 'Pricing configuration & approval',
     ['dl_pricing_config', 'dl_pricing_complexity_level', 'dl_pricing_waste_rule',
      'dl_pricing_operation', 'dl_pricing_operation_rule', 'dl_pricing_cost_adjustment_rule',
      'dl_pricing_profit_rule', 'dl_pricing_discount_rule', 'dl_pricing_approval_matrix',
      'dl_pricing_approval_setting', 'dl_pricing_approval_request', 'dl_config_audit_log',
      'dl_pricing_waste', 'dl_approval_level']),
    ('F', 'Inventory',
     ['stock_warehouse', 'stock_location', 'stock_picking_type', 'stock_picking', 'stock_move',
      'stock_move_line', 'stock_quant', 'stock_lot', 'procurement_group',
      'dl_scrap_recovery_report']),
]
GROUP_OF = {t: g for g, _, ts in GROUPS for t in ts}
GROUP_NAME = {g: n for g, n, _ in GROUPS}

# 5 bảng trung tâm — lặp lại trên mọi trang cần tới, dạng hộp tham chiếu xám
HUBS = ('res_partner', 'res_users', 'res_company', 'product_product', 'product_category')

# §3.1 gõ nhầm tên bảng
ALIAS = {'dl_pricing_watse_rule': 'dl_pricing_waste_rule'}

# mixin trừu tượng → các bảng thật kế thừa nó (cột của mixin thành cột thật)
MIXIN_USERS = {
    'dl.bom.header.mixin': ['dl_bom', 'dl_bom_template'],
    'dl.bom.line.mixin': ['dl_bom_line', 'dl_bom_template_line'],
    'dl.pricing.rule.mixin': ['dl_pricing_waste_rule', 'dl_pricing_operation_rule',
                              'dl_pricing_cost_adjustment_rule', 'dl_pricing_profit_rule',
                              'dl_pricing_discount_rule'],
}

MODULE_OF = {}
for _t in ('dl_rbac_feature', 'dl_rbac_operation'):
    MODULE_OF[_t] = 'dl_base'
for _t in ('dl_pricing_config', 'dl_pricing_waste', 'dl_approval_level', 'dl_config_audit_log',
           'dl_pricing_complexity_level', 'dl_pricing_operation', 'dl_pricing_approval_setting',
           'dl_pricing_approval_request', 'dl_pricing_approval_matrix', 'dl_pricing_waste_rule',
           'dl_pricing_operation_rule', 'dl_pricing_cost_adjustment_rule',
           'dl_pricing_profit_rule', 'dl_pricing_discount_rule'):
    MODULE_OF[_t] = 'dl_config'
for _t in ('dl_measurement_type', 'dl_measurement_shape', 'dl_measurement_shape_param'):
    MODULE_OF[_t] = 'dl_product'
for _t in ('dl_drawing', 'dl_bom', 'dl_bom_line', 'dl_bom_operation_line', 'dl_bom_template',
           'dl_bom_template_line', 'dl_bom_template_param', 'dl_bom_template_line_param_map',
           'dl_quotation_request', 'dl_quotation_request_line', 'dl_quotation_request_line_image',
           'dl_rfq_line_ir_attachment_rel', 'dl_bom_line_dl_bom_operation_line_rel'):
    MODULE_OF[_t] = 'dl_technical'
for _t in ('dl_quotation', 'dl_quotation_line', 'dl_quotation_price_component',
           'dl_sale_order', 'dl_sale_order_line'):
    MODULE_OF[_t] = 'dl_sale'
for _t in ('dl_scrap_recovery_report',):
    MODULE_OF[_t] = 'dl_inventory'

# bảng lõi Odoo ĐƯỢC THÊM CỘT dlm_ (9 bảng) — vẽ đầy màu, ghi rõ số cột lõi còn lại
# stock_location vào nhóm này từ 2026-08-12: RS-07 thêm dlm_no_inventory. 26 = số cột
# lõi thật, đo trên dlm_dev lúc dl_inventory chưa cài (nên không lẫn cột dlm_).
EXTENDED = {'res_partner': 58, 'res_users': 18, 'product_product': 22, 'product_category': 15,
            'product_supplierinfo': 23, 'stock_picking': 29, 'stock_move': 45, 'stock_lot': 13,
            'stock_location': 26}

# bảng lõi CHỈ THAM CHIẾU — §3.1 không định nghĩa, vẽ rút gọn
CORE_ONLY = {
    'res_company': ([('id', 'BIGSERIAL', 'PK'), ('name', 'VARCHAR', ''),
                     ('currency_id', 'INTEGER', 'FK')], 45),
    'res_country': ([('id', 'BIGSERIAL', 'PK'), ('name', 'JSONB', ''),
                     ('code', 'VARCHAR', 'U')], 14),
    'product_template': ([('id', 'BIGSERIAL', 'PK'), ('name', 'JSONB', ''),
                          ('categ_id', 'INTEGER', 'FK'), ('uom_id', 'INTEGER', 'FK'),
                          ('list_price', 'NUMERIC', ''), ('detailed_type', 'VARCHAR', '')], 33),
    'uom_uom': ([('id', 'BIGSERIAL', 'PK'), ('name', 'JSONB', ''),
                 ('category_id', 'INTEGER', 'FK'), ('factor', 'NUMERIC', '')], 11),
    'procurement_group': ([('id', 'BIGSERIAL', 'PK'), ('name', 'VARCHAR', ''),
                           ('partner_id', 'INTEGER', 'FK')], 8),
    'ir_attachment': ([('id', 'BIGSERIAL', 'PK'), ('name', 'VARCHAR', ''),
                       ('res_model', 'VARCHAR', ''), ('res_id', 'INTEGER', ''),
                       ('store_fname', 'VARCHAR', '')], 22),
    'ir_sequence': ([('id', 'BIGSERIAL', 'PK'), ('code', 'VARCHAR', ''),
                     ('prefix', 'VARCHAR', '')], 14),
    'res_currency': ([('id', 'BIGSERIAL', 'PK'), ('name', 'VARCHAR', 'U')], 15),
    'ir_model': ([('id', 'BIGSERIAL', 'PK'), ('model', 'VARCHAR', 'U')], 9),
    'res_groups': ([('id', 'BIGSERIAL', 'PK'), ('name', 'JSONB', '')], 8),
}

# bảng lõi bị FK trỏ tới nhưng nằm ngoài 56 đối tượng — vẽ hộp xám rút gọn
PERIPHERAL = ('ir_attachment', 'ir_sequence', 'res_currency', 'ir_model', 'res_groups')

# bảng nối Many2many do ORM sinh — chỉ có 2 cột, cả hai là PK ghép
M2M = {
    'dl_rfq_line_ir_attachment_rel': [('line_id', 'INTEGER', 'PK'),
                                      ('attachment_id', 'INTEGER', 'PK')],
    'dl_bom_line_dl_bom_operation_line_rel': [('dl_bom_line_id', 'INTEGER', 'PK'),
                                              ('dl_bom_operation_line_id', 'INTEGER', 'PK')],
}

PG_TYPE = {'Char': 'VARCHAR', 'Text': 'TEXT', 'Html': 'TEXT', 'Boolean': 'BOOL',
           'Integer': 'INTEGER', 'Float': 'NUMERIC', 'Monetary': 'NUMERIC', 'Date': 'DATE',
           'Datetime': 'TIMESTAMP', 'Selection': 'VARCHAR', 'Many2one': 'INTEGER',
           'Binary': 'BYTEA', 'Image': 'BYTEA', 'Json': 'JSONB', 'Reference': 'VARCHAR',
           'Many2oneReference': 'INTEGER', 'Properties': 'JSONB'}
AUDIT = [('create_uid', 'INTEGER', 'FK'), ('create_date', 'TIMESTAMP', ''),
         ('write_uid', 'INTEGER', 'FK'), ('write_date', 'TIMESTAMP', '')]


# ────────────────────────────── nguồn 1: docx ────────────────────────────────

def _clean(name):
    return re.sub(r'\s*\[[^\]]*\]', '', name).strip()


def from_docx():
    """({table: [(name, pgtype, mark)]}, {table: flag}) — FK gán sau theo danh sách cạnh."""
    raw = json.load(open(os.path.join(D, 'phys_cols.json'), encoding='utf-8'))
    mixin = {}
    out = {}
    flag = {}
    for key, v in raw.items():
        rows = []
        for c in v['cols']:
            nm = _clean(c['name'])
            if not nm or nm.lower() == 'column':
                continue
            pg = (c['pg'] or '').split(',')[0].strip() or '—'
            cons = (c['cons'] or '').upper()
            mark = 'PK' if re.search(r'\bPK\b', cons) else ('U' if 'UNIQUE' in cons else '')
            rows.append([nm if nm != 'Id' else 'id', pg, mark])
        if v['kind'] == 'Mixin':
            mixin[key] = rows
        else:
            t = ALIAS.get(key, key)
            out[t] = rows
            flag[t] = v['flag']
    # trải mixin vào bảng thật: cột mixin đứng sau cột riêng, bỏ trùng tên
    for mx, users in MIXIN_USERS.items():
        for t in users:
            if t not in out or mx not in mixin:
                continue
            have = {r[0] for r in out[t]}
            out[t] += [r for r in mixin[mx] if r[0] not in have]
    return out, flag


# ─────────────────────────────── nguồn 2: AST ────────────────────────────────

MAIL = ('mail.thread', 'mail.activity.mixin')


def _host(r):
    if r['name']:
        return r['name']
    inh = r['inherit']
    if isinstance(inh, list):
        inh = [x for x in inh if x not in MAIL]
        return inh[0] if inh else None
    return inh


def _stored(f):
    kw = f['kw']
    if kw.get('related') or kw.get('compute'):
        return kw.get('store') is True
    return True


def _has_col(f):
    if f['type'] in ('One2many', 'Many2many'):
        return False
    if f['type'] in ('Binary', 'Image') and f['kw'].get('attachment') is not False:
        return False
    return True


def from_ast():
    recs = json.load(open(os.path.join(D, 'survey_src.json'), encoding='utf-8'))
    abstracts = {r['name']: r for r in recs if r['kind'] == 'Abstract' and r['name']}
    acc = defaultdict(dict)
    mail = set()
    for r in recs:
        if r['kind'] != 'Model':
            continue
        m = _host(r)
        if not m:
            continue
        t = (r['table'] or m.replace('.', '_'))
        inh = r['inherit'] if isinstance(r['inherit'], list) else ([r['inherit']] if r['inherit'] else [])
        if any(x in MAIL for x in inh):
            mail.add(t)
        for n in inh:
            if n in abstracts:
                for f in abstracts[n]['fields']:
                    acc[t][f['name']] = f
        for f in r['fields']:
            acc[t][f['name']] = f
    out = {}
    for t, fl in acc.items():
        rows = [['id', 'BIGSERIAL', 'PK']]
        for name, f in fl.items():
            if not (_stored(f) and _has_col(f)):
                continue
            mark = 'U' if f['kw'].get('required') is True and name == 'code' else ''
            rows.append([name, PG_TYPE.get(f['type'], 'VARCHAR'), mark])
        rows += [list(a) for a in AUDIT]
        if t in mail:
            rows.append(['message_main_attachment_id', 'INTEGER', 'FK'])
        out[t] = rows
    return out


# ─────────────────────────────── cạnh (FK) ───────────────────────────────────

def edges():
    """Đúng danh sách đã in ở §3.2: (child, col, parent, ondelete, nullable)."""
    import sec3_rel as R
    src = json.load(open(os.path.join(D, 'rel_rows.json'), encoding='utf-8'))
    out = []
    for child, col, parent, card, ondel, nullable, idx in src:
        if GROUP_OF.get(child):
            out.append((child, col, parent, ondel, nullable))
    out += [tuple(x) for x in R.CORE_STOCK_FK]
    out += [tuple(x) for x in R.M2M_FK]
    return out


# ─────────────────────────────── ráp lại ─────────────────────────────────────

def build():
    docx, flag = from_docx()
    ast = from_ast()
    fks = edges()
    fk_of = defaultdict(dict)
    for child, col, parent, ondel, nullable in fks:
        fk_of[child][col] = parent

    tables = {}
    for t in list(GROUP_OF) + list(PERIPHERAL):
        if t in M2M:
            rows, footer, src, style = [list(r) for r in M2M[t]], None, 'manual', 'm2m'
        elif t in CORE_ONLY:
            spec, total = CORE_ONLY[t]
            rows = [list(r) for r in spec]
            footer = '+ %d further core columns' % (total - len(rows))
            src, style = 'manual', 'core'
        elif t in docx:
            rows = [list(r) for r in docx[t]]
            src = 'docx'
            if t in EXTENDED:
                # cột lõi còn lại = tổng cột thật trừ số cột lõi ĐÃ vẽ (dlm_ là cột mới)
                shown = len([r for r in rows if not r[0].startswith('dlm_')])
                footer = '+ %d further core columns' % max(EXTENDED[t] - shown, 0)
                style = 'ext'
            elif flag.get(t) == 'Native':
                footer, style = None, 'core'
            else:
                footer, style = None, 'custom'
        elif t in ast:
            rows, footer, src, style = [list(r) for r in ast[t]], None, 'ast', 'custom'
        else:
            rows, footer, src, style = [['id', 'BIGSERIAL', 'PK']], None, 'missing', 'custom'
        if t == 'dl_scrap_recovery_report':
            style = 'view'
        for r in rows:
            if not r[2] and r[0] in fk_of.get(t, {}):
                r[2] = 'FK'
        tables[t] = {'group': GROUP_OF.get(t), 'module': MODULE_OF.get(t, 'odoo_core'),
                     'style': style, 'cols': rows, 'footer': footer, 'src': src}
    return tables, fks


if __name__ == '__main__':
    import io
    o = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    tabs, fks = build()
    o.write('bang: %d | canh FK: %d\n\n' % (len(tabs), len(fks)))
    for g, name, ts in GROUPS:
        o.write('--- %s %s\n' % (g, name))
        for t in ts:
            v = tabs[t]
            o.write('  %-38s %-7s %-8s %2d cot  %s\n'
                    % (t, v['style'], v['src'], len(v['cols']), v['footer'] or ''))
    miss = [t for t, v in tabs.items() if v['src'] == 'missing']
    o.write('\nKHONG co nguon cot: %s\n' % (miss or 'khong'))
    unknown = sorted({p for _, _, p, _, _ in fks if p not in tabs})
    o.write('bang CHA ngoai 56 (se ve rut gon): %s\n' % unknown)
    o.flush()
