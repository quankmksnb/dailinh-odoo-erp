# -*- coding: utf-8 -*-
"""Hoàn thiện §3 Data Model của Report 4.0_TDS.docx: bổ sung phần Kho + lấp §3.2.

Chạy:  venv/Scripts/python.exe .tmp_tds/apply_kho.py [--dry]
"""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.oxml.ns import qn

import builder as B
import sec3_kho as K
import sec3_rel as R

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
DRY = '--dry' in sys.argv
W = B.W


# ───────────────────────────── tiện ích đọc/ghi ──────────────────────────────

def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def pstyle(p):
    pr = p.find(qn('w:pPr'))
    if pr is None:
        return ''
    st = pr.find(qn('w:pStyle'))
    return st.get(qn('w:val')) if st is not None else ''


def sec3_blocks(body):
    """Danh sách phần tử thuộc mục 3 (từ '3. Data Model' đến trước '4. Security Design')."""
    out, on = [], False
    for el in body:
        tag = el.tag.split('}')[1]
        if tag == 'p':
            t = ptext(el).strip()
            if t == '3. Data Model':
                on = True
            elif t == '4. Security Design':
                break
        if on and tag in ('p', 'tbl'):
            out.append(el)
    if not out:
        raise SystemExit("!! Khong tim thay muc '3. Data Model'")
    return out


def find_p(blocks, text):
    for el in blocks:
        if el.tag.endswith('}p') and ptext(el).strip() == text:
            return el
    raise SystemExit('!! Khong tim thay doan: %r' % text)


def table_by_header(blocks, want):
    """Tìm <w:tbl> mà hàng đầu khớp ĐÚNG các ô trong `want` (theo thứ tự).

    Khớp đủ nhiều ô để không nhận nhầm bảng khác — nhận nhầm sẽ chèn hàng vào
    đúng chỗ sai mà không lỗi nào nổ.
    """
    hits = []
    for el in blocks:
        if not el.tag.endswith('}tbl'):
            continue
        tr = el.find(qn('w:tr'))
        if tr is None:
            continue
        cells = [' '.join(''.join(x.text or '' for x in tc.iter(qn('w:t'))).split())
                 for tc in tr.findall(qn('w:tc'))]
        if cells[:len(want)] == list(want):
            hits.append(el)
    if not hits:
        raise SystemExit('!! Khong tim thay bang co header = %r' % (want,))
    if len(hits) > 1:
        raise SystemExit('!! Header %r khop %d bang - can lam ro' % (want, len(hits)))
    return hits[0]


def grid_widths(tbl):
    grid = tbl.find(qn('w:tblGrid'))
    return [int(round(float(gc.get(qn('w:w'))))) for gc in grid.findall(qn('w:gridCol'))]


def append_rows(tbl, rows, group_label=None):
    """Thêm hàng vào cuối bảng có sẵn, dùng đúng độ rộng cột của bảng đó."""
    from docx.oxml import parse_xml
    widths = grid_widths(tbl)
    n = len(widths)
    if group_label:
        cell = B._tc(group_label, sum(widths), group=True, span=n)
        tbl.append(parse_xml('<w:tr %s><w:trPr/>%s</w:tr>' % (B.NS, cell)))
    for row in rows:
        row = list(row) + [''] * (n - len(row))
        cells = ''.join(B._tc(c, w) for c, w in zip(row[:n], widths))
        tbl.append(parse_xml('<w:tr %s><w:trPr/>%s</w:tr>' % (B.NS, cells)))


# ─────────────────────────────── các bước sửa ────────────────────────────────

def step_fix_numbering(blocks, log):
    """Bỏ trùng số mục: '3.1 Notation Conventions' -> đoạn thường không đánh số;
    '3.2 Entity Definitions' -> '3.1 Entity Definitions'."""
    old = find_p(blocks, '3.1 Notation Conventions')
    notation = B.para('Notation Conventions', bold=True, sz=26)
    old.addnext(notation)
    old.getparent().remove(old)
    log.append("3.1 Notation Conventions -> doan thuong in dam (het trung so muc 3.2)")

    defs = find_p(blocks, '3.2 Entity Definitions')
    for t in defs.iter(qn('w:t')):
        t.text = '3.1 Entity Definitions'
    log.append('3.2 Entity Definitions -> 3.1 Entity Definitions (khop template)')
    return notation, defs


def step_notation_table(notation, log):
    tbl = B.table(R.CONV_HEADERS, R.CONV_ROWS, R.CONV_WIDTHS)
    notation.addnext(tbl)
    notation.addnext(B.para(''))
    log.append('them bang chu giai ky hieu (%d dong)' % len(R.CONV_ROWS))


def step_strip_empty_headings(blocks, log):
    """Xoá đoạn RỖNG mang style Heading — chúng lọt vào Mục lục thành dòng trắng."""
    killed = 0
    for el in blocks:
        if not el.tag.endswith('}p'):
            continue
        if ptext(el).strip():
            continue
        if not pstyle(el).startswith('Heading'):
            continue
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
            killed += 1
    log.append('xoa %d heading rong (khong con dong trang trong Muc luc)' % killed)


