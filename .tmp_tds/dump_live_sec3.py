# -*- coding: utf-8 -*-
"""Dump mục 3 của TDS đang dùng thật (DLM-ERP Report/)."""
import io, sys
from docx import Document
from docx.oxml.ns import qn

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
START = sys.argv[2] if len(sys.argv) > 2 else "3. Data Model"
END = sys.argv[3] if len(sys.argv) > 3 else "4. Security Design"

doc = Document(SRC)
body = doc.element.body


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def pstyle(p):
    s = p.find(qn('w:pPr'))
    if s is None:
        return ''
    st = s.find(qn('w:pStyle'))
    return st.get(qn('w:val')) if st is not None else ''


on = False
n = 0
for el in body:
    tag = el.tag.split('}')[1]
    if tag == 'p':
        t = ptext(el).strip()
        if t == START:
            on = True
        elif t == END:
            break
        if on:
            n += 1
            st = pstyle(el)
            if t or st.startswith('Heading'):
                print('%-4d %-12s %s' % (n, st, t[:220]))
    elif tag == 'tbl' and on:
        n += 1
        rows = el.findall(qn('w:tr'))
        first = rows[0] if rows else None
        hdr = ' | '.join(''.join(x.text or '' for x in tc.iter(qn('w:t')))
                         for tc in first.findall(qn('w:tc'))) if first is not None else ''
        print('%-4d %-12s [TABLE %d rows] %s' % (n, '', len(rows), hdr[:190]))
print('--- tong block trong muc 3: %d' % n)
