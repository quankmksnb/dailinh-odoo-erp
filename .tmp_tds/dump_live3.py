# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
doc = Document(SRC)
def walk(el, path=''):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'): yield tag, ch, path
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c, path+'sdt/'): yield x

items = list(walk(doc.element.body))
start = None; end = None
for i,(tag,el,path) in enumerate(items):
    if tag=='p':
        p = Paragraph(el, doc); t = p.text.strip()
        st = p.style.name if p.style is not None else ''
        if st=='Heading 1' and t.startswith('3.'): start = i
        if st=='Heading 1' and t.startswith('4.') and start is not None and end is None: end = i
print("range", start, end, "total", len(items))
for i,(tag,el,path) in enumerate(items):
    if start is None or i < start or (end and i > end): continue
    if tag=='p':
        p = Paragraph(el, doc); t = p.text.strip()
        st = p.style.name if p.style is not None else ''
        if t: print(f"[{i}] P <{st}> {t[:130]}")
    else:
        t = Table(el, doc)
        try: hdr = " | ".join(c.text.strip()[:18] for c in t.rows[0].cells)
        except Exception: hdr='?'
        print(f"[{i}] TABLE {len(t.rows)}x{len(t.columns)} :: {hdr[:150]}")
