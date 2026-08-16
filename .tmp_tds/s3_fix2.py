# -*- coding: utf-8 -*-
"""Sửa kiểu dữ liệu sai trong các bảng cột của §3.

1. BIGSERIAL → SERIAL. Odoo 17 tạo bảng bằng `id SERIAL NOT NULL`
   (odoo/tools/sql.py:232) ⇒ khoá chính là int4, không phải int8. Cả §3.1 đang
   ghi BIGSERIAL — sai nhất quán từ bản nháp đầu.
2. Gõ nhầm kiểu: INTE / INTERGER → INTEGER.
3. Ô đầu 'Id' → 'id' cho khớp tên cột thật.
4. Bỏ dòng material_line_ids khỏi bảng CỘT của dl_bom_operation_line: Many2many
   KHÔNG sinh cột, nó sinh bảng nối — để trong bảng cột thì ERD vật lý vẽ ra một
   dòng "material_line_ids : —" không có thật. Đưa xuống câu chú thích.

Chỉ đụng vào các bảng có hàng tiêu đề bắt đầu bằng 'Column', và chỉ trong §3.

Chạy:  venv/Scripts/python.exe .tmp_tds/s3_fix2.py [--dry]
"""
import io
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document                                       # noqa: E402
from docx.oxml.ns import qn                                     # noqa: E402

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
DRY = '--dry' in sys.argv

PG_FIX = {'BIGSERIAL': 'SERIAL', 'INTE': 'INTEGER', 'INTERGER': 'INTEGER'}
M2M_NOTE = (' Cột material_line_ids của ORM là Many2many nên KHÔNG sinh cột trên bảng này: '
            'quan hệ nằm ở bảng nối dl_bom_line_dl_bom_operation_line_rel — xem cuối §3.1.')


def cellt(tc):
    return ' '.join(''.join(t.text or '' for t in tc.iter(qn('w:t'))).split())


def set_cellt(tc, value):
    """Ghi đè nội dung một ô đơn giản (giữ run đầu, xoá các run còn lại)."""
    ts = list(tc.iter(qn('w:t')))
    if not ts:
        return False
    ts[0].text = value
    ts[0].set(qn('xml:space'), 'preserve')
    for t in ts[1:]:
        t.text = ''
    return True


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def walk(el):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p', 'tbl'):
            yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c):
                    yield x


def main():
    doc = Document(SRC)
    items = list(walk(doc.element.body))
    s = e = None
    for i, (tag, el) in enumerate(items):
        if tag != 'p':
            continue
        t = ptext(el).strip()
        if t == '3. Data Model':
            s = i
        elif t.startswith('4. Security Design') and s is not None and e is None:
            e = i
    if s is None or e is None:
        print('DUNG: khong khoanh duoc §3')
        sys.exit(1)

    n_pg, n_id, n_m2m, noted = 0, 0, 0, False
    cur_head = ''
    for tag, el in items[s:e]:
        if tag == 'p':
            t = ptext(el).strip()
            if t.startswith(('Table:', 'View:', 'Mixin:')):
                cur_head = t
            elif n_m2m and not noted and 'estimated_unit_cost' in t:
                ts = list(el.iter(qn('w:t')))
                if ts:
                    noted = True
                    if not DRY:
                        ts[-1].text = (ts[-1].text or '') + M2M_NOTE
                        ts[-1].set(qn('xml:space'), 'preserve')
            continue
        rows = el.findall(qn('w:tr'))
        if not rows:
            continue
        hdr = [cellt(tc) for tc in rows[0].findall(qn('w:tc'))]
        if hdr[:2] != ['Column', 'Type']:
            continue
        for tr in rows[1:]:
            tcs = tr.findall(qn('w:tc'))
            if not tcs:
                continue
            name = cellt(tcs[0])
            if name == 'material_line_ids' and 'dl_bom_operation_line' in cur_head:
                n_m2m += 1
                if not DRY:
                    tr.getparent().remove(tr)
                continue
            if name == 'Id':
                n_id += 1
                if not DRY:
                    set_cellt(tcs[0], 'id')
            if len(tcs) > 2:
                pg = cellt(tcs[2])
                if pg in PG_FIX:
                    n_pg += 1
                    if not DRY:
                        set_cellt(tcs[2], PG_FIX[pg])

    print('o kieu du lieu sua : %d' % n_pg)
    print("o 'Id' -> 'id'      : %d" % n_id)
    print('dong m2m go bo      : %d (gan chu thich: %s)' % (n_m2m, 'co' if noted else 'KHONG'))
    if DRY:
        print('--dry: khong ghi file')
        return
    shutil.copy2(SRC, SRC.replace('.docx', '.backup-%s.docx'
                                  % datetime.now().strftime('%Y%m%d-%H%M%S')))
    doc.save(SRC)
    print('DA GHI: %s' % SRC)


if __name__ == '__main__':
    main()
