# -*- coding: utf-8 -*-
"""Dựng lại §3.1 (nhóm A–F + bảng ràng buộc) và §3.3–§3.6 của Report 4.0_TDS.docx.

Nguồn nội dung
  s3_groups.py   bố cục 6 nhóm, chú giải cờ, 11 khối bảng CHƯA có trong tài liệu
  s3_dcc_*.py    bảng "Data Constraints & Conditions" cho đủ 56 bảng
  s3_tail.py     §3.3 Enum · §3.4 Index · §3.5 Migration · §3.6 Seed Data

Nguyên tắc: KHÔNG viết lại các bảng cột đã có trong tài liệu. Chúng được GỠ RA
rồi ĐẶT LẠI đúng nhóm, giữ nguyên từng ô. Script chỉ sinh tiêu đề, thứ tự nhóm,
các khối còn thiếu và bảng ràng buộc.

Chạy:  venv/Scripts/python.exe .tmp_tds/s3_apply.py [--dry]
"""
import io
import os
import re
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document                                       # noqa: E402
from docx.oxml.ns import qn                                     # noqa: E402

import builder as B                                             # noqa: E402
import s3_groups as G                                           # noqa: E402
import s3_tail as T                                             # noqa: E402
from s3_dcc_abc import DCC as _DCC_ABC                          # noqa: E402
from s3_dcc_def import DCC as _DCC_DEF                          # noqa: E402

DCC = dict(_DCC_ABC)
DCC.update(_DCC_DEF)

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
DRY = '--dry' in sys.argv

# ───────────────────────────── phân loại tiêu đề ─────────────────────────────
# Cùng biểu thức với .tmp_erd/phys_cols.py — bản vẽ ERD đọc §3.1 bằng chính nó,
# đổi tiêu đề mà lệch biểu thức này là bản vẽ mất bảng.
HEAD_RE = re.compile(r'^(Table|View|Mixin):\s*([A-Za-z0-9_. +]+?)\s*'
                     r'(?:\[([^\]]*)\])?\s*(?:\(.*\))?$')

KEY_FIX = {'dl_pricing_watse_rule': 'dl_pricing_waste_rule'}   # §3.1 gõ nhầm
DROP_HEAD = {'Authorization'}                                  # tiêu đề rỗng, bỏ
F_LEAD = '__f_lead__'          # khối dẫn nhập "Inventory — ..." của nhóm F
SO_INV = '__sale_order_inv__'  # khối "dl_sale_order [extended by dl_inventory]"

# Cờ trong tiêu đề — phải khớp bảng chú giải ở đầu §3.
EXTENDED = {'res_partner', 'res_users', 'product_product', 'product_category',
            'product_supplierinfo', 'stock_picking', 'stock_move', 'stock_lot',
            'stock_location'}
NATIVE = {'res_company', 'res_country', 'product_template', 'uom_uom', 'stock_warehouse',
          'stock_picking_type', 'stock_move_line', 'stock_quant', 'procurement_group'}
VIEWS = {'dl_scrap_recovery_report'}

ALL_KEYS = [k for g in G.GROUPS for k in g['keys']]


def head_text(key):
    if key in G.NEW_ENTITIES:
        return G.NEW_ENTITIES[key]['head']
    if '.' in key:
        return 'Mixin: %s [Mixin]' % key
    if key in VIEWS:
        return 'View: %s [SQL VIEW]' % key
    if key in EXTENDED:
        return 'Table: %s [Inherit]' % key
    if key in NATIVE:
        return 'Table: %s [Native]' % key
    return 'Table: %s [New]' % key


# ─────────────────────────────── đọc tài liệu ────────────────────────────────

def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def pstyle(p):
    ppr = p.find(qn('w:pPr'))
    st = ppr.find(qn('w:pStyle')) if ppr is not None else None
    return st.get(qn('w:val')) if st is not None else 'Normal'


