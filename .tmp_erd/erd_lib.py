# -*- coding: utf-8 -*-
"""Thư viện ký hiệu Chen/EER (Elmasri & Navathe) để sinh file .drawio.

Quy ước ký hiệu hiện thực trong module này:
  - Kiểu thực thể            : hình chữ nhật đơn
  - Kiểu thực thể yếu        : hình chữ nhật KÉP
  - Entity biên (sub-ERD khác): hình chữ nhật nét đứt, xám, chỉ có tên
  - Quan hệ                  : hình thoi đơn
  - Quan hệ định danh        : hình thoi KÉP
  - Tham gia bộ phận (partial): đường đơn
  - Tham gia toàn bộ (total)  : đường KÉP (shape=link)
  - Lực lượng                : nhãn 1 / M / N trên cạnh
  - Chuyên biệt hoá (ISA)    : vòng tròn chứa d (disjoint) hoặc o (overlapping),
                               cung nối lớp con mang ký hiệu ⊂
  - Tham chiếu mềm (snapshot): đường chấm, không khoá ngoại
"""
from xml.sax.saxutils import escape as _esc


def esc(s):
    return _esc(s, {'"': '&quot;', "'": '&#39;', '\n': '&#10;'})


# ----------------------------------------------------------------- styles
ENTITY = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;'
          'fontSize=13;fontStyle=1;verticalAlign=middle;align=center;')
ENTITY_SUB = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;'
              'fontSize=13;fontStyle=1;verticalAlign=middle;align=center;')
ENTITY_WEAK = ('shape=ext;double=1;rounded=0;whiteSpace=wrap;html=1;fillColor=#ffe6cc;'
               'strokeColor=#d79b00;fontSize=13;fontStyle=1;verticalAlign=middle;')
ENTITY_EXT = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#999999;'
              'dashed=1;dashPattern=8 6;fontSize=12;fontStyle=2;fontColor=#666666;'
              'verticalAlign=middle;align=center;')
ENTITY_TODO = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#b85450;'
               'dashed=1;dashPattern=8 6;fontSize=13;fontStyle=3;fontColor=#b85450;'
               'verticalAlign=middle;align=center;')
# thực thể dẫn xuất (derived): không lưu trữ, tính lại mỗi lần đọc
ENTITY_DERIVED = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#f3ebff;strokeColor=#9673a6;'
                  'dashed=1;dashPattern=8 4;fontSize=13;fontStyle=1;fontColor=#6a4c93;'
                  'verticalAlign=middle;align=center;')

REL = ('rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;'
       'fontSize=11;verticalAlign=middle;align=center;')
REL_ID = ('rhombus;double=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;'
          'strokeColor=#d79b00;fontSize=11;verticalAlign=middle;align=center;')
REL_DERIVED = ('rhombus;whiteSpace=wrap;html=1;fillColor=#f3ebff;strokeColor=#9673a6;'
               'dashed=1;dashPattern=8 4;fontSize=11;fontColor=#6a4c93;'
               'verticalAlign=middle;align=center;')

ISA = ('ellipse;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;'
       'fontSize=16;fontStyle=1;verticalAlign=middle;align=center;')

ATTR = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#b3b3b3;'
        'align=left;verticalAlign=top;fontSize=10;spacing=4;spacingLeft=6;')

NOTE = ('shape=note;whiteSpace=wrap;html=1;size=16;fillColor=#fff9e6;'
        'strokeColor=#d6b656;align=left;verticalAlign=top;fontSize=11;')
LEGEND = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#666666;'
          'align=left;verticalAlign=top;fontSize=11;spacing=6;')
TITLE = ('text;html=1;strokeColor=none;fillColor=none;align=left;'
         'verticalAlign=middle;fontSize=20;fontStyle=1;fontColor=#333333;')
SUBTITLE = ('text;html=1;strokeColor=none;fillColor=none;align=left;'
            'verticalAlign=middle;fontSize=12;fontColor=#666666;')

# cạnh: tham gia bộ phận (single line) / toàn bộ (double line)
E_PART = ('endArrow=none;html=1;rounded=0;fontSize=12;fontStyle=1;strokeColor=#333333;'
          'labelBackgroundColor=#ffffff;exitPerimeter=1;')
E_TOTAL = ('shape=link;html=1;rounded=0;fontSize=12;fontStyle=1;strokeColor=#333333;'
           'labelBackgroundColor=#ffffff;width=3;')
E_ISA = ('endArrow=none;html=1;rounded=0;fontSize=14;strokeColor=#9673a6;'
         'strokeWidth=2;labelBackgroundColor=#ffffff;')
