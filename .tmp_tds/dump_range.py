# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
doc = Document(SRC)
def walk(el):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'): yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c): yield x
items = list(walk(doc.element.body))
rngs = []
for a in sys.argv[1:]:
    x,y = a.split('-'); rngs.append((int(x),int(y)))
for lo,hi in rngs:
    print('#'*70)
    for i in range(lo,hi+1):
        tag, el = items[i]
        if tag=='p':
            P=Paragraph(el,doc); st=P.style.name if P.style is not None else ''
            print('[%d] P <%s> %s' % (i, st, P.text))
        else:
            T=Table(el,doc)
            print('[%d] TABLE %dx%d' % (i,len(T.rows),len(T.columns)))
            for r in T.rows:
                cells=[' '.join(c.text.split()) for c in r.cells]
                ded=[]
                for c in cells:
                    if not ded or ded[-1]!=c: ded.append(c)
                print('     | ' + ' | '.join(x[:70] for x in ded))
