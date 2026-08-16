# -*- coding: utf-8 -*-
"""Sub-ERD D — Sales: RFQ → Quotation → Order (E17–E23). Nguồn: §2 Group D, §4.5."""
from erd_lib import Page, LEGEND_TEXT, E_SOFT, E_ATTR


def build():
    p = Page(4, 'D. Ban hang - RFQ, Bao gia, Don hang', 2600, 1980)
    p.title('Sub-ERD D &#8212; Sales: Quotation Request &#8594; Quotation &#8594; '
            'Sales Order',
            'S&#7903; h&#7919;u: QUOTATION_REQUEST(+LINE) &#183; QUOTATION(+LINE) &#183; '
            'PRICE_COMPONENT &#183; SALES_ORDER(+LINE) &#160;&#8212;&#160; '
            'entity bi&#234;n: CUSTOMER &#183; COMPANY &#183; USER &#183; '
            'PRODUCT_CATEGORY &#183; ITEM + l&#7899;p con &#183; BOM &#183; '
            'SUPPLIER_PRICE_LIST')

    # ============================================ ba chứng từ + ba dòng
    p.entity('qr', 'QUOTATION REQUEST', 400, 520)
    p.entity('quo', 'QUOTATION', 1100, 520)
    p.entity('so', 'SALES ORDER', 1800, 520)
    p.entity('qrl', 'QUOTATION REQUEST LINE', 400, 850, kind='weak')
    p.entity('quol', 'QUOTATION LINE', 1100, 850, kind='weak')
    p.entity('sol', 'SALES ORDER LINE', 1800, 850, kind='weak')

    p.rel('r_cont_r', 'contains', 435, 690, ident=True)
    p.link('qr', 'r_cont_r', '1')
    p.link('r_cont_r', 'qrl', 'N', total=True)

    p.rel('r_cont_q', 'contains', 1135, 690, ident=True)
    p.link('quo', 'r_cont_q', '1')
    p.link('r_cont_q', 'quol', 'N', total=True)

    p.rel('r_cont_o', 'contains', 1835, 690, ident=True)
    p.link('so', 'r_cont_o', '1')
    p.link('r_cont_o', 'sol', 'N', total=True)

    p.rel('r_gen', 'generates', 750, 512)
    p.link('qr', 'r_gen', '1')
    p.link('r_gen', 'quo', 'N')

    p.rel('r_conv', 'converts', 1450, 512)
    p.link('quo', 'r_conv', '1')
    p.link('r_conv', 'so', '1')

    p.rel('r_gen_l', 'generates', 750, 842)
    p.link('qrl', 'r_gen_l', '1')
    p.link('r_gen_l', 'quol', '1')

    p.rel('r_conv_l', 'converts', 1450, 842)
    p.link('quol', 'r_conv_l', '1')
    p.link('r_conv_l', 'sol', '1')

    # ============================================ băng trên: người & khách
    p.entity('user', 'USER', 60, 120, kind='ext')
    p.rel('r_handles', 'creates_and_handles', 95, 300)
    p.link('user', 'r_handles', '1')
    p.link('r_handles', 'qr', 'N', entry=('0', '0.5'),
           pts=[(165, 549)])

    p.entity('cust', 'CUSTOMER', 400, 120, kind='ext')
    p.rel('r_req', 'requests', 435, 300)
    p.link('cust', 'r_req', '1')
    p.link('r_req', 'qr', 'N', total=True)

    p.rel('r_recv', 'receives', 1350, 300)
    p.link('cust', 'r_recv', '1', exit_=('1', '0.3'), pts=[(1420, 137)])
    p.link('r_recv', 'quo', 'N', total=True)

    p.rel('r_orders', 'orders', 1835, 300)
    p.link('cust', 'r_orders', '1', exit_=('1', '0.7'), pts=[(1905, 161)])
    p.link('r_orders', 'so', 'N', total=True)

    p.rel('r_super', 'supersedes', 1135, 300)
    p.link('quo', 'r_super', '1', exit_=('0.2', '0'))
    p.link('r_super', 'quo', 'N', entry=('0', '0.3'),
           pts=[(1060, 337), (1060, 537)])

    # ============================================ băng giữa: công ty
    p.entity('company', 'COMPANY', 1520, 610, kind='ext')
    p.rel('r_iss_q', 'issues', 1350, 602)
    p.link('company', 'r_iss_q', '1')
    p.link('r_iss_q', 'quo', 'N', entry=('1', '0.7'))

    p.rel('r_iss_o', 'issues', 1740, 602)
    p.link('company', 'r_iss_o', '1')
    p.link('r_iss_o', 'so', 'N', entry=('0', '0.7'))

    # ============================================ băng dưới: master data
    p.entity('pcat', 'PRODUCT CATEGORY', 60, 1150, kind='ext')
    p.rel('r_classif', 'classified_by', 95, 1000)
    p.link('qrl', 'r_classif', 'N', exit_=('0', '0.8'), pts=[(165, 896)])
    p.link('r_classif', 'pcat', '1')

    p.entity('mp', 'MANUFACTURED\nPRODUCT', 300, 1150, kind='ext')
    p.rel('r_resolves', 'resolves', 330, 1000)
    p.link('qrl', 'r_resolves', 'N', exit_=('0.1', '1'))
    p.link('r_resolves', 'mp', '1')

    p.entity('tp', 'TRADING PRODUCT', 540, 1150, kind='ext')
    p.rel('r_ref_tp', 'references', 540, 1000)
    p.link('qrl', 'r_ref_tp', 'N', exit_=('0.6', '1'))
    p.link('r_ref_tp', 'tp', '1')

    p.entity('bom', 'BILL OF MATERIALS', 900, 1300, kind='ext')
    p.rel('r_ref_bom', 'references', 700, 1000)
    p.link('qrl', 'r_ref_bom', 'N', exit_=('1', '0.7'))
    p.link('r_ref_bom', 'bom', '1')

    p.rel('r_stamp_q', 'stamps_version', 900, 1000)
    p.link('quol', 'r_stamp_q', 'N', exit_=('0', '0.8'))
    p.link('r_stamp_q', 'bom', '1')

    p.entity('item', 'ITEM', 1400, 1300, kind='ext')
    p.rel('r_quotes', 'quotes', 1350, 1000)
    p.link('quol', 'r_quotes', 'N', exit_=('1', '0.8'))
    p.link('r_quotes', 'item', '1')

    p.entity('pc', 'PRICE COMPONENT', 1100, 1150, kind='weak')
    p.rel('r_expl', 'explained_by', 1135, 1000, ident=True)
    p.link('quol', 'r_expl', '1')
    p.link('r_expl', 'pc', 'N', total=True)

    p.rel('r_refers', 'refers_to', 1350, 1150)
    p.link('pc', 'r_refers', 'N')
    p.link('r_refers', 'item', '1')

    p.entity('spl', 'SUPPLIER PRICE LIST', 600, 1450, kind='ext')
    p.rel('r_source', 'sourced_from', 700, 1230)
    p.edge('pc', 'r_source', 'N', style=E_SOFT)
    p.edge('r_source', 'spl', '1', style=E_SOFT)

    p.rel('r_sells', 'sells', 1620, 1000)
    p.link('sol', 'r_sells', 'N', exit_=('0.25', '1'))
    p.link('r_sells', 'item', '1')

    p.rel('r_stamp_o', 'stamps_version', 1620, 1150)
    p.link('sol', 'r_stamp_o', 'N', exit_=('0.5', '1'), pts=[(1905, 1187)])
    p.link('r_stamp_o', 'bom', '1')

    # ============================================ thuộc tính
    p.attrs('a_qr', 'QUOTATION REQUEST', [
        '<u>Request code</u> (RFQ-2026-0001)',
        'Customer &#183; Received date',
        'Deadline (&#8805; received date)',
        'Creator (Sales)',
        'Assignee &#183; Assignment date (Engineering)',
        'Return-for-supplement reason',
        'Request description',
        'Technical progress (<i>3 of 5 lines resolved</i>)',
        'Deadline status &#183; Days in queue',
    ], 620, 180, w=330)
    p.attach('qr', 'a_qr')

    p.attrs('a_quo', 'QUOTATION', [
        '<u>Quotation number</u> (BG/2026/0001-R2)',
        'Customer &#183; Quotation date',
        '<b>Pricing date</b> (freezes rules &amp; price lists)',
        'Validity date',
        'Revision number &#183; Previous quotation',
        'Discount rate &#183; VAT rate',
        'Five money layers (before &#8594; grand total)',
        'Total cost &#183; Floor price &#183; Actual markup',
        'Approval outcome (required &#183; level &#183; reason)',
        'Three approval triggers',
        'Payment / delivery / warranty terms',
        'Rejection reason &#183; Revision type &amp; note',
    ], 1560, 180, w=270)
    p.attach('quo', 'a_quo')

    p.attrs('a_so', 'SALES ORDER', [
        '<u>Order number</u> (DH/2026/0001)',
        'Customer (<b>locked</b> once quotation attached)',
        'Source quotation (1&#8211;1)',
        'Order date (&#8805; quotation date)',
        'Discount &amp; VAT copied from the quotation',
        'Five money layers (copied)',
        'Notes',
        'Reset-to-draft audit trail',
    ], 2150, 460, w=330)
    p.attach('so', 'a_so')

    p.attrs('a_qrl', 'QUOTATION REQUEST LINE <i>(weak)</i>', [
        '<u>(RFQ, Product name)</u> &#8212; manufactured lines',
        'Line kind (Manufactured / Trading)',
        'Product name as the customer calls it',
        'Product category &#183; Reference product',
        'Quantity (&gt; 0)',
        'Dimension note (system parses L&#215;W&#215;H)',
        'Attachments',
        'Resolved product &#183; Referenced BOM',
        'Infeasibility verdict + mandatory reason',
        'Information request back to Sales',
        'Scored matching suggestion',
        'Missing-supplier-price warning',
    ], 40, 700, w=340)
    p.attach('qrl', 'a_qrl')

    p.attrs('a_quol', 'QUOTATION LINE <i>(weak)</i>', [
        '<u>(Quotation, Line sequence)</u>',
        'Description printed on the quotation',
        'Quantity &#183; Unit price &#183; Subtotal',
        'Line kind &#183; Item &#183; BOM used',
        '<b>Immutable BOM stamp</b> (version &#183; approver &#183; date)',
        '<i>Internal layer &#8212; pricing roles only:</i>',
        'Material / operation / overhead cost per unit',
        'Unit cost &#183; Floor price per unit',
    ], 1620, 1250, w=340)
    p.edge('quol', 'a_quol', '', E_ATTR,
           exit_=('1', '0.9'), entry=('0', '0.25'),
           pts=[(1600, 902), (1600, 1302)])

    p.attrs('a_sol', 'SALES ORDER LINE <i>(weak)</i>', [
        '<u>(Sales order, Line sequence)</u>',
        '1&#8211;1 with the source quotation line',
        'Committed description &#183; Quantity',
        'Committed unit price &#183; Subtotal',
        'Line kind &#183; Item',
        'BOM to be used for production',
        'BOM stamp (version &#183; approver &#183; date)',
    ], 2150, 780, w=330)
    p.attach('sol', 'a_sol')

    p.attrs('a_pc', 'PRICE COMPONENT <i>(weak)</i>', [
        '<u>(Quotation, Line, Component type, Source)</u>',
        'Component type &#8212; 10 kinds: trading base price,',
        '&#160;&#160;raw material, processed material, operation,',
        '&#160;&#160;setup fee, overhead, profit, discount, VAT,',
        '&#160;&#160;<b>scrap recovery</b> (<i>kho&#7843;n tr&#7915;</i>)',
        'Related item',
        '<b>Soft reference</b> to source (type &#183; number &#183; version)',
        'Quantity &#183; Unit price &#183; Rate',
        'Subtotal <i>(pricing roles only)</i>',
        'Discount-excluded flag',
    ], 1150, 1450, w=340)
    p.attach('pc', 'a_pc')

    # ============================================ ghi chú
    p.note('<b>Snapshot &#8212; ch&#7889;t s&#7889; (&#167;0.3)</b><br/>'
           'PRICE_COMPONENT tr&#7887; v&#7873; ngu&#7891;n b&#7857;ng '
           '<b>tham chi&#7871;u m&#7873;m</b> (lo&#7841;i + s&#7889; hi&#7879;u + '
           'phi&#234;n b&#7843;n), <b>c&#7889; &#253; kh&#244;ng c&#243; kho&#225; '
           'ngo&#7841;i</b> &#8658; v&#7869; b&#7857;ng &#273;&#432;&#7901;ng ch&#7845;m. '
           'D&#249; b&#7843;ng gi&#225; NCC hay c&#7845;u h&#236;nh gi&#225; ngu&#7891;n '
           'b&#7883; s&#7917;a/xo&#225;, b&#225;o gi&#225; &#273;&#227; ph&#225;t '
           'h&#224;nh v&#7851;n nguy&#234;n v&#7865;n.',
           700, 1560, w=430, h=175)

    p.note('<b>R&#224;ng bu&#7897;c nghi&#7879;p v&#7909; ch&#237;nh</b><br/>'
           '&#8226; M&#7897;t RFQ c&#243; <b>t&#7889;i &#273;a M&#7852;T</b> '
           'b&#225;o gi&#225; ch&#432;a &#273;&#243;ng (Cancelled &#183; Superseded &#183; '
           'Expired &#183; Rejected l&#224; tr&#7841;ng th&#225;i &#273;&#243;ng).<br/>'
           '&#8226; B&#225;o gi&#225; &#8594; &#272;&#417;n h&#224;ng l&#224; <b>1&#8211;1</b>; '
           'b&#225;o gi&#225; ngu&#7891;n kh&#244;ng xo&#225; &#273;&#432;&#7907;c khi '
           '&#273;&#417;n c&#242;n t&#7891;n t&#7841;i.<br/>'
           '&#8226; M&#7897;t d&#242;ng b&#225;o gi&#225; truy ng&#432;&#7907;c '
           '<b>1&#8211;1</b> v&#7873; &#273;&#250;ng m&#7897;t d&#242;ng RFQ.<br/>'
           '&#8226; Ch&#7889;t &#273;&#417;n &#8658; n&#226;ng s&#7843;n ph&#7849;m '
           'Nh&#225;p l&#234;n ch&#237;nh th&#7913;c, <b>kho&#225; BOM</b>, '
           'c&#7853;p nh&#7853;t nh&#243;m kh&#225;ch h&#224;ng.',
           1180, 1650, w=440, h=190)

    p.legend(LEGEND_TEXT, 60, 1560, w=560, h=340)
    return p
