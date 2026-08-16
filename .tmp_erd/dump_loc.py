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
        if t.startswith('Table: stock_location'): on=True
        elif t.startswith('Table: stock_picking_type'): break
        if on and t: print('P: ' + t[:200])
    elif tag == 'tbl' and on:
        for tr in el.findall(qn('w:tr')):
            print('   | ' + ' | '.join(cellt(tc)[:70] for tc in tr.findall(qn('w:tc'))))
