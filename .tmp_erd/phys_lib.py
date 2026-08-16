# -*- coding: utf-8 -*-
"""Ký hiệu và bố cục cho ERD vật lý (crow's foot, drawio)."""
import html

# ─────────────────────────────── ký hiệu hộp ─────────────────────────────────
# (nền, viền, chữ) — khớp bảng chú giải ở §3.2 của TDS
STYLE = {
    'custom': ('#FFFFFF', '#1F3D63', '#12263F'),   # bảng dl_* do dự án tạo
    'ext':    ('#E8F2FF', '#2E6DA4', '#123A5E'),   # bảng lõi + cột dlm_
    'core':   ('#F2F2F2', '#9E9E9E', '#4A4A4A'),   # bảng lõi dùng nguyên trạng
    'view':   ('#F5EEFF', '#7B4FA8', '#4B2870'),   # SQL VIEW (_auto = False)
    'm2m':    ('#FFF4E5', '#D79B00', '#7F5200'),   # bảng nối Many2many
    'ref':    ('#EDEDED', '#B0B0B0', '#707070'),   # hộp nhắc lại từ trang khác
}
MODULE_TAG = {
    'dl_base': '#7B4FA8', 'dl_config': '#D79B00', 'dl_product': '#4CA37E',
    'dl_technical': '#2E6DA4', 'dl_sale': '#C08A00', 'dl_inventory': '#B85450',
    'odoo_core': '#9E9E9E',
}
POLICY = {
    'CASCADE':  '#B85450',
    'RESTRICT': '#2D7600',
    'SET NULL': '#8A8A8A',
}

W = 300           # bề ngang hộp
HDR = 26          # chiều cao dải tiêu đề
ROW = 16          # chiều cao một dòng cột
PAD = 8
COL_GAP = 120     # khoảng cách giữa hai cột hộp — chừa chỗ cho cạnh đi dọc
ROW_GAP = 40


def esc(s):
    return html.escape(s, quote=True)


def box_h(spec, compact=False):
    n = 1 if compact else len(spec['cols'])
    return HDR + ROW * n + (ROW if spec.get('footer') and not compact else 0) + PAD


def box(cid, table, spec, x, y, compact=False, ref_from=None):
    """Một hộp bảng. compact=True chỉ vẽ PK (dùng cho trang Overview)."""
    kind = 'ref' if ref_from else spec['style']
    fill, stroke, fg = STYLE[kind]
    dash = 'dashed=1;' if spec['style'] == 'view' else ''
    rounded = 'rounded=1;arcSize=20;' if spec['style'] == 'm2m' else 'rounded=0;'

    cols = spec['cols'][:1] if compact else spec['cols']
    lines = []
    for name, typ, mark in cols:
        nm = '<b>%s</b>' % name if mark == 'PK' else name
        badge = ''
        if mark == 'PK':
            badge = " <span style='color:#B85450;font-size:8px'>PK</span>"
        elif mark == 'FK':
            badge = " <span style='color:#2E6DA4;font-size:8px'>FK</span>"
        elif mark == 'U':
            badge = " <span style='color:#7B4FA8;font-size:8px'>U</span>"
        lines.append("<div style='padding:0 6px'>%s%s"
                     "<span style='color:#8A8A8A'> : %s</span></div>"
                     % (nm, badge, typ))
    if ref_from:
        lines.append("<div style='padding:0 6px;color:#707070;font-style:italic'>"
                     "định nghĩa ở trang %s</div>" % ref_from)
    elif spec.get('footer') and not compact:
        lines.append("<div style='padding:0 6px;color:#8A8A8A;font-style:italic'>%s</div>"
                     % spec['footer'])

    tag = MODULE_TAG.get(spec['module'], '#9E9E9E')
    head = ("<div style='font-weight:bold;padding:4px;text-align:center;color:%s;"
            "border-bottom:1px solid %s'>%s</div>" % (fg, stroke, table))
    label = head + ''.join(lines)
    style = ('%swhiteSpace=wrap;html=1;verticalAlign=top;align=left;overflow=hidden;'
             'fillColor=%s;strokeColor=%s;fontColor=%s;fontSize=10;strokeWidth=%s;%s'
             % (rounded, fill, stroke, fg, '2' if kind == 'custom' else '1', dash))
    h = HDR + ROW * len(lines) + PAD
    xml = ('<mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
           '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/></mxCell>'
           % (cid, esc(label), style, x, y, W, h))
    return xml, h


def edge(cid, src, dst, col, policy, nullable, cross=False):
    """Cạnh FK: cha → con. Vòng tròn phía cha = cha TÙY CHỌN (FK cho phép NULL)."""
    colr = POLICY.get(policy.upper(), '#8A8A8A')
    start = 'ERzeroToOne' if nullable.upper() == 'NULL' else 'ERone'
    dash = 'dashed=1;' if policy.upper() == 'SET NULL' else ''
    style = ('edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;jettySize=auto;'
             'startArrow=%s;startFill=0;endArrow=ERmany;endFill=0;'
             'strokeColor=%s;fontColor=#5A5A5A;fontSize=9;%s%s'
             % (start, colr, dash, 'strokeWidth=2;' if cross else ''))
    lbl = '%s · %s' % (col, policy)
    return ('<mxCell id="%s" value="%s" style="%s" edge="1" parent="1" source="%s" target="%s">'
            '<mxGeometry relative="1" as="geometry"/></mxCell>'
            % (cid, esc(lbl), style, src, dst))


def text(cid, s, x, y, w, size=14, bold=True, color='#12263F', h=None):
    style = ('text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=%d;%s'
             'fontColor=%s;' % (size, 'fontStyle=1;' if bold else '', color))
    return ('<mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
            '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/></mxCell>'
            % (cid, esc(s), style, x, y, w, h or (size + 10)))


# ─────────────────────────────── bố cục cột ──────────────────────────────────

def pack(items, ncol, x0, y0):
    """Xếp (key, height) vào ncol cột theo kiểu 'cột nào thấp nhất thì bỏ vào'.

    Trả về {key: (x, y)}. Giữ nguyên thứ tự đầu vào để bảng liên quan nằm gần nhau.
    """
    heights = [y0] * ncol
    pos = {}
    for key, h in items:
        i = heights.index(min(heights))
        pos[key] = (x0 + i * (W + COL_GAP), heights[i])
        heights[i] += h + ROW_GAP
    return pos, max(heights)


def page(name, cells, w, h):
    return ('  <diagram name="%s" id="%s">\n'
            '    <mxGraphModel dx="1600" dy="1000" grid="0" gridSize="10" guides="1" '
            'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            'pageWidth="%d" pageHeight="%d" math="0" shadow="0">\n'
            '      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n        '
            % (esc(name), esc(name.split()[0].strip('.')) or 'p', int(w), int(h))
            + '\n        '.join(cells)
            + '\n      </root>\n    </mxGraphModel>\n  </diagram>\n')


def write(pages, path):
    xml = ('<mxfile host="app.diagrams.net" agent="DLM-ERP physical ERD generator" pages="%d">\n'
           % len(pages)) + ''.join(pages) + '</mxfile>\n'
    open(path, 'w', encoding='utf-8').write(xml)
