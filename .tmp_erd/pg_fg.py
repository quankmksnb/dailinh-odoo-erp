# -*- coding: utf-8 -*-
"""Sub-ERD G — Production Orders *(reserved)*. Nguồn: §4.8, §4.9.

Trang F trước đây nằm chung file này (khi Kho còn là khung rỗng); nay Kho đã hiện thực
nên F tách sang `pg_f.py`.
"""
from erd_lib import Page, LEGEND_TEXT

RESERVED_NOTE = (
    '<b>Trang n&#224;y c&#7889; &#253; &#273;&#7875; tr&#7889;ng</b><br/>'
    'H&#7897;p <b>n&#233;t &#273;&#7913;t &#273;&#7887;, ch&#7919; nghi&#234;ng</b> '
    'l&#224; entity <i>d&#7921; ki&#7871;n</i> &#8212; ch&#432;a ch&#7889;t '
    't&#234;n, ch&#432;a ch&#7889;t thu&#7897;c t&#237;nh, ch&#432;a c&#7845;p '
    'm&#227;. H&#7897;p <b>n&#233;t &#273;&#7913;t x&#225;m</b> l&#224; entity '
    'bi&#234;n &#273;&#227; ch&#7889;t &#7903; sub-ERD A&#8211;E.<br/>'
    'M&#361;i t&#234;n <b>ch&#7845;m t&#237;m</b> l&#224; <b>seam</b> '
    '(&#167;4.9) &#8212; cam k&#7871;t v&#7873; &#273;i&#7875;m n&#7889;i, '
    '<i>ch&#432;a</i> ph&#7843;i l&#7921;c l&#432;&#7907;ng. Khi v&#7869; th&#7853;t '
    'm&#7899;i thay b&#7857;ng h&#236;nh thoi + 1/M/N.'
)


