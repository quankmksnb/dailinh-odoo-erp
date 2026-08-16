# -*- coding: utf-8 -*-
import io, sys, re
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
# locate 3.1 .. 3.2
s=e=None
for i,(tag,el,p) in enumerate(items):
    if tag=='p':
        P=Paragraph(el,doc); t=P.text.strip(); st=P.style.name if P.style is not None else ''
        if st=='Heading 2' and t.startswith('3.1'): s=i
        if st=='Heading 2' and t.startswith('3.2') and s is not None and e is None: e=i

blocks=[]   # (heading, [table headers])
cur=None
for i in range(s,e):
    tag,el,p = items[i]
    if tag=='p':
        P=Paragraph(el,doc); t=P.text.strip(); st=P.style.name if P.style is not None else ''
        if st=='Heading 3':
            cur={'h':t,'tbls':[]}; blocks.append(cur)
    else:
        if cur is not None:
            T=Table(el,doc)
            try: hdr=T.rows[0].cells[0].text.strip()[:40]
            except Exception: hdr='?'
            cur['tbls'].append((hdr,len(T.rows),len(T.columns)))

print("=== 3.1 entity blocks: %d ===" % len(blocks))
missing=[]
for b in blocks:
    has = any('Data Constraints' in h for h,_,_ in b['tbls'])
    flag = 'OK ' if has else 'NO '
    if not has: missing.append(b['h'])
    print("%s %-70s %s" % (flag, b['h'][:70], [ (h[:22],r,c) for h,r,c in b['tbls'] ]))
print()
print("=== thieu DC&C: %d ===" % len(missing))
for m in missing: print("  -", m)
