# -*- coding: utf-8 -*-
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
def ptext(p): return ''.join(t.text or '' for t in p.iter(qn('w:t')))
def walk(el):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'): yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c): yield x
doc = Document(SRC)
pat = re.compile(r'(extend|core table|storage table|custom table|native|grey box|\b\d+\s+(core|custom|table))', re.I)
for tag, el in walk(doc.element.body):
    if tag != 'p': continue
    t = ptext(el).strip()
    if len(t) > 25 and pat.search(t):
        print('- ' + t[:400])
        print()
