# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

SRC = r"D:\FPTU\do_van_an\dailinh-odoo-erp\docs\Report 4.0_TDS_Template.docx"
doc = Document(SRC)

def walk(el, path=''):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'):
            yield tag, ch, path
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c, path+'sdt/'):
                    yield x

i = 0
for tag, el, path in walk(doc.element.body):
    if tag == 'p':
        p = Paragraph(el, doc)
        txt = p.text.strip()
        st = p.style.name if p.style is not None else ''
        if txt:
            print(f"[{i}]{path} P <{st}> {txt[:150]}")
    else:
        t = Table(el, doc)
        try:
            hdr = " | ".join(c.text.strip()[:20] for c in t.rows[0].cells)
        except Exception:
            hdr = "?"
        print(f"[{i}]{path} TABLE {len(t.rows)}x{len(t.columns)} :: {hdr[:160]}")
    i += 1
