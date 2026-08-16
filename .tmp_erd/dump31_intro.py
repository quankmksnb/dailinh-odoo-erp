# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
def ptext(p): return ''.join(t.text or '' for t in p.iter(qn('w:t')))
def cellt(tc): return ' '.join(''.join(x.text or '' for x in tc.iter(qn('w:t'))).split())
def walk(el):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'): yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c): yield x
doc = Document(SRC)
on=False
for tag, el in walk(doc.element.body):
    if tag == 'p':
        t = ptext(el).strip()
        if t == '3. Data Model': on=True; print('### ', t); continue
        if not on or not t: continue
        print('P: ' + t[:300])
        if t.startswith('Table: res_partner'): break
    elif tag == 'tbl' and on:
        rows = el.findall(qn('w:tr'))
        for tr in rows[:14]:
            print('   | ' + ' | '.join(cellt(tc)[:60] for tc in tr.findall(qn('w:tc'))))
