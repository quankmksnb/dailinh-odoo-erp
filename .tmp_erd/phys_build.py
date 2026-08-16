# -*- coding: utf-8 -*-
"""Sinh docs/erd/DLM-ERP_Physical_ERD.drawio — 7 trang đúng như §3.2 của TDS.

    venv/Scripts/python.exe .tmp_erd/phys_build.py [--split]

--split xuất thêm từng trang ra .tmp_erd/preview_phys/ để soi PNG cho nhanh.
"""
import io
import os
import sys
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

import phys_data as PD          # noqa: E402
import phys_lib as L            # noqa: E402

OUT = os.path.join(os.path.dirname(D), 'docs', 'erd', 'DLM-ERP_Physical_ERD.drawio')
TOP = 150                       # chừa chỗ cho tiêu đề + chú giải

PAGE_TITLE = {
    'A': 'A — Partners, Users, RBAC',
    'B': 'B — Product & Material catalogue',
    'C': 'C — Engineering: drawings, BOM, RFQ',
    'D': 'D — Sales: quotations & orders',
    'E': 'E — Pricing configuration & approval',
    'F': 'F — Inventory',
}
NCOL = {'A': 2, 'B': 3, 'C': 4, 'D': 2, 'E': 4, 'F': 3}

LEGEND = ('Hộp viền đậm = bảng do dự án tạo (dl_*) · nền xanh nhạt = bảng lõi Odoo có thêm cột '
          'dlm_ · nền xám = bảng lõi dùng nguyên trạng · viền đứt tím = SQL VIEW · hộp bo tròn cam '
          '= bảng nối Many2many · hộp xám nhạt = nhắc lại từ trang khác.')
LEGEND2 = ("Cạnh: chân quạ ở đầu 'nhiều'. Vòng tròn ở đầu 'một' = cha TÙY CHỌN (FK cho phép "
           "NULL). Màu cạnh = ON DELETE — đỏ CASCADE · xanh lá RESTRICT · xám đứt SET NULL. "
           "Cạnh đậm = nối sang trang khác.")


def counter():
    n = [1]

    def nxt(prefix):
        n[0] += 1
        return '%s%d' % (prefix, n[0])
    return nxt


def overlaps(rects):
    bad = []
    ks = list(rects)
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            (ax, ay, aw, ah), (bx, by, bw, bh) = rects[ks[i]], rects[ks[j]]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                bad.append('%s x %s' % (ks[i], ks[j]))
    return bad


def build_subject(g, tables, fks):
    """Một trang chủ đề: bảng của nhóm + hộp nhắc lại cho bảng ở trang khác."""
    nxt = counter()
    own = [t for t in PD.GROUP_OF if PD.GROUP_OF[t] == g]
    ownset = set(own)

    # Mỗi cạnh chỉ vẽ MỘT lần, ở trang của bảng CON. Bảng cha ở trang khác được
    # nhắc lại bằng hộp xám — nếu vẽ cả cạnh có cha thuộc trang này thì trang A
    # (chứa res_partner, res_users) sẽ hút về gần như toàn bộ bảng của hệ thống.
    mine = [e for e in fks if e[0] in ownset]
    refs = []
    for child, col, parent, ondel, nullable in mine:
        if parent not in ownset and parent not in refs:
            refs.append(parent)

    cells, rects, nid = [], {}, {}
    cells.append(L.text(nxt('t'), 'DLM-ERP — Physical ERD · %s' % PAGE_TITLE[g],
                        40, 30, 1400, size=22))
    cells.append(L.text(nxt('t'), LEGEND, 40, 66, 1500, size=10, bold=False, color='#5A5A5A', h=32))
    cells.append(L.text(nxt('t'), LEGEND2, 40, 100, 1500, size=10, bold=False, color='#5A5A5A', h=32))

    # cột trái: hộp nhắc lại — phần lớn là bảng cha dùng chung (hub)
    x = 40
    y = TOP
    for t in refs:
        spec = tables[t]
        cid = nxt('r')
        home = PD.GROUP_OF.get(t)
        xml, h = L.box(cid, t, spec, x, y, compact=True,
                       ref_from=home if home else 'Odoo lõi')
        cells.append(xml)
        rects[cid] = (x, y, L.W, h)
        nid[t] = cid
        y += h + L.ROW_GAP

    x0 = 40 + (L.W + L.COL_GAP if refs else 0)
    items = [(t, L.box_h(tables[t])) for t in own]
    pos, ymax = L.pack(items, NCOL[g], x0, TOP)
    for t in own:
        spec = tables[t]
        cid = nxt('b')
        bx, by = pos[t]
        xml, h = L.box(cid, t, spec, bx, by)
        cells.append(xml)
        rects[cid] = (bx, by, L.W, h)
        nid[t] = cid

    for child, col, parent, ondel, nullable in mine:
        if child not in nid or parent not in nid:
            continue
        cross = PD.GROUP_OF.get(child) != PD.GROUP_OF.get(parent)
        cells.append(L.edge(nxt('e'), nid[parent], nid[child], col, ondel, nullable, cross))

    w = x0 + NCOL[g] * (L.W + L.COL_GAP) + 80
    return (L.page('%s. %s' % (g, PAGE_TITLE[g].split('—', 1)[1].strip()), cells, w,
                   max(ymax, y) + 80),
            overlaps(rects), len(own), len(refs), len(mine))


