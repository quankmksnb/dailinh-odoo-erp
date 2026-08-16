# -*- coding: utf-8 -*-
"""Do trước khi sửa: đếm chỗ xuất hiện + cấu trúc run của từng đích."""
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
TOKENS = ['dl_lifecycle_state', 'dl_waste_rate', 'dl_has_recorvery',
          'dl_customer_group', 'dlm_has_recovery', 'dl_pricing_waste_rule']
PHRASES = ['10 physical columns spread over 3 native tables',
           '8 Odoo core tables extended',
           '10 further core tables referenced',
           'Table: stock_location [Native]']

def ptext(p): return ''.join(t.text or '' for t in p.iter(qn('w:t')))

def walk(el, path=''):
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p', 'tbl'):
            yield tag, ch, path
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c, path + 'sdt/'):
                    yield x

doc = Document(SRC)
paras = []
for tag, el, path in walk(doc.element.body):
    if tag == 'p':
        paras.append((el, path))
    else:
        for p in el.iter(qn('w:p')):
            paras.append((p, path + 'tbl/'))
print('tong so doan (ke ca trong bang): %d' % len(paras))
print()
for tok in TOKENS:
    rx = re.compile(r'(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])' % re.escape(tok))
    hits = [(p, path) for p, path in paras if rx.search(ptext(p))]
    print('== %-22s %d cho' % (tok, len(hits)))
    for p, path in hits:
        runs = p.findall(qn('w:r'))
        print('     [%s] runs=%d | %s' % (path or 'body', len(runs), ptext(p)[:110]))
print()
for ph in PHRASES:
    hits = [(p, path) for p, path in paras if ph in ptext(p)]
    print('== %r -> %d cho' % (ph[:50], len(hits)))
    for p, path in hits:
        runs = p.findall(qn('w:r'))
        wts = sum(1 for _ in p.iter(qn('w:t')))
        print('     [%s] runs=%d wt=%d | %s' % (path or 'body', len(runs), wts, ptext(p)[:150]))