def step_insert_kho(anchor, log):
    """Chèn nhóm thực thể Kho vào cuối §3.1, ngay trước anchor."""
    out = [
        B.para(K.GROUP_TITLE, style='Heading3'),
        B.para(K.GROUP_LEAD),
        B.note_box('Stored versus computed — what actually becomes a column', K.NOTE_NONSTORED),
        B.para(''),
    ]
    for ent in K.ENTITIES:
        out.append(B.para(ent['head'], style='Heading3'))
        out.append(B.para(ent['desc']))
        if ent.get('meta'):
            out.append(B.para(ent['meta'], italic=True, sz=20, color='555555'))
        if ent.get('note'):
            out.append(B.note_box(ent['note'][0], ent['note'][1]))
        if ent.get('cols'):
            out.append(B.table(K.CH, ent['cols'], K.CW))
        if ent.get('extra'):
            out.append(B.para(ent['extra'], sz=20, color='555555'))
        out.append(B.para(''))

    out.append(B.note_box(
        'Transient (wizard) tables are intentionally excluded from §3.1 and §3.2',
        'The 15 wizard models listed below do create real PostgreSQL tables, but their rows are '
        'deleted automatically by the ORM vacuum after transient_max_hours (1 hour by default). '
        'They hold no durable business data and no long-term integrity constraint, so modelling '
        'them would add roughly 40 edges describing temporary UI state: '
        'dl_bom_create_btp_wizard, dl_bom_from_template_wizard, dl_pricing_approval_reject_wizard, '
        'dl_pricing_ui, dl_quotation_export_wizard, dl_quotation_reject_wizard, '
        'dl_quotation_revision_wizard, dl_rfq_history_wizard, dl_rfq_line_infeasible_wizard, '
        'dl_rfq_line_supplement_wizard, dl_rfq_resolve_param, dl_rfq_resolve_wizard, '
        'dl_rfq_return_wizard, dl_rfq_return_wizard_line, dl_sale_order_reset_draft_wizard.'))
    out.append(B.para(''))

    for el in out:
        anchor.addprevious(el)
    log.append('chen %d block cho nhom Kho (%d bang thuc the)'
               % (len(out), len(K.ENTITIES)))


def step_fill_relationships(rel_head, log):
    rows, total = R.build_rel_rows()
    out = [
        B.para(R.REL_LEAD),
        B.para(''),
        B.para('Diagram set', bold=True, sz=26),
        B.para(R.DIAG_LEAD),
        B.table(R.DIAG_HEADERS, R.DIAG_ROWS, R.DIAG_WIDTHS),
        B.para(''),
        B.note_box(R.DIAG_NOTE_LABEL, R.DIAG_NOTE),
        B.para(''),
        B.para('Foreign keys', bold=True, sz=26),
        B.para(R.REL_TBL_LEAD),
        B.table(R.REL_HEADERS, rows, R.REL_WIDTHS),
        B.para(''),
        B.note_box(R.REL_NOTE_LABEL, R.REL_NOTE),
        B.para(''),
    ]
    for el in reversed(out):
        rel_head.addnext(el)
    log.append('lap §3.2 Entity Relationships: 7 so do + %d khoa ngoai' % total)


def main():
    if not os.path.exists(SRC):
        raise SystemExit('!! Khong thay file: %s' % SRC)
    lock = os.path.join(os.path.dirname(SRC), '~$' + os.path.basename(SRC))
    if os.path.exists(lock):
        raise SystemExit('!! File dang mo trong Word. Dong Word roi chay lai.')

    doc = Document(SRC)
    body = doc.element.body
    blocks = sec3_blocks(body)
    log = []

    notation, _ = step_fix_numbering(blocks, log)
    step_notation_table(notation, log)

    rel_head = find_p(blocks, '3.2 Entity Relationships')
    step_insert_kho(rel_head, log)
    step_fill_relationships(rel_head, log)

    append_rows(table_by_header(blocks, ['Table / Mixin', 'Column', 'Allowed Values']),
                R.ENUM_KHO_ROWS, group_label='Inventory (dl_inventory)')
    log.append('§3.3 Enum: them %d dong' % len(R.ENUM_KHO_ROWS))

    idx_tbl = table_by_header(blocks, ['Table', 'Index Column(s)', 'Type', 'Reason'])
    append_rows(idx_tbl, R.IDX_KHO_ROWS,
                group_label='BTREE — inventory module (index=True)')
    log.append('§3.4 Indexing: them %d dong' % len(R.IDX_KHO_ROWS))
    idx_tbl.addnext(B.note_box(R.IDX_KHO_NOTE_LABEL, R.IDX_KHO_NOTE))
    idx_tbl.addnext(B.para(''))

    acc_tbl = table_by_header(blocks, ['—', 'Permission group', 'Test objective'])
    append_rows(acc_tbl, [R.SEED_ACCOUNT_ROW])
    log.append('§3.6 Seed accounts: them tai khoan Thu kho')

    dom_tbl = table_by_header(blocks, ['Entity', 'Count', 'States needed'])
    append_rows(dom_tbl, R.SEED_KHO_ROWS, group_label='Inventory (dl_inventory)')
    log.append('§3.6 Seed domain: them %d dong' % len(R.SEED_KHO_ROWS))
    dom_tbl.addnext(B.note_box(R.SEED_NOTE_LABEL, R.SEED_NOTE))
    dom_tbl.addnext(B.para(''))

    step_strip_empty_headings(blocks, log)

    print('\n'.join('  - ' + x for x in log))
    if DRY:
        print('\n[dry-run] khong ghi file')
        return
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = SRC.replace('.docx', '.backup-%s.docx' % stamp)
    shutil.copy2(SRC, backup)
    print('\n[backup] %s' % backup)
    doc.save(SRC)
    print('[saved]  %s' % SRC)


if __name__ == '__main__':
    main()