E_SOFT = ('endArrow=open;endFill=0;html=1;rounded=0;dashed=1;dashPattern=2 4;'
          'fontSize=11;strokeColor=#9673a6;labelBackgroundColor=#ffffff;'
          'fontColor=#9673a6;')
E_ATTR = ('endArrow=none;html=1;rounded=0;strokeColor=#b3b3b3;dashed=1;'
          'dashPattern=3 3;')
# quan hệ suy diễn: dữ liệu đọc lại từ nơi khác, không lưu khoá ngoại
E_DERIV = ('endArrow=none;html=1;rounded=0;dashed=1;dashPattern=8 4;fontSize=12;'
           'fontStyle=1;strokeColor=#9673a6;fontColor=#6a4c93;'
           'labelBackgroundColor=#ffffff;')

# ----------------------------------------------------------------- sizes
EW, EH = 210, 58        # entity
RW, RH = 140, 74        # relationship diamond
IW = 46                 # ISA circle


class Page(object):
    """Một trang .drawio; sinh cell với parent riêng để id không đụng trang khác."""

    def __init__(self, idx, name, w=2400, h=1600):
        self.idx = idx
        self.name = name
        self.pw, self.ph = w, h
        self.cells = []
        self._seq = 0
        self._ids = set()

    # -- id helpers -------------------------------------------------
    def pid(self, key):
        return 'p%d-%s' % (self.idx, key)

    def _next(self, prefix):
        self._seq += 1
        return '%s%d' % (prefix, self._seq)

    # -- vertices ---------------------------------------------------
    def box(self, key, label, x, y, style, w, h):
        assert key not in self._ids, 'trùng id: %s (trang %s)' % (key, self.name)
        self._ids.add(key)
        self.cells.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">\n'
            '          <mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/>\n'
            '        </mxCell>' % (self.pid(key), esc(label), style,
                                   self.pid('1'), x, y, w, h))
        return key

    def entity(self, key, label, x, y, kind='normal', w=EW, h=EH):
        st = {'normal': ENTITY, 'sub': ENTITY_SUB, 'weak': ENTITY_WEAK,
              'ext': ENTITY_EXT, 'todo': ENTITY_TODO,
              'derived': ENTITY_DERIVED}[kind]
        return self.box(key, label, x, y, st, w, h)

    def rel(self, key, label, x, y, ident=False, w=RW, h=RH, derived=False):
        st = REL_DERIVED if derived else (REL_ID if ident else REL)
        return self.box(key, label, x, y, st, w, h)

    def isa(self, key, x, y, disjoint=True):
        return self.box(key, 'd' if disjoint else 'o', x, y, ISA, IW, IW)

    def attrs(self, key, title, items, x, y, w=250):
        """Hộp thuộc tính: khoá nghiệp vụ gạch chân (bọc trong <u>...</u>)."""
        body = '<br/>'.join('&#8226; ' + it for it in items)
        html = ('<b>%s</b><hr size="1"/>%s' % (title, body))
        h = 34 + 16 * len(items)
        self.cells.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">\n'
            '          <mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/>\n'
            '        </mxCell>' % (self.pid(key), esc(html), ATTR, self.pid('1'),
                                   x, y, w, h))
        self._ids.add(key)
        return key

    def note(self, text, x, y, w=340, h=130):
        return self.box(self._next('nt'), text, x, y, NOTE, w, h)

    def legend(self, text, x, y, w=420, h=300):
        return self.box(self._next('lg'), text, x, y, LEGEND, w, h)

    def title(self, text, sub, x=40, y=30):
        self.box(self._next('ti'), text, x, y, TITLE, 1400, 34)
        if sub:
            self.box(self._next('ti'), sub, x, y + 32, SUBTITLE, 1400, 24)

    # -- edges ------------------------------------------------------
    def edge(self, a, b, label='', style=E_PART, entry=None, exit_=None,
             pts=None):
        st = style
        if exit_:
            st += 'exitX=%s;exitY=%s;exitDx=0;exitDy=0;' % exit_
        if entry:
            st += 'entryX=%s;entryY=%s;entryDx=0;entryDy=0;' % entry
        if pts:
            st += 'edgeStyle=orthogonalEdgeStyle;'
            geo = ('          <mxGeometry relative="1" as="geometry">\n'
                   '            <Array as="points">\n%s\n'
                   '            </Array>\n'
                   '          </mxGeometry>'
                   % '\n'.join('              <mxPoint x="%d" y="%d"/>' % (px, py)
                               for px, py in pts))
        else:
            geo = '          <mxGeometry relative="1" as="geometry"/>'
        self.cells.append(
            '        <mxCell id="%s" value="%s" style="%s" edge="1" parent="%s" '
            'source="%s" target="%s">\n%s\n'
            '        </mxCell>' % (self.pid(self._next('e')), esc(label), st,
                                   self.pid('1'), self.pid(a), self.pid(b), geo))

    def link(self, a, b, card='', total=False, **kw):
        """Cạnh entity–relationship: card = '1'/'M'/'N', total = tham gia toàn bộ."""
        self.edge(a, b, card, E_TOTAL if total else E_PART, **kw)

    def isa_link(self, sup, circle, sub_list, total=False):
        """Vòng cung ISA: lớp cha — vòng tròn — các lớp con (mang ký hiệu ⊂)."""
        self.edge(sup, circle, '', E_TOTAL if total else E_ISA)
        for s in sub_list:
            self.edge(circle, s, '⊂', E_ISA)

    def soft(self, a, b, label=''):
        self.edge(a, b, label, E_SOFT)

    def attach(self, ent, att):
        self.edge(ent, att, '', E_ATTR)

    # -- render -----------------------------------------------------
    def xml(self):
        return (
            '  <diagram name="%s" id="page-%d">\n'
            '    <mxGraphModel dx="1600" dy="1000" grid="0" gridSize="10" guides="1" '
            'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            'pageWidth="%d" pageHeight="%d" math="0" shadow="0">\n'
            '      <root>\n'
            '        <mxCell id="%s"/>\n'
            '        <mxCell id="%s" parent="%s"/>\n'
            '%s\n'
            '      </root>\n'
            '    </mxGraphModel>\n'
            '  </diagram>'
            % (esc(self.name), self.idx, self.pw, self.ph,
               self.pid('0'), self.pid('1'), self.pid('0'),
               '\n'.join(self.cells)))


