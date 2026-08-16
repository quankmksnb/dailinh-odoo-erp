# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
doc = Document(r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx")
def dump(el, ind=2):
    for ch in el:
        tag = ch.tag.split('}')[1]
        attrs = {k.split('}')[1]: v for k, v in ch.attrib.items()}
        print(' '*ind + tag + ' ' + str(attrs))
        if tag in ('rPr','pPr'): dump(ch, ind+3)
for st in doc.styles.element.findall(qn('w:style')):
    sid = st.get(qn('w:styleId'))
    if sid in ('Heading2','Heading3','Heading4','Normal'):
        print('==', sid)
        dump(st)