def build_overview(tables, fks):
    """Trang 0: mọi bảng, chỉ tên + khoá chính, xếp theo nhóm chủ đề."""
    nxt = counter()
    cells, rects, nid = [], {}, {}
    cells.append(L.text(nxt('t'), 'DLM-ERP — Physical ERD · 0 — Overview / Table map',
                        40, 30, 1600, size=22))
    cells.append(L.text(nxt('t'),
                        'Toàn bộ 56 đối tượng vật lý, chỉ tên bảng và khoá chính, gom theo 6 vùng '
                        'chủ đề. Cột cuối là bảng lõi Odoo bị tham chiếu nhưng nằm ngoài phạm vi '
                        'mô hình. Thuộc tính đầy đủ xem trang A–F.',
                        40, 64, 1700, size=11, bold=False, color='#5A5A5A', h=40))
    cells.append(L.text(nxt('t'), LEGEND2, 40, 106, 1700, size=10, bold=False,
                        color='#5A5A5A', h=32))

    x = 40
    ymax = TOP
    for g, name, ts in PD.GROUPS:
        cells.append(L.text(nxt('h'), '%s — %s' % (g, name), x, TOP - 34, L.W, size=13))
        y = TOP
        for t in ts:
            cid = nxt('o')
            xml, h = L.box(cid, t, tables[t], x, y, compact=True)
            cells.append(xml)
            rects[cid] = (x, y, L.W, h)
            nid[t] = cid
            y += h + 22
        ymax = max(ymax, y)
        x += L.W + L.COL_GAP

    cells.append(L.text(nxt('h'), 'Lõi Odoo — chỉ bị tham chiếu', x, TOP - 34, L.W, size=13))
    y = TOP
    for t in PD.PERIPHERAL:
        cid = nxt('o')
        xml, h = L.box(cid, t, tables[t], x, y, compact=True)
        cells.append(xml)
        rects[cid] = (x, y, L.W, h)
        nid[t] = cid
        y += h + 22
    ymax = max(ymax, y)

    for child, col, parent, ondel, nullable in fks:
        if child not in nid or parent not in nid:
            continue
        cross = PD.GROUP_OF.get(child) != PD.GROUP_OF.get(parent)
        cells.append(L.edge(nxt('e'), nid[parent], nid[child], '', ondel, nullable, cross))
    return (L.page('0. Overview - Table map', cells, x + L.W + 80, ymax + 80),
            overlaps(rects))


def main():
    o = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    tables, fks = PD.build()
    pages = []

    pg, bad = build_overview(tables, fks)
    pages.append(pg)
    o.write('[0 Overview          ] %d bang, %d canh %s\n'
            % (len(tables), len(fks), '!! CHONG LAN: %s' % bad[:4] if bad else ''))

    for g, _, _ in PD.GROUPS:
        pg, bad, nown, nref, nedge = build_subject(g, tables, fks)
        pages.append(pg)
        o.write('[%s %-18s] %2d bang + %2d hop nhac lai, %3d canh %s\n'
                % (g, PAGE_TITLE[g].split('—')[1].strip()[:18], nown, nref, nedge,
                   '!! CHONG LAN: %s' % bad[:4] if bad else ''))

    L.write(pages, OUT)
    o.write('\n=> %s (%d trang)\n' % (OUT, len(pages)))

    if '--split' in sys.argv:
        d = os.path.join(D, 'preview_phys')
        if not os.path.isdir(d):
            os.makedirs(d)
        for i, pg in enumerate(pages):
            L.write([pg], os.path.join(d, 'q%d.drawio' % i))
        o.write('split -> %s\n' % d)
    o.flush()


if __name__ == '__main__':
    main()
