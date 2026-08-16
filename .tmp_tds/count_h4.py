# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
doc = Document(r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx")
n = {}
for p in doc.element.body.iter(qn('w:p')):
    ppr = p.find(qn('w:pPr'))
    st = ppr.find(qn('w:pStyle')) if ppr is not None else None
    sid = st.get(qn('w:val')) if st is not None else 'Normal'
    n[sid] = n.get(sid, 0) + 1
    if sid in ('Heading4','Heading5','Heading6'):
        print(sid, ''.join(t.text or '' for t in p.iter(qn('w:t')))[:90])
print(sorted(n.items(), key=lambda kv: -kv[1])[:12])