LEGEND_TEXT = (
    '<b>CH&#218; GI&#7842;I K&#221; HI&#7878;U &#8212; Chen / EER (Elmasri &amp; Navathe)</b>'
    '<hr size="1"/>'
    '&#9633; H&#7897;p &#273;&#417;n &#8212; ki&#7875;u th&#7921;c th&#7875;<br/>'
    '&#9636; H&#7897;p k&#233;p (cam) &#8212; th&#7921;c th&#7875; y&#7871;u (weak entity)<br/>'
    '&#9633; H&#7897;p n&#233;t &#273;&#7913;t x&#225;m &#8212; entity bi&#234;n '
    '(thu&#7897;c sub-ERD kh&#225;c, kh&#244;ng v&#7869; thu&#7897;c t&#237;nh)<br/>'
    '&#9671; H&#236;nh thoi &#8212; ki&#7875;u quan h&#7879;<br/>'
    '&#9671; H&#236;nh thoi k&#233;p &#8212; quan h&#7879; &#273;&#7883;nh danh '
    '(identifying relationship)<br/>'
    '&#8212; &#272;&#432;&#7901;ng &#273;&#417;n &#8212; tham gia b&#7897; ph&#7853;n (partial)<br/>'
    '&#8801; &#272;&#432;&#7901;ng k&#233;p &#8212; tham gia to&#224;n b&#7897; (total)<br/>'
    '<b>1 / M / N</b> tr&#234;n c&#7841;nh &#8212; l&#7921;c l&#432;&#7907;ng (cardinality ratio)<br/>'
    '&#9711; V&#242;ng tr&#242;n <b>d</b> / <b>o</b> &#8212; chuy&#234;n bi&#7879;t ho&#225; '
    'disjoint / overlapping; cung mang <b>&#8834;</b> tr&#7887; v&#7873; l&#7899;p con<br/>'
    '&#8943; &#272;&#432;&#7901;ng ch&#7845;m t&#237;m &#8212; tham chi&#7871;u m&#7873;m '
    '(snapshot, c&#7889; &#253; kh&#244;ng c&#243; kho&#225; ngo&#7841;i)<br/>'
    '&#9642; H&#7897;p tr&#7855;ng c&#7841;nh entity &#8212; thu&#7897;c t&#237;nh nghi&#7879;p '
    'v&#7909; ch&#237;nh; <u>g&#7841;ch ch&#226;n</u> = &#273;&#7883;nh danh nghi&#7879;p v&#7909;'
)


def build(pages, out_path):
    xml = ('<mxfile host="app.diagrams.net" agent="DLM-ERP conceptual ERD generator" '
           'version="24.7.17" type="device">\n%s\n</mxfile>\n'
           % '\n'.join(p.xml() for p in pages))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return out_path
