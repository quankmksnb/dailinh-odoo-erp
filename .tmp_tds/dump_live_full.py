# -*- coding: utf-8 -*-
"""Dump ĐẦY ĐỦ một khoảng block của TDS thật (kèm nội dung bảng)."""
import io, sys
from docx import Document
from docx.oxml.ns import qn

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
LO = int(sys.argv[1]) if len(sys.argv) > 1 else 1
HI = int(sys.argv[2]) if len(sys.argv) > 2 else 999

doc = Document(SRC)
body = doc.element.body


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def pstyle(p):
    pr = p.find(qn('w:pPr'))
    if pr is None:
        return ''
    st = pr.find(qn('w:pStyle'))
    return st.get(qn('w:val')) if st is not None else ''


on = False
n = 0
for el in body:
    tag = el.tag.split('}')[1]
    if tag == 'p':
        t = ptext(el).strip()
        if t == '3. Data Model':
            on = True
        elif t == '4. Security Design':
            break
        if on:
            n += 1
            if LO <= n <= HI:
                print('%-4d P  [%-10s] %s' % (n, pstyle(el), t))
    elif tag == 'tbl' and on:
        n += 1
        if LO <= n <= HI:
            rows = el.findall(qn('w:tr'))
            print('%-4d TBL (%d rows)' % (n, len(rows)))
            for tr in rows:
                cells = [' '.join(''.join(x.text or '' for x in tc.iter(qn('w:t'))).split())
                         for tc in tr.findall(qn('w:tc'))]
                print('       | ' + ' | '.join(cells))
