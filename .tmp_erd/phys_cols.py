# -*- coding: utf-8 -*-
"""Trích danh sách cột của từng bảng từ §3.1 của Report 4.0_TDS.docx.

Bản vẽ ERD vật lý PHẢI khớp tài liệu, nên nguồn cột lấy thẳng từ tài liệu chứ
không dựng lại từ AST — dựng lại là mở đường cho hai bản mô tả lệch nhau.

Ra: .tmp_erd/phys_cols.json  {table: {kind, title, cols: [...]}}
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document                                    # noqa: E402
from docx.oxml.ns import qn                                   # noqa: E402

D = os.path.dirname(os.path.abspath(__file__))
SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"

# "Table: dl_bom" · "Table: stock_picking [Inherit]" · "View: dl_scrap_recovery_report [SQL VIEW]"
# Đuôi "(...)" là chú thích tự do trong tiêu đề — "Table: dl_quotation_request (RFQ)".
HEAD = re.compile(r'^(Table|View|Mixin):\s*([A-Za-z0-9_. +]+?)\s*'
                  r'(?:\[([^\]]*)\])?\s*(?:\(.*\))?$')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def cellt(tc):
    return ' '.join(''.join(x.text or '' for x in tc.iter(qn('w:t'))).split())


def walk(el):
    """Duyệt block, chui vào w:sdt — phần §3.1 cũ nằm trong content control."""
    for ch in el:
        tag = ch.tag.split('}')[1]
        if tag in ('p', 'tbl'):
            yield tag, ch
        elif tag == 'sdt':
            c = ch.find(qn('w:sdtContent'))
            if c is not None:
                for x in walk(c):
                    yield x


def parse(src=SRC):
    doc = Document(src)
    on, cur, out = False, None, {}
    for tag, el in walk(doc.element.body):
        if tag == 'p':
            t = ptext(el).strip()
            if t == '3. Data Model':
                on = True
            elif t == '4. Security Design':
                break
            if not on or not t:
                continue
            m = HEAD.match(t)
            if m:
                what, name, flag = m.group(1), m.group(2).strip(), (m.group(3) or '').strip()
                # "product_product + product_template" -> bảng đầu là chủ
                name = name.split('+')[0].strip()
                cur = name
                out.setdefault(name, {'kind': what, 'flag': flag, 'title': t, 'cols': []})
        elif tag == 'tbl' and on and cur:
            rows = el.findall(qn('w:tr'))
            if not rows:
                continue
            hdr = [cellt(tc) for tc in rows[0].findall(qn('w:tc'))]
            if hdr[:2] != ['Column', 'Type']:
                continue
            for tr in rows[1:]:
                c = [cellt(tc) for tc in tr.findall(qn('w:tc'))]
                c += [''] * (5 - len(c))
                out[cur]['cols'].append({'name': c[0], 'type': c[1], 'pg': c[2],
                                         'cons': c[3], 'notes': c[4]})
    return out


if __name__ == '__main__':
    out = parse()
    json.dump(out, open(os.path.join(D, 'phys_cols.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('bang doc duoc: %d' % len(out))
    empty = [k for k, v in out.items() if not v['cols']]
    print('bang KHONG co bang cot (%d): %s' % (len(empty), empty))
    print()
    for k in sorted(out):
        v = out[k]
        print('%-34s %-6s %-12s %3d cot' % (k, v['kind'], v['flag'], len(v['cols'])))
