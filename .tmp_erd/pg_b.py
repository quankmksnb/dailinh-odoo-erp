# -*- coding: utf-8 -*-
"""Sub-ERD B — Product & Material Master Data (E04–E11). Nguồn: §2 Group B, §4.3."""
from erd_lib import Page, LEGEND_TEXT


def build():
    p = Page(2, 'B. Danh muc San pham & Vat tu', 2460, 1440)
    p.title('Sub-ERD B &#8212; Product &amp; Material Master Data',
            'S&#7903; h&#7919;u: PRODUCT_CATEGORY &#183; ITEM + 4 l&#7899;p con &#183; '
            'SUPPLIER_PRICE_LIST &#183; UOM &#160;&#8212;&#160; '
            'entity bi&#234;n: SUPPLIER &#183; USER')

    # -------------------------------------------------- category -> item
    p.entity('cat', 'PRODUCT_CATEGORY', 420, 140)
    p.rel('r_parent', 'parent_of', 710, 132)
    p.link('cat', 'r_parent', '1', exit_=('1', '0.3'))
    p.link('r_parent', 'cat', 'N', entry=('1', '0.7'),
           pts=[(780, 92), (420, 92)])

    p.rel('r_class', 'classifies', 455, 290)
    p.link('cat', 'r_class', '1')
    p.link('r_class', 'item', 'N', total=True)

    p.entity('item', 'ITEM', 420, 440)
    p.isa('isa_i', 517, 560, disjoint=True)
    p.entity('mp', 'MANUFACTURED\nPRODUCT', 60, 700, kind='sub')
    p.entity('tp', 'TRADING\nPRODUCT', 310, 700, kind='sub', w=210)
    p.entity('rm', 'RAW MATERIAL', 560, 700, kind='sub')
    p.entity('pm', 'PROCESSED\nMATERIAL', 810, 700, kind='sub')
    p.isa_link('item', 'isa_i', ['mp', 'tp', 'rm', 'pm'], total=True)

    # vật tư -> phế liệu thu hồi (đệ quy qua ITEM)
    p.rel('r_scrap', 'recovers_as_scrap', 900, 580)
    p.link('rm', 'r_scrap', 'N', exit_=('0.9', '0'), entry=('0.2', '1'))
    p.link('r_scrap', 'item', '1', exit_=('0', '0.5'), entry=('0.8', '1'))

    # -------------------------------------------------- uom / price list
    p.entity('uom', 'UNIT OF MEASURE', 1400, 440)
    p.rel('r_meas', 'measures', 1150, 432)
    p.link('uom', 'r_meas', '1')
    p.link('r_meas', 'item', 'N', total=True)

    p.entity('spl', 'SUPPLIER PRICE LIST', 1400, 900)
    p.rel('r_conv', 'converts', 1435, 690)
    p.link('uom', 'r_conv', '1')
    p.link('r_conv', 'spl', 'N')

    p.rel('r_priced', 'priced_by', 1150, 892)
    p.link('spl', 'r_priced', 'N', total=True)
    p.link('r_priced', 'item', '1', entry=('0.85', '1'),
           pts=[(1080, 929), (1080, 545), (598, 545)])

    p.entity('supp', 'SUPPLIER /\nSUBCONTRACTOR', 2000, 900, kind='ext')
    p.rel('r_issues', 'issues', 1750, 892)
    p.link('supp', 'r_issues', '1')
    p.link('r_issues', 'spl', 'N', total=True)

    p.entity('user', 'USER', 2000, 1100, kind='ext')
    p.rel('r_appr', 'approves', 1750, 1092)
    p.link('user', 'r_appr', '1')
    p.link('r_appr', 'spl', 'N')

    # -------------------------------------------------- attributes
    p.attrs('a_cat', 'PRODUCT_CATEGORY', [
        '<u>Full path in the tree</u>',
        'Category name',
        'Parent category',
        'Business branch (derived from position)',
        'Usage status',
    ], 60, 120, w=330)
    p.attach('cat', 'a_cat')

    p.attrs('a_item', 'ITEM', [
        '<u>Item code</u> (GC- / TM- / VT- / BTP-)',
        'Item name',
        'Item kind &#8212; <i>discriminator</i>',
        'Product category &#183; Unit of measure',
        'Sale price',
        'Reference cost (from applied price list)',
        'Lifecycle state (Draft/Approved/Obsolete)',
        'RFQ-provisional flag',
    ], 60, 300, w=330)
    p.attach('item', 'a_item')

    p.attrs('a_mp', 'MANUFACTURED PRODUCT', [
        '<u>Code GC-</u> &#183; <u>Name (no duplicate)</u>',
        'Dimensions L &#183; W &#183; H &#183; thickness',
        'Main material &#183; Finishing type',
        'Estimated weight',
    ], 30, 790, w=250)
    p.attach('mp', 'a_mp')

    p.attrs('a_tp', 'TRADING PRODUCT', [
        '<u>Code TM-</u>',
        'Sale price (unlocked once cost exists)',
        'Reference cost &#183; Margin rate',
        'Supplier-price state',
    ], 300, 790, w=250)
    p.attach('tp', 'a_tp')

    p.attrs('a_rm', 'RAW MATERIAL', [
        '<u>Code VT- + specification</u>',
        'Density (single source of truth)',
        'Base waste rate',
        'Recoverable flag &#183; Recovery rate',
        'Matching scrap item',
    ], 560, 790, w=250)
    p.attach('rm', 'a_rm')

    p.attrs('a_pm', 'PROCESSED MATERIAL', [
        '<u>Code BTP-</u> &#183; <u>Name (no duplicate)</u>',
        'Dimensions L &#183; W &#183; H &#183; thickness',
        'Source raw material to be cut',
        'Waste rate &#183; Recoverable flag',
    ], 830, 790, w=250)
    p.attach('pm', 'a_pm')

    p.attrs('a_uom', 'UNIT OF MEASURE', [
        '<u>Unit name within its category</u>',
        'Measurement category (Weight/Length/Area/Unit)',
        'Conversion factor vs reference unit',
        'Usage status',
    ], 1730, 400, w=310)
    p.attach('uom', 'a_uom')

    p.attrs('a_spl', 'SUPPLIER PRICE LIST', [
        '<u>(Supplier, Item, Validity period)</u>',
        'Unit price (&gt; 0)',
        'Purchase unit of measure',
        'Minimum quantity',
        'Validity start &#183; end date',
        'Approval state &#183; <b>Applied flag</b>',
        'Approver &#183; Approval date',
    ], 1730, 1210, w=310)
    p.attach('spl', 'a_spl')

    # -------------------------------------------------- notes
    p.note('<b>Chuy&#234;n bi&#7879;t ho&#225; ITEM: to&#224;n ph&#7847;n, '
           'lo&#7841;i tr&#7915; (total, disjoint)</b><br/>'
           'M&#7885;i m&#7863;t h&#224;ng b&#7855;t bu&#7897;c thu&#7897;c '
           '&#273;&#250;ng m&#7897;t trong b&#7889;n l&#7899;p con &#8658; '
           'v&#242;ng tr&#242;n mang <b>d</b>, &#273;&#432;&#7901;ng n&#7889;i '
           'l&#7899;p cha l&#224; <b>&#273;&#432;&#7901;ng k&#233;p</b>.<br/>'
           '&#272;&#7893;i lo&#7841;i m&#7863;t h&#224;ng ch&#7881; l&#224; '
           '&#273;&#7893;i thu&#7897;c t&#237;nh ph&#226;n l&#7899;p '
           '<i>item kind</i> &#8212; kh&#244;ng m&#7845;t l&#7883;ch s&#7917;.',
           700, 1010, w=420, h=150)

    p.note('<b>R&#224;ng bu&#7897;c nghi&#7879;p v&#7909;</b><br/>'
           '&#8226; M&#7897;t ITEM c&#243; <b>t&#7889;i &#273;a M&#7852;T</b> '
           'SUPPLIER_PRICE_LIST &#273;ang <i>&#225;p d&#7909;ng</i>.<br/>'
           '&#8226; Ch&#7881; &#273;&#225;nh d&#7845;u <i>&#225;p d&#7909;ng</i> khi '
           'b&#7843;ng gi&#225; &#273;&#227; duy&#7879;t <b>v&#224;</b> c&#242;n '
           'trong h&#7841;n hi&#7879;u l&#7921;c.<br/>'
           '&#8226; Gi&#225; v&#7889;n tham chi&#7871;u c&#7911;a ITEM '
           '<b>suy ra</b> t&#7915; b&#7843;ng gi&#225; &#273;ang &#225;p d&#7909;ng, '
           'kh&#244;ng nh&#7853;p tay.<br/>'
           '&#8226; BTP kh&#244;ng l&#7845;y gi&#225; t&#7915; b&#7843;ng gi&#225; NCC &#8212; '
           'gi&#225; v&#7889;n suy <b>&#273;&#7879; quy</b> t&#7915; &#273;&#7883;nh '
           'm&#7913;c con (sub-ERD C).',
           1150, 1010, w=430, h=180)

    p.note('<b>Ph&#7871; li&#7879;u thu h&#7891;i &#8212; <i>kh&#244;ng</i> ph&#7843;i '
           'th&#7921;c th&#7875; ri&#234;ng</b><br/>'
           'Ph&#7871; li&#7879;u c&#7855;t ra t&#7915; m&#7897;t v&#7853;t t&#432; '
           'l&#7841;i ch&#237;nh l&#224; <b>m&#7897;t ITEM kh&#225;c</b> (b&#225;n '
           '&#273;&#432;&#7907;c, c&#243; &#273;&#417;n v&#7883; t&#237;nh v&#224; '
           'gi&#225;) &#8658; m&#244; h&#236;nh b&#7857;ng quan h&#7879; '
           '<b>&#273;&#7879; quy qua ITEM</b>: <i>recovers_as_scrap</i> '
           '(&#167;5-2), kh&#244;ng nh&#226;n &#273;&#244;i danh m&#7909;c.<br/>'
           'RAW MATERIAL gi&#7919; <i>recoverable flag</i>, <i>recovery rate</i> '
           '(&#225;p tr&#234;n <b>l&#432;&#7907;ng hao h&#7909;t</b>) v&#224; '
           '<i>matching scrap item</i>.<br/>'
           'Ti&#7873;n thu h&#7891;i xu&#7845;t hi&#7879;n ti&#7871;p &#7903;: '
           '<b>sub-ERD C</b> &#8212; <i>scrap value</i> tr&#234;n d&#242;ng '
           'v&#7853;t t&#432;; <b>sub-ERD D</b> &#8212; c&#7845;u ph&#7847;n '
           'gi&#225; lo&#7841;i <i>Scrap recovery</i> (kho&#7843;n <b>tr&#7915;</b> '
           'gi&#225; th&#224;nh).',
           1700, 560, w=430, h=210)

    p.legend(LEGEND_TEXT, 60, 1010, w=560, h=340)
    return p