def first_cell(tbl):
    tr = tbl.find(qn('w:tr'))
    if tr is None:
        return ''
    tc = tr.find(qn('w:tc'))
    if tc is None:
        return ''
    return ' '.join(''.join(t.text or '' for t in tc.iter(qn('w:t'))).split())


def walk(el):
    """Duyệt block, chui vào w:sdt (tài liệu đầy vỏ sdt goog_rdk_* của Google Docs)."""
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p', 'tbl'):
            yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c):
                    yield x


def die(msg):
    print('DUNG: %s' % msg)
    sys.exit(1)


def anchor_of(items, style, prefix):
    hits = [i for i, (t, el) in enumerate(items)
            if t == 'p' and pstyle(el) == style and ptext(el).strip().startswith(prefix)]
    if len(hits) != 1:
        die('tim thay %d cho cho tieu de %r (can dung 1)' % (len(hits), prefix))
    return hits[0]


def key_of(title):
    if title in DROP_HEAD:
        return None
    if title.startswith('Inventory'):
        return F_LEAD
    m = HEAD_RE.match(title)
    if not m:
        return '?? ' + title
    name = m.group(2).split('+')[0].strip()
    flag = (m.group(3) or '').strip()
    if name == 'dl_sale_order' and 'extended' in flag:
        return SO_INV
    return KEY_FIX.get(name, name)


# ──────────────────────────────── dựng khối ──────────────────────────────────

def dcc_table(key):
    rows = [list(r) for r in DCC[key]]
    return B.table(G.DCC_HEADERS, rows, G.DCC_WIDTHS,
                   banner='Data Constraints & Conditions')


def keep_els(block):
    """Nội dung cũ của một khối, bỏ đoạn rỗng và bảng ràng buộc cũ."""
    out = []
    for tag, el in block['els']:
        if tag == 'p' and not ptext(el).strip():
            continue
        if tag == 'tbl' and first_cell(el).startswith('Data Constraints'):
            continue
        out.append(el)
    return out


def block_new(key):
    d = G.NEW_ENTITIES[key]
    out = [B.para(d['head'], style='Heading4')]
    for k in ('desc', 'meta'):
        if d.get(k):
            out.append(B.para(d[k], style='Normal'))
    if d.get('cols'):
        out.append(B.table(G.CH, d['cols'], G.CW))
    if d.get('extra'):
        out.append(B.para(d['extra'], style='Normal'))
    if d.get('note'):
        out.append(B.note_box(*d['note']))
    return out


# ──────────────────────────────── §3.3–§3.6 ──────────────────────────────────

def build_tail():
    out = [
        B.para('3.3 Enum / Lookup Values', style='Heading2'),
        B.para(T.ENUM_LEAD, style='Normal'),
        B.table(T.ENUM_HEADERS, T.ENUM_ROWS, T.ENUM_WIDTHS),
        B.note_box(*T.ENUM_NOTE),

        B.para('3.4 Indexing Strategy', style='Heading2'),
        B.para(T.IDX_LEAD, style='Normal'),
        B.table(T.IDX_HEADERS, T.IDX_ROWS, T.IDX_WIDTHS),
        B.note_box(*T.IDX_NOTE),

        B.para('3.5 Migration Strategy', style='Heading2'),
        B.para(T.MIG_LEAD, style='Normal'),
        B.table(T.MIG_HEADERS, T.MIG_ROWS, T.MIG_WIDTHS),
        B.note_box(*T.MIG_NOTE),

        B.para('3.6 Seed Data', style='Heading2'),
        B.para(T.SEED_LEAD, style='Normal'),
        B.para('Minimum accounts required:', style='Heading3'),
        B.table(T.SEED_ACC_HEADERS, T.SEED_ACC_ROWS, T.SEED_ACC_WIDTHS),
        B.para('Minimum domain data required:', style='Heading3'),
        B.table(T.SEED_DOM_HEADERS, T.SEED_DOM_ROWS, T.SEED_DOM_WIDTHS),
        B.note_box(*T.SEED_NOTE),
    ]
    return out


