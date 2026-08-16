# -*- coding: utf-8 -*-
"""Sinh file draw.io (.drawio) Conceptual ERD cho DLM-ERP.

Nguồn: docs/conceptual-data-model.md
Output: docs/erd/DLM-ERP_Conceptual_ERD.drawio  (nhiều page: Overview + 6 Sub-ERD)
"""
import os
from xml.sax.saxutils import escape as _esc


def escape(s):
    return _esc(s, {'"': '&quot;', "'": '&#39;', '\n': '&#10;'})

OUT = os.path.join(os.path.dirname(__file__), '..', 'docs', 'erd',
                   'DLM-ERP_Conceptual_ERD.drawio')

E_STYLE = ('rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;'
           'fontSize=12;fontStyle=1;verticalAlign=middle;')
E_WEAK = ('shape=ext;double=1;rounded=0;whiteSpace=wrap;html=1;fillColor=#d5e8d4;'
          'strokeColor=#82b366;fontSize=12;fontStyle=1;')
R_STYLE = ('rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;'
           'fontSize=11;')
R_IDENT = ('rhombus;double=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;'
           'strokeColor=#d79b00;fontSize=11;')
L_STYLE = ('endArrow=none;html=1;rounded=0;fontSize=11;strokeColor=#666666;'
           'labelBackgroundColor=#ffffff;')
A_STYLE = ('endArrow=block;html=1;rounded=0;fontSize=11;strokeColor=#9673a6;'
           'labelBackgroundColor=#ffffff;edgeStyle=orthogonalEdgeStyle;')
NOTE = ('shape=note;whiteSpace=wrap;html=1;size=14;fillColor=#f5f5f5;'
        'strokeColor=#666666;align=left;verticalAlign=top;fontSize=11;')

EW, EH = 190, 50      # entity box
RW, RH = 150, 70      # relationship diamond


_PAGE_SEQ = [0]


class Page(object):
    def __init__(self, name):
        self.name = name
        self.cells = []
        self.n = 0
        _PAGE_SEQ[0] += 1
        self.idx = _PAGE_SEQ[0]

    def _id(self, key):
        return '%s_%s' % (self.name_id(), key)

    def name_id(self):
        return 'pg%d' % self.idx

    def box(self, key, label, x, y, style=E_STYLE, w=EW, h=EH):
        self.cells.append(
            '<mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
            '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/></mxCell>'
            % (self._id(key), escape(label), style, x, y, w, h))
        return key

    def entity(self, key, label, x, y, weak=False):
        return self.box(key, label, x, y, E_WEAK if weak else E_STYLE)

    def rel(self, key, label, x, y, ident=False):
        return self.box(key, label, x, y, R_IDENT if ident else R_STYLE, RW, RH)

    def note(self, text, x, y, w=300, h=120):
        self.n += 1
        return self.box('note%d' % self.n, text, x, y, NOTE, w, h)

    def link(self, a, b, label='', style=L_STYLE):
        self.n += 1
        self.cells.append(
            '<mxCell id="%s_e%d" value="%s" style="%s" edge="1" parent="1" '
            'source="%s" target="%s"><mxGeometry relative="1" as="geometry"/></mxCell>'
            % (self._id('l'), self.n, escape(label), style,
               self._id(a), self._id(b)))

    def arrow(self, a, b, label=''):
        self.link(a, b, label, A_STYLE)

    def xml(self):
        return ('<diagram name="%s" id="%s"><mxGraphModel dx="1400" dy="900" '
                'grid="0" gridSize="10" guides="1" tooltips="1" connect="1" '
                'arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" '
                'pageHeight="1100" math="0" shadow="0"><root>'
                '<mxCell id="%s_0"/><mxCell id="%s_1" parent="%s_0"/>%s'
                '</root></mxGraphModel></diagram>'
                % (escape(self.name), self.name_id(), self.name_id(),
                   self.name_id(), self.name_id(), ''.join(self.cells))
                ).replace('parent="1"', 'parent="%s_1"' % self.name_id()) \
                 .replace('id="%s_' % self.name_id(), 'id="%s_' % self.name_id())


def fix_parent(p):
    # parent="1" đã được thay ở xml(); nhưng id root phải khớp
    return p.xml()


pages = []