def _g():
    p = Page(7, 'G. Lenh san xuat (reserved - chua hien thuc)', 2700, 2000)
    p.title('Sub-ERD G &#8212; Production Orders <i>(reserved &#8212; '
            'ch&#432;a hi&#7879;n th&#7921;c)</i>',
            'Gi&#7919; ch&#7895; cho nghi&#7879;p v&#7909; <b>Ph&#225;t '
            'l&#7879;nh s&#7843;n xu&#7845;t</b>. To&#224;n b&#7897; &#273;i&#7875;m '
            'n&#7889;i &#273;&#7873;u tr&#7887; v&#7873; th&#7921;c th&#7875; '
            '&#273;&#227; ch&#7889;t &#8658; th&#234;m G <b>kh&#244;ng '
            '&#273;&#242;i &#273;&#7893;i c&#7845;u tr&#250;c</b> A&#8211;E '
            '&#8212; xem &#167;4.8.')

    p.box('h_ext', 'ENTITY BI&#202;N B&#7854;T BU&#7896;C '
                   '<i>(&#273;&#227; ch&#7889;t &#7903; sub-ERD A&#8211;E, F)</i>',
          100, 150, 'text;html=1;strokeColor=none;fillColor=none;align=left;'
                    'verticalAlign=middle;fontSize=13;fontStyle=1;'
                    'fontColor=#666666;', 460, 26)
    p.entity('sol', 'SALES ORDER LINE  (D)', 100, 200, kind='ext')
    p.entity('bom', 'BILL OF MATERIALS  (C)', 100, 370, kind='ext')
    p.entity('user', 'USER  (A)', 100, 540, kind='ext')
    p.entity('bml', 'BOM MATERIAL LINE  (C)', 100, 710, kind='ext')
    p.entity('item', 'ITEM + 4 l&#7899;p con  (B)', 100, 880, kind='ext')
    p.entity('uom', 'UNIT OF MEASURE  (B)', 100, 1050, kind='ext')
    p.entity('sm', 'STOCK MOVE  (F)', 100, 1220, kind='ext')
    p.entity('bol', 'BOM OPERATION LINE  (C)', 100, 1390, kind='ext')
    p.entity('op', 'OPERATION  (C)', 100, 1560, kind='ext')

    p.box('h_todo', 'D&#920; KI&#7870;N S&#7902; H&#7918;U &#8212; d&#7843;i '
                    'm&#227; <b>E40+</b> <i>(ch&#432;a c&#7845;p)</i>',
          800, 150, 'text;html=1;strokeColor=none;fillColor=none;align=left;'
                    'verticalAlign=middle;fontSize=13;fontStyle=1;'
                    'fontColor=#b85450;', 460, 26)
    p.entity('po', 'PRODUCTION ORDER', 800, 300, kind='todo')
    p.entity('pml', 'PRODUCTION MATERIAL LINE\n<i>(ti&#234;u hao th&#7921;c '
                    't&#7871;)</i>', 800, 780, kind='todo')
    p.entity('wc', 'WORK CENTER\n<i>(t&#249;y ph&#7841;m vi)</i>',
             800, 1120, kind='todo')
    p.entity('pol', 'PRODUCTION OPERATION LINE\n<i>(c&#244;ng &#273;o&#7841;n '
                    '&#273;&#227; th&#7921;c hi&#7879;n)</i>', 800, 1450,
             kind='todo')

    p.soft('sol', 'po', 'S1 &#183; ngu&#7891;n ph&#225;t l&#7879;nh')
    p.soft('bom', 'po', 'S2 &#183; c&#244;ng th&#7913;c')
    p.soft('user', 'po', 'S7 &#183; ng&#432;&#7901;i ph&#225;t l&#7879;nh')
    p.soft('bml', 'pml', 'S2 &#183; &#273;&#7883;nh m&#7913;c v&#7853;t t&#432;')
    p.soft('item', 'pml', 'S4 &#183; v&#7853;t t&#432; ti&#234;u hao')
    p.soft('uom', 'pml', 'S5 &#183; quy &#273;&#7893;i')
    p.soft('sm', 'pml', 'S9 &#183; ti&#234;u hao &amp; nh&#7853;p kho')
    p.soft('bol', 'pol', 'S2 &#183; &#273;&#7883;nh m&#7913;c c&#244;ng &#273;o&#7841;n')
    p.soft('op', 'pol', 'S3 &#183; ghi nh&#7853;n c&#244;ng &#273;o&#7841;n')

    p.note('<b>Thu&#7897;c t&#237;nh ph&#7843;i b&#7893; sung &#7903; '
           's&#417; &#273;&#7891; KH&#193;C</b> (quy &#432;&#7899;c &#167;4.0-4)<br/>'
           'Khai <b>t&#7841;i sub-ERD D</b> (&#167;4.5), kh&#244;ng khai &#7903; '
           '&#273;&#226;y:<br/>'
           '&#8226; SALES_ORDER_LINE &#8592; <i>linked production order</i><br/>'
           '&#8226; SALES_ORDER_LINE &#8592; <i>produced quantity</i><br/>'
           'k&#232;m ch&#250; th&#237;ch <i>ngu&#7891;n g&#7889;c: ph&#7841;m vi '
           'S&#7843;n xu&#7845;t</i>.',
           1350, 200, w=440, h=190)

    p.note('<b>Vi&#7879;c c&#7847;n l&#224;m khi v&#7869; (&#167;4.8)</b><br/>'
           '&#9312; Ch&#7889;t l&#7879;nh ph&#225;t theo <b>&#273;&#417;n '
           'h&#224;ng</b> hay theo <b>d&#242;ng &#273;&#417;n h&#224;ng</b>.<br/>'
           '&#9313; Ch&#7889;t l&#7879;nh <b>sao ch&#233;p c&#7913;ng</b> '
           '&#273;&#7883;nh m&#7913;c (snapshot &#8212; &#273;&#7891;ng '
           'b&#7897; nguy&#234;n t&#7855;c &#167;0.3) hay <b>tra '
           '&#273;&#7897;ng</b> BOM hi&#7879;n h&#224;nh.<br/>'
           '&#9314; Ch&#7889;t c&#243; t&#225;ch <b>Work Center</b> kh&#244;ng.<br/>'
           '&#9315; Th&#234;m d&#242;ng v&#224;o <b>&#167;3.4</b> v&#224; '
           '<b>&#167;4.1</b>.',
           1350, 430, w=440, h=210)

    p.note(RESERVED_NOTE, 1350, 680, w=440, h=230)

    p.note('<b>V&#236; sao G kh&#244;ng l&#224;m v&#7905; A&#8211;E</b><br/>'
           'M&#7885;i seam c&#7911;a G (S1&#8211;S5, S7, S9) &#273;&#7873;u '
           'tr&#7887; v&#7873; <b>master data ho&#7863;c ch&#7913;ng t&#7915; '
           '&#273;&#227; ch&#7889;t</b>: d&#242;ng &#273;&#417;n b&#225;n, '
           '&#273;&#7883;nh m&#7913;c v&#224; hai lo&#7841;i d&#242;ng '
           'c&#7911;a n&#243;, c&#244;ng &#273;o&#7841;n, m&#7863;t h&#224;ng, '
           '&#273;&#417;n v&#7883; t&#237;nh, ng&#432;&#7901;i d&#249;ng.<br/>'
           'Kh&#244;ng seam n&#224;o ch&#7841;m v&#224;o <b>sub-ERD E</b> &#8212; '
           'c&#7845;u h&#236;nh gi&#225; v&#224; ph&#234; duy&#7879;t '
           'b&#225;o gi&#225; &#273;&#7913;ng ngo&#224;i ph&#7841;m vi '
           'S&#7843;n xu&#7845;t.<br/>'
           '<b>Th&#7913; t&#7921; l&#224;m</b>: &#9312; c&#7845;p m&#227; '
           'E40+ &#8594; &#9313; v&#7869; sub-ERD G &#8594; &#9314; '
           'c&#7853;p nh&#7853;t &#167;3.4, &#167;4.1, &#167;4.9.',
           1350, 940, w=440, h=280)

    p.legend(LEGEND_TEXT, 1350, 1260, w=560, h=340)
    return p


def build():
    return [_g()]