# ───────────────────────────── sửa style Heading 4 ───────────────────────────

def restyle_h4(doc):
    """Heading 4 chưa dùng ở đâu (mặc định nghiêng, xanh dương). Đổi về lối nhà:
    đậm, màu xanh lá của tài liệu, có khoảng cách trên."""
    for st in doc.styles.element.findall(qn('w:style')):
        if st.get(qn('w:styleId')) != 'Heading4':
            continue
        ppr = st.find(qn('w:pPr'))
        if ppr is not None:
            sp = ppr.find(qn('w:spacing'))
            if sp is not None:
                sp.set(qn('w:before'), '200')
                sp.set(qn('w:after'), '60')
            kn = ppr.find(qn('w:keepNext'))
            if kn is not None:
                kn.set(qn('w:val'), '1')
        rpr = st.find(qn('w:rPr'))
        if rpr is not None:
            for tag, val in (('w:b', '1'), ('w:bCs', '1'), ('w:i', '0'), ('w:iCs', '0')):
                e = rpr.find(qn(tag))
                if e is not None:
                    e.set(qn('w:val'), val)
            c = rpr.find(qn('w:color'))
            if c is not None:
                c.set(qn('w:val'), B.HDR_FILL)
        return True
    return False


# ──────────────────────────────────── main ───────────────────────────────────