# ---------------------------------------------------------------- Page 0
p = Page('0. Overview - Toan canh')
C = [40, 300, 560, 820, 1080, 1340]
R = [40, 180, 320, 460, 600, 740]
ent = {
    'role': ('Role', 0, 0), 'user': ('System User', 1, 0),
    'cust': ('Customer', 3, 0), 'supp': ('Supplier', 4, 0),
    'meas': ('Measurement Standard', 5, 0),
    'pcat': ('Product Category', 0, 1), 'prod': ('Product', 1, 1),
    'draw': ('Technical Drawing', 2, 1), 'rfq': ('Quotation Request', 3, 1),
    'sprice': ('Supplier Price', 4, 1), 'uom': ('Unit of Measure', 5, 1),
    'tpl': ('BOM Template', 0, 2), 'bom': ('Bill of Materials', 1, 2),
    'rfql': ('Quotation Request Line', 3, 2), 'prule': ('Pricing Rule', 4, 2),
    'tparam': ('BOM Template Parameter', 0, 3), 'boml': ('BOM Material Line', 1, 3),
    'bomo': ('BOM Operation Line', 2, 3), 'quo': ('Quotation', 3, 3),
    'amx': ('Approval Matrix', 5, 3),
    'cplx': ('Complexity Level', 1, 4), 'mop': ('Manufacturing Operation', 2, 4),
    'quol': ('Quotation Line', 3, 4), 'pcomp': ('Price Component', 4, 4),
    'areq': ('Approval Request', 5, 4),
    'so': ('Sales Order', 3, 5), 'sol': ('Sales Order Line', 4, 5),
}
for k, (lbl, c, r) in ent.items():
    p.entity(k, lbl, C[c], R[r])
for a, b, lbl in [
    ('role', 'user', 'N:M grants'),
    ('cust', 'rfq', '1:N requests'),
    ('user', 'rfq', '1:N creates/receives'),
    ('rfq', 'rfql', '1:N contains'),
    ('rfql', 'prod', 'N:1 references'),
    ('rfql', 'bom', 'N:1 generates'),
    ('prod', 'pcat', 'N:1'),
    ('prod', 'uom', 'N:1'),
    ('prod', 'draw', '1:N'),
    ('prod', 'sprice', '1:N'),
    ('supp', 'sprice', '1:N issues'),
    ('pcat', 'tpl', '1:N'),
    ('tpl', 'tparam', '1:N contains'),
    ('tpl', 'bom', '1:N generates'),
    ('bom', 'prod', 'N:1 produces'),
    ('bom', 'draw', 'N:1'),
    ('bom', 'boml', '1:N contains'),
    ('bom', 'bomo', '1:N contains'),
    ('boml', 'prod', 'N:1 consumes'),
    ('boml', 'sprice', 'N:1 snapshot'),
    ('boml', 'cplx', 'N:1'),
    ('bomo', 'mop', 'N:1'),
    ('bomo', 'supp', 'N:1 outsource'),
    ('bomo', 'prule', 'N:1'),
    ('rfq', 'quo', '1:N converts'),
    ('cust', 'quo', '1:N'),
    ('quo', 'quol', '1:N contains'),
    ('quol', 'bom', 'N:1'),
    ('quol', 'pcomp', '1:N'),
    ('prule', 'quo', 'N:M snapshot'),
    ('prule', 'pcomp', '1:N'),
    ('quo', 'areq', '1:1 generates'),
    ('amx', 'areq', '1:N determines'),
    ('user', 'areq', '1:N approves'),
    ('prule', 'areq', '1:N'),
    ('quo', 'so', '1:1 converts'),
    ('cust', 'so', '1:N'),
    ('so', 'sol', '1:N contains'),
    ('sol', 'bom', 'N:1'),
    ('sol', 'prod', 'N:1'),
    ('meas', 'uom', 'N:1'),
]:
    p.link(a, b, lbl)
p.note('CONCEPTUAL ERD - DLM-ERP (Odoo 17)\n27 Business Entity, 6 Sub-ERD.\n'
       'Trang nay: toan canh quan he giua cac thuc the (khong ve thuoc tinh).\n'
       'Cac trang sau dung ky phap Chen: hinh chu nhat = Entity,\n'
       'hinh thoi = Relationship, nhan 1/N/M = ban so.\n'
       'Khung doi net = thuc the yeu (weak entity).',
       C[5] - 60, R[5], 420, 130)
