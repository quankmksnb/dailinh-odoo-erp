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
s=e=None
for i,(tag,el,p) in enumerate(items):
    if tag=='p':
        P=Paragraph(el,doc); t=P.text.strip(); st=P.style.name if P.style is not None else ''
        if st=='Heading 2' and t.startswith('3.3'): s=i
        if st=='Heading 1' and t.startswith('4.') and s is not None and e is None: e=i
for i in range(s,e):
    tag,el,p = items[i]
    if tag=='p':
        P=Paragraph(el,doc); t=P.text.strip()
        st=P.style.name if P.style is not None else ''
        if t: print('P <%s> %s' % (st,t))
    else:
        T=Table(el,doc)
        print('TABLE %dx%d' % (len(T.rows),len(T.columns)))
        for r in T.rows:
            cells=[' '.join(c.text.split()) for c in r.cells]
            ded=[]
            for c in cells:
                if not ded or ded[-1]!=c: ded.append(c)
            print('   | ' + ' | '.join(x[:60] for x in ded))
