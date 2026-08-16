# -*- coding: utf-8 -*-
"""Đồng bộ §3 của Report 4.0_TDS.docx với source sau đợt pull 2026-08-12.

Bốn việc:
  1. stock_location nhận cột dlm_no_inventory  → tiêu đề [Native] thành [Inherit].
  2. Câu đếm ở phần Kho: 10 cột / 3 bảng → 11 cột / 4 bảng.
  3. Câu đếm ở §3.2: 8 bảng lõi mở rộng + 10 bảng lõi tham chiếu → 9 + 9.
  4. Bốn tên cột gõ sai tiền tố dl_ (đúng: dlm_), kèm typo "recorvery".

MỌI phép sửa đều bắt buộc khớp ĐÚNG một chỗ. Không khớp, hoặc khớp nhiều hơn
một, là dừng ngay — sửa nhầm chỗ trong tài liệu 50 trang thì không ai thấy.

Chạy:  venv/Scripts/python.exe .tmp_tds/apply_erd_sync.py [--dry]
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
from docx.oxml import parse_xml                                 # noqa: E402
from docx.oxml.ns import qn                                     # noqa: E402

import builder as B                                             # noqa: E402

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
DRY = '--dry' in sys.argv

LOC_HEAD_OLD = 'Table: stock_location [Native]'
LOC_HEAD_NEW = 'Table: stock_location [Inherit]'
COL_HEADER = ['Column', 'Type', 'PostgreSQL', 'Constraints', 'Notes']

# Dòng cột mới. "DEFAULT FALSE" theo đúng lối bảng này đang ghi cho active.
LOC_ROW = [
    'dlm_no_inventory',
    'Boolean',
    'BOOL',
    'DEFAULT FALSE',
    'Transit-zone flag, set by dl_inventory on DL/NHAN/QC and DL/NHAN/TRA. '
    'Manual inventory counting is refused on these locations server-side, not '
    'merely hidden from the screen: their stock is already referenced by an '
    'open inspection or vendor-return document, so a hand count would erase '
    'goods that a draft document still points at.',
]

PHRASES = [
    ('10 physical columns spread over 3 native tables',
     '11 physical columns spread over 4 native tables'),
    ('8 Odoo core tables extended with dlm_ columns and 10 further core tables '
     'referenced by foreign key',
     '9 Odoo core tables extended with dlm_ columns and 9 further core tables '
     'referenced by foreign key'),
]

# Tên cột §3.1 gõ sai — source dùng tiền tố dlm_ (và "recovery", không "recorvery")
RENAMES = [
    ('dl_lifecycle_state', 'dlm_lifecycle_state'),
    ('dl_waste_rate', 'dlm_waste_rate'),
    ('dl_has_recorvery', 'dlm_has_recovery'),
    ('dl_customer_group', 'dlm_customer_group'),
]


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def cellt(tc):
    return ' '.join(''.join(x.text or '' for x in tc.iter(qn('w:t'))).split())


def walk(el):
    """Block theo đúng thứ tự tài liệu, CHUI VÀO w:sdt.

    Phần §3.1 cũ (res_users … dl_rbac_operation) nằm trong content control; đi
    `for el in body` trơn sẽ không thấy bốn tên cột cần sửa.
    """
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p', 'tbl'):
            yield tag, ch
        elif tag == 'sdt':
            content = ch.find(qn('w:sdtContent'))
            if content is not None:
                for x in walk(content):
                    yield x


def set_text(p, new):
    """Ghi lại nội dung đoạn, giữ nguyên run/định dạng.

    Chỉ nhận đoạn có ĐÚNG một <w:t>: mọi đích ở đây đều do builder.py sinh ra
    nên chỉ có một run. Đoạn nhiều run nghĩa là Word đã tách lại (do sửa tay
    hoặc bật track changes) — lúc đó ghi đè w:t đầu là mất chữ, phải dừng.
    """
    ts = list(p.iter(qn('w:t')))
    if len(ts) != 1:
        raise SystemExit('!! Doan co %d <w:t>, khong ghi de an toan duoc: %r'
                         % (len(ts), ptext(p)[:80]))
    ts[0].text = new


def grid_widths(tbl):
    grid = tbl.find(qn('w:tblGrid'))
    return [int(round(float(gc.get(qn('w:w'))))) for gc in grid.findall(qn('w:gridCol'))]


def append_row(tbl, row):
    widths = grid_widths(tbl)
    row = list(row) + [''] * (len(widths) - len(row))
    cells = ''.join(B._tc(c, w) for c, w in zip(row[:len(widths)], widths))
    tbl.append(parse_xml('<w:tr %s><w:trPr/>%s</w:tr>' % (B.NS, cells)))


def main():
    if not os.path.exists(SRC):
        raise SystemExit('!! Khong thay file: %s' % SRC)
    lock = os.path.join(os.path.dirname(SRC), '~$' + os.path.basename(SRC))
    if os.path.exists(lock):
        raise SystemExit('!! File dang mo trong Word. Dong Word roi chay lai.')

    doc = Document(SRC)
    blocks = list(walk(doc.element.body))
    log = []

    # ── 1. Bảng cột stock_location: thêm dòng dlm_no_inventory ────────────────
    heads = [i for i, (tag, el) in enumerate(blocks)
             if tag == 'p' and ptext(el).strip() == LOC_HEAD_OLD]
    if len(heads) != 1:
        raise SystemExit('!! %r khop %d cho (can dung 1)' % (LOC_HEAD_OLD, len(heads)))
    start = heads[0]

    target = None
    for tag, el in blocks[start + 1:]:
        if tag == 'p' and ptext(el).strip().startswith('Table: '):
            break                      # sang thực thể kế tiếp mà chưa thấy bảng
        if tag != 'tbl':
            continue
        tr = el.find(qn('w:tr'))
        if tr is None:
            continue
        cells = [cellt(tc) for tc in tr.findall(qn('w:tc'))]
        if cells[:len(COL_HEADER)] == COL_HEADER:
            target = el
            break
    if target is None:
        raise SystemExit('!! Khong thay bang cot cua stock_location')

    có = [cellt(tr.findall(qn('w:tc'))[0]) for tr in target.findall(qn('w:tr'))]
    if LOC_ROW[0] in có:
        log.append('bo qua: %s da co trong bang' % LOC_ROW[0])
    else:
        append_row(target, LOC_ROW)
        log.append('stock_location: them cot %s (bang dang co %d dong)'
                   % (LOC_ROW[0], len(có) - 1))

    # ── 2. Tiêu đề [Native] → [Inherit] ───────────────────────────────────────
    set_text(blocks[start][1], LOC_HEAD_NEW)
    log.append('tieu de: %s -> [Inherit]' % LOC_HEAD_OLD)

    # ── 3. Hai câu đếm ────────────────────────────────────────────────────────
    paras = [el for tag, el in blocks if tag == 'p']
    for tag, el in blocks:
        if tag == 'tbl':
            paras.extend(el.iter(qn('w:p')))
    for old, new in PHRASES:
        hits = [p for p in paras if old in ptext(p)]
        if len(hits) != 1:
            raise SystemExit('!! Cau dem %r khop %d cho' % (old[:45], len(hits)))
        set_text(hits[0], ptext(hits[0]).replace(old, new))
        log.append('cap nhat so dem: %s...' % new[:58])

    # ── 4. Bốn tên cột sai ────────────────────────────────────────────────────
    for old, new in RENAMES:
        rx = re.compile(r'(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])' % re.escape(old))
        hits = [p for p in paras if rx.search(ptext(p))]
        if len(hits) != 1:
            raise SystemExit('!! Ten cot %r khop %d cho (can dung 1)' % (old, len(hits)))
        set_text(hits[0], rx.sub(new, ptext(hits[0])))
        log.append('doi ten cot: %s -> %s' % (old, new))

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