pages.append(p)


def chen(page, entities, rels, links, notes=()):
    for k, lbl, x, y, weak in entities:
        page.entity(k, lbl, x, y, weak)
    for k, lbl, x, y, ident in rels:
        page.rel(k, lbl, x, y, ident)
    for a, b, lbl in links:
        page.link(a, b, lbl)
    for t, x, y, w, h in notes:
        page.note(t, x, y, w, h)


# ---------------------------------------------------------------- Page 1
p = Page('1. Sub-ERD - Doi tac & Nguoi dung')
chen(p,
     [('cust', 'CUSTOMER', 80, 60, False),
      ('supp', 'SUPPLIER', 80, 420, False),
      ('user', 'SYSTEM USER', 900, 60, False),
      ('role', 'ROLE', 1300, 60, False),
      ('rfq', 'QUOTATION REQUEST', 520, 240, False),
      ('quo', 'QUOTATION', 900, 400, False),
      ('so', 'SALES ORDER', 900, 560, False),
      ('sprice', 'SUPPLIER PRICE', 520, 560, False),
      ('bomo', 'BOM OPERATION LINE', 520, 700, False),
      ('prule', 'PRICING RULE', 80, 700, False)],
     [('r1', 'requests', 240, 150, False),
      ('r2', 'plays dual role', 240, 260, False),
      ('r3', 'issues', 240, 480, False),
      ('r4', 'outsourced to', 240, 620, False),
      ('r5', 'has role', 1130, 65, False),
      ('r6', 'creates /\nreceives', 760, 150, False),
      ('r7', 'receives', 760, 320, False),
      ('r8', 'issues', 760, 480, False),
      ('r9', 'applies to\ncustomer group', 240, 60, False)],
     [('cust', 'r1', '1'), ('r1', 'rfq', 'N'),
      ('cust', 'r2', '0..1'), ('r2', 'supp', '0..1'),
      ('supp', 'r3', '1'), ('r3', 'sprice', 'N'),
      ('supp', 'r4', '1'), ('r4', 'bomo', 'N'),
      ('user', 'r5', 'M'), ('r5', 'role', 'N'),
      ('rfq', 'r6', 'N'), ('r6', 'user', '1'),
      ('cust', 'r7', '1'), ('r7', 'quo', 'N'),
      ('cust', 'r8', '1'), ('r8', 'so', 'N'),
      ('prule', 'r9', 'N'), ('r9', 'cust', 'M')],
     [('Ghi chu: Customer va Supplier cung xuat phat tu res.partner\n'
       '(phan biet boi partner_role). Mot phap nhan co the giu ca hai vai tro\n'
       '=> quan he 1:1 tuy chon "plays dual role".\n'
       'Role gop res.groups + dl.rbac.feature + dl.rbac.operation.',
       1080, 620, 440, 140)])
pages.append(p)

# ---------------------------------------------------------------- Page 2
p = Page('2. Sub-ERD - Danh muc San pham')
chen(p,
     [('pcat', 'PRODUCT CATEGORY', 80, 320, False),
      ('prod', 'PRODUCT', 640, 320, False),
      ('uom', 'UNIT OF MEASURE', 1240, 320, False),
      ('sprice', 'SUPPLIER PRICE', 640, 720, False),
      ('supp', 'SUPPLIER', 80, 720, False),
      ('user', 'SYSTEM USER', 1240, 720, False),
      ('draw', 'TECHNICAL DRAWING', 640, 60, True),
      ('meas', 'MEASUREMENT STANDARD', 1240, 60, False)],
     [('r1', 'belongs to', 380, 315, False),
      ('r2', 'measured in', 990, 315, False),
      ('r3', 'sub-category of', 80, 480, False),
      ('r4', 'scrap /\nmain material', 640, 480, False),
      ('r5', 'has version', 640, 180, True),
      ('r6', 'quoted for', 640, 560, False),
      ('r7', 'issues', 380, 730, False),
      ('r8', 'approves /\napplies', 990, 730, False),
      ('r9', 'priced in', 990, 560, False),
      ('r10', 'formula uom', 1240, 180, False)],
     [('prod', 'r1', 'N'), ('r1', 'pcat', '1'),
      ('prod', 'r2', 'N'), ('r2', 'uom', '1'),
      ('pcat', 'r3', '1/N'),
      ('prod', 'r4', '1/N'),
      ('prod', 'r5', '1'), ('r5', 'draw', 'N'),
      ('prod', 'r6', '1'), ('r6', 'sprice', 'N'),
      ('supp', 'r7', '1'), ('r7', 'sprice', 'N'),
      ('sprice', 'r8', 'N'), ('r8', 'user', '1'),
      ('sprice', 'r9', 'N'), ('r9', 'uom', '1'),
      ('meas', 'r10', 'N'), ('r10', 'uom', '1')],
     [('Ghi chu:\n- PRODUCT gop 4 product_kind: Gia cong / Thuong mai / Vat tu / Ban thanh pham.\n'
       '- TECHNICAL DRAWING la thuc te yeu: dinh danh boi (Product, version).\n'
       '- Rang buoc: moi Product co toi da MOT Supplier Price dang ap dung (is_applied).\n'
       '- Quan he de quy tren PRODUCT: vat lieu chinh & san pham phe lieu thu hoi.\n'
       '- MEASUREMENT STANDARD hien la danh muc tham chieu doc lap.',
       80, 60, 480, 170)])
