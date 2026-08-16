# -*- coding: utf-8 -*-
"""Overview — toàn cảnh chuỗi giá trị (superset, không attribute). Nguồn: §4.1."""
from erd_lib import Page, LEGEND_TEXT


def build():
    p = Page(0, 'Overview - Toan canh chuoi gia tri', 3600, 2350)
    p.title('Conceptual ERD &#8212; Overview: to&#224;n c&#7843;nh chu&#7895;i '
            'gi&#225; tr&#7883; DLM-ERP',
            'Superset c&#7911;a 5 sub-ERD A&#8211;E &#8212; <b>ch&#7881; t&#234;n '
            'th&#7921;c th&#7875; v&#224; quan h&#7879; ch&#237;nh, '
            'kh&#244;ng v&#7869; thu&#7897;c t&#237;nh</b> (quy &#432;&#7899;c '
            '&#167;4.0-3). Thu&#7897;c t&#237;nh &#273;&#7847;y &#273;&#7911; xem '
            '&#7903; sub-ERD ch&#7911; s&#7903; h&#7919;u.')

    # ============================================================ Đối tác
    p.entity('partner', 'PARTNER', 330, 150)
    p.isa('isa_p', 412, 252, disjoint=False)
    p.entity('supp', 'SUPPLIER /\nSUBCONTRACTOR', 100, 340, kind='sub')
    p.entity('cust', 'CUSTOMER', 620, 340, kind='sub')
    p.isa_link('partner', 'isa_p', ['supp', 'cust'], total=False)

    # ============================================================ chứng từ bán hàng
    p.entity('qr', 'QUOTATION REQUEST', 1360, 340)
    p.entity('quo', 'QUOTATION', 2060, 340)
    p.entity('so', 'SALES ORDER', 2760, 340)

    p.rel('r_req', 'requests', 1030, 332)
    p.link('cust', 'r_req', '1')
    p.link('r_req', 'qr', 'N', total=True)

    p.rel('r_gen', 'generates', 1710, 332)
    p.link('qr', 'r_gen', '1')
    p.link('r_gen', 'quo', 'N')

    p.rel('r_conv', 'converts', 2410, 332)
    p.link('quo', 'r_conv', '1')
    p.link('r_conv', 'so', '1')

    p.rel('r_recv', 'receives', 1710, 160)
    p.link('cust', 'r_recv', '1', exit_=('0.8', '0'), pts=[(788, 197)])
    p.link('r_recv', 'quo', 'N', total=True, entry=('0', '0.3'))

    p.rel('r_orders', 'orders', 2795, 160)
    p.link('cust', 'r_orders', '1', exit_=('0.6', '0'), pts=[(746, 120)],
           entry=('0.5', '0'))
    p.link('r_orders', 'so', 'N', total=True)

    p.rel('r_super', 'supersedes', 2095, 140)
    p.link('quo', 'r_super', '1', exit_=('0.3', '0'))
    p.link('r_super', 'quo', 'N', entry=('0.7', '0'))

    # ============================================================ phê duyệt
    p.entity('areq', 'APPROVAL REQUEST', 3230, 100)
    p.rel('r_ask', 'requests', 3230, 250)
    p.link('quo', 'r_ask', '1', exit_=('0.9', '0'),
           pts=[(2249, 287)], entry=('0', '0.5'))
    p.link('r_ask', 'areq', 'N', exit_=('0.5', '0'))

    # ============================================================ dòng chứng từ
    p.entity('qrl', 'QUOTATION REQUEST LINE', 1360, 660, kind='weak')
    p.entity('quol', 'QUOTATION LINE', 2060, 660, kind='weak')
    p.entity('sol', 'SALES ORDER LINE', 2760, 660, kind='weak')

    p.rel('r_cont_r', 'contains', 1395, 500, ident=True)
    p.link('qr', 'r_cont_r', '1')
    p.link('r_cont_r', 'qrl', 'N', total=True)

    p.rel('r_cont_q', 'contains', 2095, 500, ident=True)
    p.link('quo', 'r_cont_q', '1')
    p.link('r_cont_q', 'quol', 'N', total=True)

    p.rel('r_cont_o', 'contains', 2795, 500, ident=True)
    p.link('so', 'r_cont_o', '1')
    p.link('r_cont_o', 'sol', 'N', total=True)

    p.rel('r_gen_l', 'generates', 1710, 652)
    p.link('qrl', 'r_gen_l', '1')
    p.link('r_gen_l', 'quol', '1')

    p.rel('r_conv_l', 'converts', 2410, 652)
    p.link('quol', 'r_conv_l', '1')
    p.link('r_conv_l', 'sol', '1')

    # ============================================================ cấu phần giá
    p.entity('pc', 'PRICE COMPONENT', 2620, 1010, kind='weak')
    p.rel('r_expl', 'contains', 2500, 820, ident=True)
    p.link('quol', 'r_expl', '1', exit_=('1', '0.9'), entry=('0', '0.3'))
    p.link('r_expl', 'pc', 'N', total=True, entry=('0.5', '0'))

    # ============================================================ bảng giá NCC
    p.entity('spl', 'SUPPLIER PRICE LIST', 100, 700)
    p.entity('item', 'ITEM', 100, 1010)

    p.rel('r_issues', 'issues', 135, 520)
    p.link('supp', 'r_issues', '1')
    p.link('r_issues', 'spl', 'N', total=True)

    p.rel('r_priced', 'priced_by', 135, 830)
    p.link('spl', 'r_priced', 'N', total=True)
    p.link('r_priced', 'item', '1')

    # ============================================================ sản phẩm & BOM
    p.entity('tp', 'TRADING PRODUCT', 820, 1010)
    p.entity('mp', 'MANUFACTURED\nPRODUCT', 1180, 1010)
    p.entity('bom', 'BILL OF MATERIALS', 1900, 1010)
    p.entity('td', 'TECHNICAL DRAWING', 820, 1370)

    p.rel('r_ref_tp', 'references', 890, 830)
    p.link('qrl', 'r_ref_tp', 'N', exit_=('0', '0.5'), entry=('1', '0.3'))
    p.link('r_ref_tp', 'tp', '1')

    p.rel('r_resolves', 'resolves', 1250, 830)
    p.link('qrl', 'r_resolves', 'N', exit_=('0', '0.8'), entry=('0.5', '0'))
    p.link('r_resolves', 'mp', '1')

    p.rel('r_ref_bom', 'references', 1690, 830)
    p.link('qrl', 'r_ref_bom', 'N', exit_=('1', '0.7'), entry=('0', '0.3'))
    p.link('r_ref_bom', 'bom', '1', entry=('0.5', '0'))

    p.rel('r_stamp_q', 'stamps_version', 2330, 830)
    p.link('quol', 'r_stamp_q', 'N', exit_=('1', '0.7'), entry=('0', '0.3'))
    p.link('r_stamp_q', 'bom', '1', entry=('1', '0.3'))

    p.rel('r_stamp_o', 'stamps_version', 2830, 830)
    p.link('sol', 'r_stamp_o', 'N', exit_=('0.35', '1'), entry=('0.5', '0'))
    p.link('r_stamp_o', 'bom', '1', entry=('1', '0.5'))

    p.rel('r_prod_mp', 'produced_by', 1575, 1002)
    p.link('mp', 'r_prod_mp', '1')
    p.link('r_prod_mp', 'bom', 'N', total=True)

    p.rel('r_doc', 'documented_by', 890, 1190)
    p.link('mp', 'r_doc', '1', exit_=('0', '0.5'), entry=('1', '0.3'))
    p.link('r_doc', 'td', 'N', total=True, entry=('0.5', '0'))

    # ============================================================ dòng của BOM
    p.entity('bml', 'BOM MATERIAL LINE', 1900, 1370, kind='weak')
    p.entity('bol', 'BOM OPERATION LINE', 2260, 1370, kind='weak')

    p.rel('r_has_bml', 'contains', 1970, 1190, ident=True)
    p.link('bom', 'r_has_bml', '1', exit_=('0.5', '1'))
    p.link('r_has_bml', 'bml', 'N', total=True)

    p.rel('r_has_bol', 'contains', 2330, 1190, ident=True)
    p.link('bom', 'r_has_bol', '1', exit_=('1', '0.7'), entry=('0', '0.5'))
    p.link('r_has_bol', 'bol', 'N', total=True, entry=('0.5', '0'))

    p.rel('r_outs', 'outsourced_to', 2610, 1362)
    p.link('bol', 'r_outs', 'N', exit_=('1', '0.5'), entry=('0', '0.5'))
    p.link('r_outs', 'supp', '1', exit_=('0.5', '0'), entry=('1', '0.5'),
           pts=[(2680, 1140), (565, 1140), (565, 369)])

    # ============================================================ vật tư đầu vào
    p.entity('pm', 'PROCESSED\nMATERIAL', 1540, 1730)
    p.entity('rm', 'RAW MATERIAL', 1900, 1730)

    p.rel('r_cons_rm', 'consumes', 1970, 1550)
    p.link('bml', 'r_cons_rm', 'N')
    p.link('r_cons_rm', 'rm', '1', total=True)

    p.rel('r_cons_pm', 'consumes', 1610, 1550)
    p.link('bml', 'r_cons_pm', 'N', exit_=('0', '0.5'), entry=('1', '0.3'))
    p.link('r_cons_pm', 'pm', '1', entry=('0.5', '0'))

    p.rel('r_prod_pm', 'produced_by', 1250, 1190)
    p.link('pm', 'r_prod_pm', '1', exit_=('0', '0.5'), entry=('0.5', '1'))
    p.link('r_prod_pm', 'bom', 'N', total=True, exit_=('1', '0.5'),
           entry=('0', '0.7'))

    # ============================================================ ghi chú
    p.note('<b>&#272;&#7885;c s&#417; &#273;&#7891; n&#224;y nh&#432; th&#7871; '
           'n&#224;o</b><br/>'
           'Ba b&#259;ng t&#7915; tr&#234;n xu&#7889;ng: <b>ch&#7913;ng t&#7915;</b> '
           '(RFQ &#8594; B&#225;o gi&#225; &#8594; &#272;&#417;n h&#224;ng) &#8212; '
           '<b>d&#242;ng ch&#7913;ng t&#7915;</b> (th&#7921;c th&#7875; y&#7871;u) &#8212; '
           '<b>d&#7919; li&#7879;u n&#7873;n</b> (m&#7863;t h&#224;ng, &#273;&#7883;nh '
           'm&#7913;c, v&#7853;t t&#432;).<br/>'
           'M&#7885;i quan h&#7879; &#7903; &#273;&#226;y &#273;&#7873;u '
           '&#273;&#432;&#7907;c v&#7869; l&#7841;i <b>&#273;&#7847;y &#273;&#7911; '
           'thu&#7897;c t&#237;nh</b> t&#7841;i sub-ERD ch&#7911; s&#7903; h&#7919;u '
           '(A&#8211;E).',
           700, 1900, w=440, h=175)

    p.note('<b>Nh&#7919;ng g&#236; c&#7889; &#253; KH&#212;NG v&#7869; &#7903; '
           '&#273;&#226;y</b><br/>'
           '&#8226; <b>Thu&#7897;c t&#237;nh</b> &#8212; xem sub-ERD ch&#7911; '
           's&#7903; h&#7919;u (quy &#432;&#7899;c &#167;4.0-3).<br/>'
           '&#8226; <b>Chuy&#234;n bi&#7879;t ho&#225; ITEM</b> (4 l&#7899;p con) '
           'v&#224; <b>BOM</b> (chu&#7849;n / theo &#273;&#417;n) &#8212; v&#7869; '
           '&#7903; sub-ERD B v&#224; C; &#7903; &#273;&#226;y c&#225;c l&#7899;p con '
           'xu&#7845;t hi&#7879;n tr&#7921;c ti&#7871;p cho g&#7885;n chu&#7895;i.<br/>'
           '&#8226; <b>C&#7845;u h&#236;nh gi&#225; &#183; Ma tr&#7853;n ph&#234; '
           'duy&#7879;t &#183; USER &#183; ROLE &#183; COMPANY &#183; UOM &#183; '
           'OPERATION &#183; PRODUCT_CATEGORY</b> &#8212; l&#224; d&#7919; li&#7879;u '
           'c&#7845;u h&#236;nh, v&#7869; &#7903; sub-ERD A / B / C / E.<br/>'
           '&#8226; <b>Thu h&#7891;i ph&#7871; li&#7879;u</b> &#8212; quan h&#7879; '
           '&#273;&#7879; quy <i>RAW_MATERIAL &#8594; ITEM</i> '
           '(<i>recovers_as_scrap</i>), v&#7869; &#7903; sub-ERD B; ti&#7873;n '
           'thu h&#7891;i n&#7857;m &#7903; C v&#224; D.<br/>'
           '&#8226; <b>Kho v&#224; S&#7843;n xu&#7845;t</b> (sub-ERD F, G) &#8212; '
           'ch&#432;a hi&#7879;n th&#7921;c (&#167;0.4).',
           1200, 1900, w=470, h=285)

    p.note('<b>Ba nguy&#234;n t&#7855;c xuy&#234;n su&#7889;t (&#167;0.3)</b><br/>'
           '&#8226; <b>Ch&#7889;t s&#7889; (snapshot)</b>: b&#225;o gi&#225; ph&#225;t '
           'h&#224;nh gi&#7919; nguy&#234;n s&#7889; li&#7879;u d&#249; d&#7919; '
           'li&#7879;u n&#7873;n &#273;&#7893;i sau &#273;&#243;.<br/>'
           '&#8226; <b>Phi&#234;n b&#7843;n (versioning)</b>: s&#7917;a b&#7843;n '
           'v&#7869; / &#273;&#7883;nh m&#7913;c / b&#225;o gi&#225; l&#224; '
           '<i>t&#7841;o phi&#234;n b&#7843;n m&#7899;i</i>, kh&#244;ng ghi '
           '&#273;&#232;.<br/>'
           '&#8226; <b>Ph&#226;n t&#7847;ng quy&#7873;n xem gi&#225; v&#7889;n</b>: '
           'l&#7899;p chi ph&#237; n&#7857;m tr&#234;n d&#242;ng b&#225;o gi&#225; '
           'v&#224; c&#7845;u ph&#7847;n gi&#225;, ch&#7881; vai tr&#242; &#273;&#7883;nh '
           'gi&#225; th&#7845;y.',
           1730, 1900, w=470, h=250)

    p.note('<b>&#272;i&#7875;m n&#7889;i d&#224;nh cho ph&#7841;m vi sau '
           '(&#167;4.9)</b><br/>'
           'SALES_ORDER_LINE &#8594; <i>Production Order</i> (G)<br/>'
           'BOM + hai lo&#7841;i d&#242;ng &#8594; <i>c&#244;ng th&#7913;c cho '
           'l&#7879;nh s&#7843;n xu&#7845;t</i> (G)<br/>'
           'ITEM &#183; UOM &#8594; <i>t&#7891;n kho</i> (F)<br/>'
           'SUPPLIER &#183; CUSTOMER &#183; SALES_ORDER &#8594; <i>nh&#7853;p mua, '
           'xu&#7845;t giao</i> (F)<br/>'
           'M&#7885;i seam &#273;&#7873;u tr&#7887; v&#7873; th&#7921;c th&#7875; '
           '&#273;&#227; ch&#7889;t &#8658; th&#234;m F/G <b>kh&#244;ng ph&#7843;i '
           'v&#7869; l&#7841;i</b> A&#8211;E.',
           2260, 1900, w=470, h=220)

    p.legend(LEGEND_TEXT, 60, 1900, w=560, h=340)
    return p
