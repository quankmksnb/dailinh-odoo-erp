# -*- coding: utf-8 -*-
"""Sub-ERD C — Engineering: Drawings & BOM (E12–E16). Nguồn: §2 Group C, §4.4."""
from erd_lib import Page, LEGEND_TEXT


def build():
    p = Page(3, 'C. Ky thuat - Ban ve & Dinh muc (BOM)', 2120, 1700)
    p.title('Sub-ERD C &#8212; Engineering: Technical Drawings &amp; Bill of Materials',
            'S&#7903; h&#7919;u: TECHNICAL_DRAWING &#183; BOM &#183; BOM_MATERIAL_LINE '
            '&#183; BOM_OPERATION_LINE &#183; OPERATION &#160;&#8212;&#160; '
            'entity bi&#234;n: MANUFACTURED_PRODUCT &#183; PROCESSED_MATERIAL &#183; '
            'RAW_MATERIAL &#183; UOM &#183; SUPPLIER &#183; USER')

    # ------------------------------------------------ đầu ra: sản phẩm
    p.entity('mp', 'MANUFACTURED\nPRODUCT', 60, 150, kind='ext')
    p.entity('pm', 'PROCESSED\nMATERIAL', 60, 560, kind='ext')
    p.entity('td', 'TECHNICAL DRAWING', 700, 150)
    p.entity('bom', 'BILL OF MATERIALS', 700, 560)

    p.rel('r_doc_mp', 'documented_by', 395, 142)
    p.link('mp', 'r_doc_mp', '1')
    p.link('r_doc_mp', 'td', 'N', total=True)

    p.rel('r_prod_mp', 'produced_by', 395, 282)
    p.link('mp', 'r_prod_mp', '1')
    p.link('r_prod_mp', 'bom', 'N', total=True)

    p.rel('r_doc_pm', 'documented_by', 395, 422)
    p.link('pm', 'r_doc_pm', '1')
    p.link('r_doc_pm', 'td', 'N', entry=('0', '0.75'))

    p.rel('r_prod_pm', 'produced_by', 395, 562)
    p.link('pm', 'r_prod_pm', '1')
    p.link('r_prod_pm', 'bom', 'N', total=True)

    p.rel('r_ref_dw', 'references', 735, 322)
    p.link('td', 'r_ref_dw', '1')
    p.link('r_ref_dw', 'bom', 'N')

    # ------------------------------------------------ phân lớp BOM
    p.isa('isa_bom', 1000, 566, disjoint=True)
    p.entity('bom_std', 'STANDARD BOM', 1150, 480, kind='sub')
    p.entity('bom_ord', 'ORDER-SPECIFIC BOM', 1150, 660, kind='sub')
    p.isa_link('bom', 'isa_bom', ['bom_std', 'bom_ord'], total=True)

    # ------------------------------------------------ người dùng
    p.entity('user', 'USER', 1400, 150, kind='ext')
    p.rel('r_creates', 'creates', 1150, 142)
    p.link('user', 'r_creates', '1')
    p.link('r_creates', 'td', 'N', total=True)

    p.rel('r_appr', 'approves', 1400, 320)
    p.link('user', 'r_appr', '1')
    p.link('r_appr', 'bom', 'N', entry=('0.6', '0'),
           pts=[(1470, 420), (826, 420)])

    # ------------------------------------------------ các dòng của BOM
    p.rel('r_has_bml', 'contains', 620, 760, ident=True)
    p.link('bom', 'r_has_bml', '1', exit_=('0.25', '1'))
    p.link('r_has_bml', 'bml', 'N', total=True)

    p.rel('r_has_bol', 'contains', 860, 760, ident=True)
    p.link('bom', 'r_has_bol', '1', exit_=('0.75', '1'))
    p.link('r_has_bol', 'bol', 'N', total=True)

    p.entity('bml', 'BOM MATERIAL LINE', 585, 900, kind='weak')
    p.entity('bol', 'BOM OPERATION LINE', 855, 900, kind='weak')

    p.rel('r_covers', 'covers', 700, 1040)
    p.link('bml', 'r_covers', 'M', exit_=('0.5', '1'))
    p.link('bol', 'r_covers', 'N', exit_=('0.5', '1'))

    # ------------------------------------------------ đầu vào của dòng vật tư
    p.entity('rm', 'RAW MATERIAL', 60, 900, kind='ext')
    p.rel('r_cons_rm', 'consumes', 300, 892)
    p.link('bml', 'r_cons_rm', 'N')
    p.link('r_cons_rm', 'rm', '1')

    p.rel('r_cons_pm', 'consumes', 300, 700)
    p.link('bml', 'r_cons_pm', 'N', entry=('0', '0.25'))
    p.link('r_cons_pm', 'pm', '1')

    p.entity('uom', 'UNIT OF MEASURE', 60, 1150, kind='ext')
    p.rel('r_conv', 'converts', 300, 1042)
    p.link('bml', 'r_conv', 'N', exit_=('0', '0.75'))
    p.link('r_conv', 'uom', '1')

    # ------------------------------------------------ đầu vào của dòng công đoạn
    p.entity('op', 'OPERATION', 1400, 900)
    p.rel('r_ref_op', 'references', 1150, 892)
    p.link('bol', 'r_ref_op', 'N')
    p.link('r_ref_op', 'op', '1', total=True)

    p.entity('supp', 'SUPPLIER /\nSUBCONTRACTOR', 1400, 1080, kind='ext')
    p.rel('r_outs', 'outsourced_to', 1150, 1042)
    p.link('bol', 'r_outs', 'N', exit_=('1', '0.75'))
    p.link('r_outs', 'supp', '1')

    # ------------------------------------------------ thuộc tính
    p.attrs('a_td', 'TECHNICAL DRAWING', [
        '<u>Drawing code</u> (DW-0001)',
        '<u>(Product, Version)</u> &#8212; unique',
        'Drawing name',
        'Product (manufactured / processed only)',
        'Version number',
        'Attachment file (required on confirm)',
        '<b>Current flag</b> (&#8804; 1 per product)',
        'Confirmation date &#183; Creator',
    ], 930, 230, w=310)
    p.attach('td', 'a_td')

    p.attrs('a_bom', 'BILL OF MATERIALS', [
        '<u>BOM code</u> (BOM-0001)',
        '<u>(Product, Version, BOM type)</u>',
        'Output product &#183; Output quantity (&gt; 0)',
        'BOM type &#8212; <i>discriminator</i>',
        'Version number',
        '<b>Current version flag</b> (standard only)',
        'Total material cost <i>(pricing roles only)</i>',
        'Approver &#183; Approval date',
        'RFQ-provisional flag &#183; Manufacturing notes',
    ], 1400, 480, w=320)
    p.attach('bom', 'a_bom')

    p.attrs('a_bml', 'BOM MATERIAL LINE <i>(weak)</i>', [
        '<u>(BOM, Material, Line sequence)</u>',
        'Consumed raw / processed material',
        'Dimensions used to derive the quantity',
        'Computed quantity (formula result)',
        'Actual quantity + override flag &amp; reason',
        'Waste rate (= base &#215; complexity)',
        'Quantity after waste',
        'Snapshotted unit price &#183; scrap value',
        'Line subtotal <i>(pricing roles only)</i>',
    ], 60, 1250, w=330)
    p.attach('bml', 'a_bml')

    p.attrs('a_bol', 'BOM OPERATION LINE <i>(weak)</i>', [
        '<u>(BOM, Operation, Line sequence)</u>',
        'Operation (from the catalogue)',
        'Pricing method (from effective rule)',
        'Base quantity per finished unit',
        'Material base scope (All / Selected)',
        'Outsourcing flag &#183; Subcontractor',
        'Has-price flag',
        'Estimated cost per unit <i>(indicative)</i>',
    ], 430, 1250, w=330)
    p.attach('bol', 'a_bol')

    p.attrs('a_op', 'OPERATION', [
        '<u>Operation code</u>',
        'Operation name &#183; Description',
        'Usage status (Active / Archived)',
    ], 1700, 880, w=300)
    p.attach('op', 'a_op')

    # ------------------------------------------------ ghi chú
    p.note('<b>BTP &#273;&#243;ng hai vai &#8658; &#273;&#7883;nh m&#7913;c '
           'nhi&#7873;u t&#7847;ng</b><br/>'
           'PROCESSED_MATERIAL v&#7915;a l&#224; <i>&#273;&#7847;u ra</i> c&#7911;a '
           'm&#7897;t BOM con (quan h&#7879; <i>produced_by</i>), v&#7915;a l&#224; '
           '<i>&#273;&#7847;u v&#224;o</i> tr&#234;n BOM_MATERIAL_LINE c&#7911;a BOM cha '
           '(quan h&#7879; <i>consumes</i>) &#8658; &#273;&#226;y ch&#237;nh l&#224; '
           'quan h&#7879; &#273;&#7879; quy t&#7841;o c&#7845;u tr&#250;c BOM '
           'nhi&#7873;u t&#7847;ng; gi&#225; v&#7889;n suy &#273;&#7879; quy '
           't&#7915; BOM con l&#234;n.',
           1400, 1250, w=420, h=170)

    p.note('<b>R&#224;ng bu&#7897;c tr&#234;n s&#417; &#273;&#7891;</b><br/>'
           '&#8226; M&#7895;i s&#7843;n ph&#7849;m c&#243; <b>t&#7889;i &#273;a m&#7897;t</b> '
           'BOM chu&#7849;n l&#224; <i>phi&#234;n b&#7843;n hi&#7879;n h&#224;nh</i>; '
           'BOM theo &#273;&#417;n <b>kh&#244;ng bao gi&#7901;</b> l&#224; hi&#7879;n h&#224;nh.<br/>'
           '&#8226; M&#7895;i s&#7843;n ph&#7849;m c&#243; <b>t&#7889;i &#273;a m&#7897;t</b> '
           'b&#7843;n v&#7869; <i>hi&#7879;n h&#224;nh</i>.<br/>'
           '&#8226; BOM &#273;&#227; <i>Kh&#243;a</i> l&#224; <b>b&#7845;t bi&#7871;n</b> &#8212; '
           's&#7917;a thi&#7871;t k&#7871; = t&#7841;o phi&#234;n b&#7843;n m&#7899;i.<br/>'
           '&#8226; K&#7929; thu&#7853;t <b>kh&#244;ng th&#7845;y gi&#225;</b>: &#273;&#417;n '
           'gi&#225; c&#244;ng &#273;o&#7841;n do sub-ERD E quy&#7871;t &#273;&#7883;nh.',
           1400, 1440, w=420, h=180)

    p.legend(LEGEND_TEXT, 790, 1250, w=560, h=340)
    return p