pages.append(p)

# ---------------------------------------------------------------- Page 3
p = Page('3. Sub-ERD - Ky thuat: Dinh muc (BOM)')
chen(p,
     [('bom', 'BILL OF MATERIALS', 620, 300, False),
      ('prod', 'PRODUCT', 620, 60, False),
      ('draw', 'TECHNICAL DRAWING', 1180, 60, False),
      ('boml', 'BOM MATERIAL LINE', 200, 560, True),
      ('bomo', 'BOM OPERATION LINE', 1060, 560, True),
      ('cplx', 'COMPLEXITY LEVEL', 200, 860, False),
      ('mop', 'MANUFACTURING OPERATION', 1400, 860, False),
      ('supp', 'SUPPLIER', 1060, 860, False),
      ('sprice', 'SUPPLIER PRICE', 620, 860, False),
      ('uom', 'UNIT OF MEASURE', 620, 700, False),
      ('user', 'SYSTEM USER', 1400, 300, False)],
     [('r1', 'produces', 620, 170, False),
      ('r2', 'references\ndrawing', 900, 170, False),
      ('r3', 'contains', 380, 420, True),
      ('r4', 'contains', 880, 420, True),
      ('r5', 'consumes', 380, 700, False),
      ('r6', 'complexity', 200, 720, False),
      ('r7', 'snapshot price', 380, 860, False),
      ('r8', 'measured in', 200, 640, False),
      ('r9', 'operation type', 1400, 700, False),
      ('r10', 'outsourced to', 1060, 700, False),
      ('r11', 'passes through', 640, 560, False),
      ('r12', 'creates /\nconfirms', 1400, 420, False),
      ('r13', 'sub-BOM\n(BTP)', 380, 300, False)],
     [('bom', 'r1', 'N'), ('r1', 'prod', '1'),
      ('bom', 'r2', 'N'), ('r2', 'draw', '1'),
      ('bom', 'r3', '1'), ('r3', 'boml', 'N'),
      ('bom', 'r4', '1'), ('r4', 'bomo', 'N'),
      ('boml', 'r5', 'N'), ('r5', 'prod', '1'),
      ('boml', 'r6', 'N'), ('r6', 'cplx', '1'),
      ('boml', 'r7', 'N'), ('r7', 'sprice', '1'),
      ('boml', 'r8', 'N'), ('r8', 'uom', '1'),
      ('bomo', 'r9', 'N'), ('r9', 'mop', '1'),
      ('bomo', 'r10', 'N'), ('r10', 'supp', '1'),
      ('boml', 'r11', 'M'), ('r11', 'bomo', 'N'),
      ('bom', 'r12', 'N'), ('r12', 'user', '1'),
      ('bom', 'r13', '1/N')],
     [('Ghi chu:\n- BOM MATERIAL LINE / BOM OPERATION LINE la thuc the yeu, dinh danh theo BOM cha.\n'
       '- BOM de quy: BOM cha tieu thu ban thanh pham von co BOM rieng.\n'
       '- Quan he M:N "passes through" giua dong vat tu va cong doan\n'
       '  dung cho cach tinh chi phi theo % gia tri vat lieu da chon.\n'
       '- Chi BOM trang thai Da xac nhan / Da khoa moi duoc dung de bao gia.',
       80, 60, 480, 170)])