def main():
    doc = Document(SRC)
    body = doc.element.body
    items = list(walk(body))

    i31 = anchor_of(items, 'Heading2', '3.1 Entity Definitions')
    i32 = anchor_of(items, 'Heading2', '3.2 Entity Relationships')
    i33 = anchor_of(items, 'Heading2', '3.3 Enum / Lookup Values')
    i40 = anchor_of(items, 'Heading1', '4. Security Design')
    if not i31 < i32 < i33 < i40:
        die('thu tu tieu de bat thuong: %s' % [i31, i32, i33, i40])

    # 1. gom khối cũ của §3.1 ------------------------------------------------
    blocks, cur, stray = [], None, []
    for i in range(i31 + 1, i32):
        tag, el = items[i]
        if tag == 'p' and pstyle(el) == 'Heading3':
            cur = {'title': ptext(el).strip(), 'head_el': el, 'els': []}
            blocks.append(cur)
        elif cur is None:
            if not (tag == 'p' and not ptext(el).strip()):
                stray.append((tag, el))
        else:
            cur['els'].append((tag, el))

    have, dup = {}, []
    for b in blocks:
        k = key_of(b['title'])
        b['key'] = k
        if k is None:
            continue
        if k in have:
            dup.append(b['title'])
        have[k] = b

    unknown = [b['title'] for b in blocks if (b['key'] or '').startswith('??')]
    orphan = [k for k in have if k not in ALL_KEYS and k not in (F_LEAD, SO_INV)]
    missing = [k for k in ALL_KEYS if k not in have and k not in G.NEW_ENTITIES]
    nodcc = [k for k in ALL_KEYS if k not in DCC]

    print('khoi §3.1 doc duoc      : %d' % len(blocks))
    print('khoa dung lai            : %d' % len([k for k in have if k in ALL_KEYS]))
    print('khoa dung mau moi        : %d' % len(G.NEW_ENTITIES))
    print('tong khoa theo bo cuc    : %d' % len(ALL_KEYS))
    if stray:
        print('!! noi dung truoc khoi dau tien: %d phan tu' % len(stray))
    if dup:
        print('!! tieu de trung (lay ban CUOI): %s' % dup)
    if unknown:
        die('tieu de khong hieu: %s' % unknown)
    if orphan:
        die('khoi cu khong nam trong bo cuc A-F: %s' % orphan)
    if missing:
        die('bo cuc doi khoi chua co va cung khong co mau: %s' % missing)
    if nodcc:
        die('thieu bang rang buoc cho: %s' % nodcc)
    if F_LEAD not in have or SO_INV not in have:
        die('khong thay khoi dan nhap Kho hoac khoi dl_sale_order mo rong')

    # 2. dựng chuỗi phần tử mới của §3.1 -------------------------------------
    new = [B.para(G.INTRO, style='Normal')]
    report = []
    for grp in G.GROUPS:
        new.append(B.para('%s  (%s)' % (grp['title'], grp['count']), style='Heading3'))
        new.append(B.para(grp['lead'], style='Normal'))
        if grp['letter'] == 'F':      # giữ hộp "Stored versus computed" của khối cũ
            new.extend([el for tag, el in have[F_LEAD]['els'] if tag == 'tbl'])
        for key in grp['keys']:
            if key in have:
                new.append(B.para(head_text(key), style='Heading4'))
                new.extend(keep_els(have[key]))
                src = 'cu'
            else:
                new.extend(block_new(key))
                src = 'MOI'
            if key == 'dl_sale_order':          # 2 cột do dl_inventory thêm
                blk = have[SO_INV]
                new.append(B.para(blk['title'], bold=True, sz=22))
                new.extend(keep_els(blk))
            new.append(dcc_table(key))
            report.append((grp['letter'], key, src, len(DCC[key])))

    for spec in (G.DEPRECATED, G.M2M, G.TRANSIENT):
        new.append(B.note_box(spec['label'], spec['text']))

    tail = build_tail()

    # 3. báo cáo --------------------------------------------------------------
    for letter, key, src, n in report:
        print('  %s  %-34s %-3s  %2d dong rang buoc' % (letter, key, src, n))
    print('phan tu moi cho §3.1: %d · cho §3.3-3.6: %d' % (len(new), len(tail)))
    if DRY:
        print('--dry: khong ghi file')
        return

    # 4. thay thế -------------------------------------------------------------
    shutil.copy2(SRC, SRC.replace('.docx', '.backup-%s.docx'
                                  % datetime.now().strftime('%Y%m%d-%H%M%S')))

    def detach(el):
        p = el.getparent()
        if p is not None:
            p.remove(el)

    for el in new:                       # gỡ phần tử tái dùng khỏi cây
        detach(el)
    for tag, el in items[i31 + 1:i32]:   # xoá phần còn lại của §3.1 cũ
        detach(el)
    for tag, el in items[i33:i40]:       # xoá §3.3–§3.6 cũ (kể cả tiêu đề)
        detach(el)

    for sdt in list(body.iter(qn('w:sdt'))):   # dọn vỏ sdt rỗng
        c = sdt.find(qn('w:sdtContent'))
        if c is None or len(c) == 0:
            p = sdt.getparent()
            if p is not None:
                p.remove(sdt)

    a31 = items[i32][1]
    if a31.getparent() is not body:
        die('moc chen §3.1 khong nam truc tiep trong body')
    for el in new:
        a31.addprevious(el)

    a33 = items[i40][1]
    if a33.getparent() is not body:
        die('moc chen §3.3 khong nam truc tiep trong body')
    for el in tail:
        a33.addprevious(el)

    # 5. bảng chú giải đầu §3 + style Heading 4 -------------------------------
    legend_old = [el for tag, el in items[:i31]
                  if tag == 'tbl' and first_cell(el).startswith('Frefix')]
    if len(legend_old) != 1:
        die('tim thay %d bang chu giai "Frefix"' % len(legend_old))
    legend_new = B.table(G.LEGEND_HEADERS, G.LEGEND_ROWS, G.LEGEND_WIDTHS)
    legend_old[0].addprevious(legend_new)
    detach(legend_old[0])

    if not restyle_h4(doc):
        die('khong tim thay style Heading4')

    doc.save(SRC)
    print('DA GHI: %s' % SRC)


if __name__ == '__main__':
    main()
