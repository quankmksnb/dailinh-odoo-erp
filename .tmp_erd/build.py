# -*- coding: utf-8 -*-
"""Ráp các trang thành docs/erd/DLM-ERP_Conceptual_ERD.drawio + kiểm tra bố cục."""
import importlib
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erd_lib import build  # noqa: E402

MODULES = ['pg_overview', 'pg_a', 'pg_b', 'pg_c', 'pg_d', 'pg_e', 'pg_f', 'pg_fg']
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'docs', 'erd', 'DLM-ERP_Conceptual_ERD.drawio')


def collect():
    pages = []
    for m in MODULES:
        try:
            mod = importlib.import_module(m)
        except ImportError:
            print('  (bo qua %s - chua co)' % m)
            continue
        importlib.reload(mod)
        r = mod.build()
        pages.extend(r if isinstance(r, list) else [r])
    return pages


def rects(diagram):
    out = []
    for c in diagram.findall('.//mxCell'):
        if c.get('vertex') != '1':
            continue
        g = c.find('mxGeometry')
        if g is None or g.get('x') is None:
            continue
        st = c.get('style') or ''
        if 'text;' in st:                      # nhãn tiêu đề: bỏ qua
            continue
        out.append((c.get('id'), float(g.get('x')), float(g.get('y')),
                    float(g.get('width')), float(g.get('height'))))
    return out


def check(path):
    root = ET.parse(path).getroot()
    ok = True
    for d in root.findall('diagram'):
        cells = d.findall('.//mxCell')
        ids = [c.get('id') for c in cells]
        dup = [k for k, v in Counter(ids).items() if v > 1]
        verts = {c.get('id') for c in cells if c.get('vertex') == '1'}
        edges = [c for c in cells if c.get('edge') == '1']
        bad = [(e.get('source'), e.get('target')) for e in edges
               if e.get('source') not in verts or e.get('target') not in verts]
        rs = rects(d)
        clash = []
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if (a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                        and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]):
                    clash.append('%s x %s' % (a[0], b[0]))
        print('[%-42s] vertex=%-3d edge=%-3d' % (d.get('name'), len(verts),
                                                len(edges)))
        for tag, val in (('id trung', dup), ('edge thieu dau noi', bad),
                         ('CHONG LAN hop', clash)):
            if val:
                ok = False
                print('   !! %s: %s' % (tag, val))
    return ok


if __name__ == '__main__':
    pages = collect()
    if '--split' in sys.argv:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preview')
        if not os.path.isdir(d):
            os.makedirs(d)
        for pg in pages:
            build([pg], os.path.join(d, 'p%d.drawio' % pg.idx))
        print('split -> %s' % d)
    tmp = OUT + '.tmp'
    build(pages, tmp)
    good = check(tmp)
    if good or '--force' in sys.argv:
        if os.path.exists(OUT):
            os.remove(OUT)
        os.rename(tmp, OUT)
        print('\n=> %s (%d trang)' % (OUT, len(pages)))
    else:
        print('\n!! con loi, giu nguyen ban cu; xem %s' % tmp)
    sys.exit(0 if good else 1)
