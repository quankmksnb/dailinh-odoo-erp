# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
doc = Document(SRC)
print("== styles (id | name | type) ==")
for st in doc.styles.element.findall(qn('w:style')):
    sid = st.get(qn('w:styleId')); typ = st.get(qn('w:type'))
    nm = st.find(qn('w:name'))
    print("  %-22s %-28s %s" % (sid, nm.get(qn('w:val')) if nm is not None else '?', typ))
print()
print("== TOC field ==")
for fld in doc.element.body.iter(qn('w:instrText')):
    t = (fld.text or '').strip()
    if 'TOC' in t: print("   ", t)
