# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
doc = Document(SRC)
def walk(el, depth=0, path='body'):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p','tbl'): yield tag, ch, path
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            # describe the sdt
            pr = ch.find(qn('w:sdtPr'))
            alias = pr.find(qn('w:alias')) if pr is not None else None
            tagel = pr.find(qn('w:tag')) if pr is not None else None
            desc = 'sdt(%s/%s)' % (alias.get(qn('w:val')) if alias is not None else '-',
                                   tagel.get(qn('w:val')) if tagel is not None else '-')
            if c is not None:
                for x in walk(c, depth+1, path+'>'+desc): yield x
items=list(walk(doc.element.body))
cur=None
for i,(tag,el,path) in enumerate(items):
    if path!=cur:
        txt=''
        if tag=='p': txt=Paragraph(el,doc).text[:60]
        print('--- from [%d] path=%s   first=%r' % (i,path,txt))
        cur=path
print('total', len(items))
