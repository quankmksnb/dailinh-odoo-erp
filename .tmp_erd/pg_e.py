# -*- coding: utf-8 -*-
"""Sub-ERD E — Pricing Configuration & Approval (E24–E26). Nguồn: §2 Group E, §4.6."""
from erd_lib import Page, LEGEND_TEXT, E_SOFT


def build():
    p = Page(5, 'E. Cau hinh gia & Phe duyet', 2700, 1850)
    p.title('Sub-ERD E &#8212; Pricing Configuration &amp; Approval',
            'S&#7903; h&#7919;u: PRICING_CONFIG &#183; APPROVAL_MATRIX &#183; '
            'APPROVAL_REQUEST &#160;&#8212;&#160; entity bi&#234;n: CUSTOMER &#183; '
            'COMPANY &#183; USER &#183; PRODUCT_CATEGORY &#183; RAW_MATERIAL &#183; '
            'OPERATION &#183; BOM_OPERATION_LINE &#183; QUOTATION &#183; '
            'QUOTATION_LINE &#183; PRICE_COMPONENT')

    # ------------------------------------------------ cấu hình giá
    p.entity('pconf', 'PRICING CONFIGURATION', 700, 620)

    p.entity('company', 'COMPANY', 700, 300, kind='ext')
    p.rel('r_scopes', 'scopes', 735, 452)
    p.link('company', 'r_scopes', '1')
    p.link('r_scopes', 'pconf', 'N', total=True)

    p.entity('pcat', 'PRODUCT CATEGORY', 60, 300, kind='ext')
    p.rel('r_tg_cat', 'targets', 380, 292)
    p.link('pconf', 'r_tg_cat', 'N', entry=('1', '0.5'))
    p.link('r_tg_cat', 'pcat', '1')

    p.entity('rm', 'RAW MATERIAL', 60, 620, kind='ext')
    p.rel('r_tg_rm', 'targets', 380, 612)
    p.link('pconf', 'r_tg_rm', 'N')
    p.link('r_tg_rm', 'rm', '1')

    p.entity('op', 'OPERATION', 60, 940, kind='ext')
    p.rel('r_tg_op', 'targets', 380, 932)
    p.link('pconf', 'r_tg_op', 'N', exit_=('0', '0.7'))
    p.link('r_tg_op', 'op', '1')

    p.entity('cust', 'CUSTOMER', 620, 940, kind='ext')
    p.rel('r_disc', 'discount_group', 700, 792)
    p.link('cust', 'r_disc', 'N')
    p.link('r_disc', 'pconf', '1')

    # ------------------------------------------------ nơi quy tắc giá tác động
    p.entity('bol', 'BOM OPERATION LINE', 1300, 460, kind='ext')
    p.rel('r_prices', 'prices', 1050, 452)
    p.link('pconf', 'r_prices', '1', exit_=('1', '0.3'))
    p.link('r_prices', 'bol', 'N')

    p.entity('quol', 'QUOTATION LINE', 1300, 620, kind='ext')
    p.rel('r_calc', 'calculates', 1050, 612)
    p.link('pconf', 'r_calc', '1')
    p.link('r_calc', 'quol', 'N')

    p.entity('pcomp', 'PRICE COMPONENT', 1300, 780, kind='ext')
    p.rel('r_src', 'sourced_from', 1050, 772)
    p.edge('pconf', 'r_src', '1', E_SOFT, exit_=('1', '0.7'))
    p.edge('r_src', 'pcomp', 'N', E_SOFT)

    # ------------------------------------------------ ma trận phê duyệt
    p.entity('amx', 'QUOTATION APPROVAL MATRIX', 1800, 620)
    p.entity('quo', 'QUOTATION', 1800, 200, kind='ext')
    p.rel('r_routes', 'routes', 1835, 400)
    p.link('amx', 'r_routes', '1')
    p.link('r_routes', 'quo', 'N')

    p.rel('r_super', 'supersedes', 2100, 612)
    p.link('amx', 'r_super', '1', exit_=('1', '0.3'))
    p.link('r_super', 'amx', 'N', entry=('1', '0.7'),
           pts=[(2170, 730), (1930, 730)])

    # ------------------------------------------------ yêu cầu phê duyệt
    p.entity('areq', 'APPROVAL REQUEST', 1800, 1000)
    p.rel('r_just', 'justifies', 1835, 820)
    p.link('amx', 'r_just', '1')
    p.link('r_just', 'areq', 'N')

    p.rel('r_req_q', 'requests', 1550, 992)
    p.link('areq', 'r_req_q', 'N')
    p.link('r_req_q', 'quo', '1', entry=('0', '0.5'),
           pts=[(1620, 229)])

    p.rel('r_req_p', 'requests', 1050, 1150)
    p.link('pconf', 'r_req_p', '1', exit_=('0.85', '1'), pts=[(888, 1187)])
    p.link('r_req_p', 'areq', 'N', entry=('0.25', '1'), pts=[(1850, 1187)])

    p.entity('user', 'USER', 2200, 1000, kind='ext')
    p.rel('r_notif', 'notifies', 2050, 992)
    p.link('areq', 'r_notif', 'N')
    p.link('r_notif', 'user', '1', total=True)

    # ------------------------------------------------ thuộc tính
    p.attrs('a_pconf', 'PRICING CONFIGURATION', [
        '<u>(Rule type, Target, Validity period)</u> + Revision',
        'Rule type &#8212; <i>classification attribute</i>:',
        '&#160;&#160;profit &#183; discount &#183; operation rate &#183; '
        'overhead &#183; waste',
        'Target: customer group &#183; operation &#183; category &#183;',
        '&#160;&#160;material &#183; company-wide',
        'Calculation method (% &#183; per unit &#183; per batch &#183;',
        '&#160;&#160;per kg/m/m&#178; &#183; multiplier) &#183; Value',
        'Target &amp; minimum markup',
        'Default &amp; maximum discount &#183; Setup fee',
        'Base waste &amp; recovery rates',
        'Discount-excluded flag',
        'Validity period &#183; Revision number &#183; Change reason',
        '<b>Used-in-a-quotation flag</b> (locks editing)',
    ], 60, 1150, w=400)
    p.attach('pconf', 'a_pconf')

    p.attrs('a_amx', 'QUOTATION APPROVAL MATRIX', [
        '<u>(Amount threshold, Validity period, Revision)</u>',
        'Amount threshold from',
        'Approval level (None / Sales Manager / CEO)',
        'Specific approver (blank &#8658; anyone at that level)',
        'The original row this one revises',
        'Validity period &#183; Revision number',
        'Change reason',
    ], 2300, 380, w=340)
    p.attach('amx', 'a_amx')

    p.attrs('a_areq', 'APPROVAL REQUEST', [
        '<u>(Submitted object, Request type, Submitted at)</u>',
        'Title (auto-composed) &#183; Request type',
        'Submitted object (<b>soft reference</b>)',
        'Old value &#8594; New value &#183; Expected impact',
        'Reason (mandatory)',
        'Requester &#183; Role at submission',
        'Resolved approval level',
        'Matrix row &amp; revision used as routing evidence',
        'Approver &#183; Processing timestamp',
        'Rejection reason &#183; Self-approval flag',
    ], 1750, 1250, w=350)
    p.attach('areq', 'a_areq')

    # ------------------------------------------------ ghi chú
    p.note('<b>Ba nguy&#234;n t&#7855;c b&#7845;t di b&#7845;t d&#7883;ch '
           'c&#7911;a c&#7845;u h&#236;nh gi&#225;</b><br/>'
           '&#8226; Quy t&#7855;c &#273;&#227; b&#7883; b&#225;o gi&#225; ch&#7889;t '
           'snapshot &#8658; <b>kh&#244;ng s&#7917;a, kh&#244;ng xo&#225;</b>.<br/>'
           '&#8226; Hai b&#7843;n &#273;ang &#225;p d&#7909;ng cho c&#249;ng '
           '&#273;&#7889;i t&#432;&#7907;ng <b>kh&#244;ng &#273;&#432;&#7907;c '
           'ch&#7891;ng l&#7845;n</b> kho&#7843;ng hi&#7879;u l&#7921;c.<br/>'
           '&#8226; &#193;p b&#7843;n m&#7899;i &#8658; h&#7879; th&#7889;ng '
           '<b>t&#7921; &#273;&#243;ng</b> b&#7843;n c&#361;.',
           1120, 1450, w=420, h=155)

    p.note('<b>&#272;&#7883;nh tuy&#7871;n ph&#234; duy&#7879;t</b><br/>'
           'Ma tr&#7853;n quy&#7871;t &#273;&#7883;nh <i>ai duy&#7879;t</i> theo '
           't&#7893;ng ti&#7873;n sau chi&#7871;t kh&#7845;u tr&#432;&#7899;c VAT. '
           'B&#225;o gi&#225; ghi l&#7841;i <b>&#273;&#250;ng d&#242;ng ma tr&#7853;n '
           '+ s&#7889; hi&#7879;u b&#7843;n s&#7917;a &#273;&#7893;i</b> &#273;&#227; '
           'd&#249;ng &#8658; quy&#7871;t &#273;&#7883;nh &#273;&#7883;nh tuy&#7871;n '
           'lu&#244;n ch&#7913;ng minh &#273;&#432;&#7907;c v&#7873; sau.<br/>'
           'M&#7897;t &#273;&#7889;i t&#432;&#7907;ng ch&#7881; c&#243; <b>m&#7897;t</b> '
           'y&#234;u c&#7847;u &#273;ang ch&#7901; &#8212; d&#7919; li&#7879;u gi&#225; '
           '&#273;&#7893;i th&#236; hu&#7927; phi&#7871;u c&#361; v&#224; l&#7853;p '
           'phi&#7871;u m&#7899;i, <b>kh&#244;ng ghi &#273;&#232;</b>.',
           1120, 1630, w=420, h=190)

    p.legend(LEGEND_TEXT, 520, 1450, w=560, h=340)
    return p
