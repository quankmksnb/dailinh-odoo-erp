# -*- coding: utf-8 -*-
"""Đối chiếu §3 trước/sau khi dựng lại: có mất bảng nào không, có đủ ràng buộc không.

Chạy: venv/Scripts/python.exe .tmp_tds/verify_s3.py <ban_cu.docx>
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document                                       # noqa: E402
from docx.oxml.ns import qn                                     # noqa: E402

NEW = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
OLD = sys.argv[1] if len(sys.argv) > 1 else None

HEAD_RE = re.compile(r'^(Table|View|Mixin):\s*([A-Za-z0-9_. +]+?)\s*'
                     r'(?:\[([^\]]*)\])?\s*(?:\(.*\))?$')
# "Table: dl_sale_order [extended by dl_inventory]" là tiêu đề phụ nằm TRONG khối
# dl_sale_order (2 cột do dl_inventory thêm), không phải một thực thể riêng.
SUBHEAD = 'extended by'


def is_head(t):
    m = HEAD_RE.match(t)
    return bool(m) and SUBHEAD not in (m.group(3) or '')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def cellt(tc):
    return ' '.join(''.join(t.text or '' for t in tc.iter(qn('w:t'))).split())


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


def sig(tbl):
    """Chữ ký một bảng: ô đầu + số dòng + tổng ký tự — đủ để nhận ra bảng cũ."""
    rows = tbl.findall(qn('w:tr'))
    head = cellt(rows[0].find(qn('w:tc'))) if rows else ''
    n = sum(len(cellt(tc)) for tr in rows for tc in tr.findall(qn('w:tc')))
    return (head[:40], len(rows), n)


def sec3(path):
    doc = Document(path)
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
    return items[s:e]


def analyse(path, label):
    items = sec3(path)
    tbls = [el for tag, el in items if tag == 'tbl']
    heads = [ptext(el).strip() for tag, el in items
             if tag == 'p' and is_head(ptext(el).strip())]
    chars = sum(len(ptext(el)) for tag, el in items if tag == 'p')
    chars += sum(s[2] for s in map(sig, tbls))
    print('%-6s  bang=%-4d tieu-de-thuc-the=%-4d ky-tu=%d' % (label, len(tbls), len(heads), chars))
    return items, tbls, heads


def main():
    items, tbls, heads = analyse(NEW, 'MOI')

    # mỗi tiêu đề thực thể phải có đúng 1 bảng ràng buộc trước tiêu đề kế tiếp
    cur, dcc, bad = None, {}, []
    for tag, el in items:
        if tag == 'p':
            t = ptext(el).strip()
            if is_head(t):
                cur = t
                dcc.setdefault(cur, 0)
        elif tag == 'tbl' and cur:
            if cellt(el.find(qn('w:tr')).find(qn('w:tc'))).startswith('Data Constraints'):
                dcc[cur] += 1
    for h, n in dcc.items():
        if n != 1:
            bad.append((h, n))
    print('tieu de thuc the: %d · thieu/thua bang rang buoc: %d' % (len(dcc), len(bad)))
    for h, n in bad:
        print('   !! %-60s %d bang' % (h[:60], n))

    if not OLD:
        return
    print()
    oitems, otbls, oheads = analyse(OLD, 'CU')
    new_sigs = {}
    for t in tbls:
        new_sigs[sig(t)] = new_sigs.get(sig(t), 0) + 1
    lost = []
    for t in otbls:
        s = sig(t)
        if new_sigs.get(s):
            new_sigs[s] -= 1
        else:
            lost.append(s)
    print('bang cu KHONG con nguyen ven: %d' % len(lost))
    for s in lost:
        print('   - %-42s %2d dong %6d ky tu' % s)
    print('bang moi xuat hien: %d' % sum(new_sigs.values()))


if __name__ == '__main__':
    main()