pages.append(p)

# ---------------------------------------------------------------- Page 4
p = Page('4. Sub-ERD - Dinh muc mau (BOM Template)')
chen(p,
     [('pcat', 'PRODUCT CATEGORY', 100, 300, False),
      ('tpl', 'BOM TEMPLATE', 640, 300, False),
      ('tparam', 'BOM TEMPLATE PARAMETER', 1160, 300, True),
      ('tline', 'BOM MATERIAL LINE\n(dong mau)', 640, 640, True),
      ('bom', 'BILL OF MATERIALS', 640, 60, False),
      ('prod', 'PRODUCT\n(dai dien ho SP)', 100, 60, False)],
     [('r1', 'has template', 380, 295, False),
      ('r2', 'declares', 940, 295, True),
      ('r3', 'contains', 640, 470, True),
      ('r4', 'maps to', 1160, 470, False),
      ('r5', 'generates', 640, 170, False),
      ('r6', 'represented by', 380, 65, False)],
     [('pcat', 'r1', '1'), ('r1', 'tpl', 'N'),
      ('tpl', 'r2', '1'), ('r2', 'tparam', 'N'),
      ('tpl', 'r3', '1'), ('r3', 'tline', 'N'),
      ('tparam', 'r4', 'M'), ('r4', 'tline', 'N'),
      ('tpl', 'r5', '1'), ('r5', 'bom', 'N'),
      ('tpl', 'r6', 'N'), ('r6', 'prod', '1')],
     [('Ghi chu:\n- BOM Template neo vao PRODUCT CATEGORY, dung chung cho ca ho san pham.\n'
       '- Tham so (Dai/Rong/Cao/Do day/Canh) anh xa vao kich thuoc & so luong\n'
       '  cua tung dong vat tu mau qua he so nhan + so cong them (M:N co thuoc tinh).\n'
       '- Nho do sinh duoc BOM cu the cho tung co ma khong phai tao ma SP moi.',
       1080, 640, 450, 160)])
pages.append(p)

# ---------------------------------------------------------------- Page 5
p = Page('5. Sub-ERD - Ban hang: RFQ -> Bao gia -> Don hang')
chen(p,
     [('cust', 'CUSTOMER', 80, 60, False),
      ('rfq', 'QUOTATION REQUEST', 80, 300, False),
      ('rfql', 'QUOTATION REQUEST LINE', 80, 620, True),
      ('quo', 'QUOTATION', 700, 300, False),
      ('quol', 'QUOTATION LINE', 700, 620, True),
      ('pcomp', 'PRICE COMPONENT', 700, 900, True),
      ('so', 'SALES ORDER', 1300, 300, False),
      ('sol', 'SALES ORDER LINE', 1300, 620, True),
      ('prod', 'PRODUCT', 380, 900, False),
      ('bom', 'BILL OF MATERIALS', 1300, 900, False),
      ('user', 'SYSTEM USER', 1300, 60, False)],
     [('r1', 'requests', 80, 170, False),
      ('r2', 'contains', 80, 470, True),
      ('r3', 'converts to', 400, 305, False),
      ('r4', 'contains', 700, 470, True),
      ('r5', 'converts to', 1000, 305, False),
      ('r6', 'contains', 1300, 470, True),
      ('r7', 'decomposed into', 700, 770, True),
      ('r8', 'line from', 400, 625, False),
      ('r9', 'quotes', 380, 770, False),
      ('r10', 'orders', 1000, 770, False),
      ('r11', 'revision of', 700, 170, False),
      ('r12', 'created /\napproved by', 1000, 65, False),
      ('r13', 'costed from', 1000, 900, False)],
     [('cust', 'r1', '1'), ('r1', 'rfq', 'N'),
      ('rfq', 'r2', '1'), ('r2', 'rfql', 'N'),
      ('rfq', 'r3', '1'), ('r3', 'quo', 'N'),
      ('quo', 'r4', '1'), ('r4', 'quol', 'N'),
      ('quo', 'r5', '1'), ('r5', 'so', '1'),
      ('so', 'r6', '1'), ('r6', 'sol', 'N'),
      ('quol', 'r7', '1'), ('r7', 'pcomp', 'N'),
      ('rfql', 'r8', '1'), ('r8', 'quol', 'N'),
      ('quol', 'r9', 'N'), ('r9', 'prod', '1'),
      ('sol', 'r10', 'N'), ('r10', 'prod', '1'),
      ('quo', 'r11', '1/N'),
      ('quo', 'r12', 'N'), ('r12', 'user', '1'),
      ('quol', 'r13', 'N'), ('r13', 'bom', '1'),
      ('sol', 'r13', 'N')],
     [('Ghi chu:\n- RFQ la dau vao DUY NHAT de sinh bao gia.\n'
       '- Quotation tu tham chieu: ban goc va cac ban lap lai (revision).\n'
       '- PRICE COMPONENT la snapshot tung khoan cau thanh gia\n'
       '  => truy vet "vi sao ra gia nay" du cau hinh gia doi ve sau.\n'
       '- Sales Order Line giu bom_version lam can cu san xuat/doi chieu.',
       80, 900, 250, 170)])
pages.append(p)

# ---------------------------------------------------------------- Page 6
p = Page('6. Sub-ERD - Cau hinh gia & Phe duyet')
chen(p,
     [('prule', 'PRICING RULE', 100, 300, False),
      ('quo', 'QUOTATION', 700, 60, False),
      ('areq', 'APPROVAL REQUEST', 700, 420, False),
      ('amx', 'APPROVAL MATRIX', 700, 760, False),
      ('user', 'SYSTEM USER', 1300, 420, False),
      ('pcomp', 'PRICE COMPONENT', 100, 620, False),
      ('mop', 'MANUFACTURING OPERATION', 100, 60, False),
      ('pcat', 'PRODUCT CATEGORY', 1300, 60, False),
      ('prod', 'PRODUCT', 1300, 760, False)],
     [('r1', 'applied to', 400, 170, False),
      ('r2', 'generates', 700, 240, False),
      ('r3', 'triggers', 400, 430, False),
      ('r4', 'determines level', 700, 600, False),
      ('r5', 'requested /\napproved by', 1000, 425, False),
      ('r6', 'default approver', 1000, 765, False),
      ('r7', 'produces', 100, 470, False),
      ('r8', 'unit price of', 100, 170, False),
      ('r9', 'waste rate for', 400, 620, False)],
     [('prule', 'r1', 'N'), ('r1', 'quo', 'M'),
      ('quo', 'r2', '1'), ('r2', 'areq', '1'),
      ('prule', 'r3', '1'), ('r3', 'areq', 'N'),
      ('amx', 'r4', '1'), ('r4', 'areq', 'N'),
      ('areq', 'r5', 'N'), ('r5', 'user', '1'),
      ('amx', 'r6', 'N'), ('r6', 'user', '1'),
      ('prule', 'r7', '1'), ('r7', 'pcomp', 'N'),
      ('prule', 'r8', 'N'), ('r8', 'mop', '1'),
      ('prule', 'r9', 'N'), ('r9', 'prod', '1'),
      ('r9', 'pcat', '1')],
     [('Ghi chu:\n- PRICING RULE gop 6 ho quy tac dung chung khung phien ban:\n'
       '  loi nhuan & gia san / chiet khau / chi phi dieu chinh /\n'
       '  don gia cong doan / hao hut & thu hoi / VAT & lam tron.\n'
       '- Quy tac da chot vao bao gia (used_in_snapshot) thi khoa, khong sua.\n'
       '- Approval Request phat sinh khi: vuot nguong tien, duoi gia san,\n'
       '  chiet khau vuot tran, hoac thay doi cau hinh thuong mai.',
       1180, 140, 400, 200)])
pages.append(p)

xml = ('<mxfile host="app.diagrams.net" modified="2026-08-09T00:00:00.000Z" '
       'agent="dlm-erp" version="24.0.0" type="device">'
       + ''.join(fix_parent(pg) for pg in pages) + '</mxfile>')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(xml)
print('WROTE', os.path.abspath(OUT), len(xml), 'bytes,', len(pages), 'pages')
