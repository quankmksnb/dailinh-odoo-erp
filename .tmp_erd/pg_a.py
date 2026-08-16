# -*- coding: utf-8 -*-
"""Sub-ERD A — Partners & Users (E01–E03, E27–E29). Nguồn: §2 Group A/E, §4.2."""
from erd_lib import Page, LEGEND_TEXT


def build():
    p = Page(1, 'A. Doi tac & Nguoi dung', 2320, 1340)
    p.title('Sub-ERD A &#8212; Partners &amp; Users',
            'S&#7903; h&#7919;u: PARTNER &#183; CUSTOMER &#183; SUPPLIER &#183; '
            'USER &#183; ROLE &#183; COMPANY &#160;&#8212;&#160; '
            'k&#253; hi&#7879;u Chen/EER (Elmasri)')

    # ---------------------------------------------------------- Partners
    p.entity('partner', 'PARTNER', 400, 150)
    p.isa('isa_p', 482, 252, disjoint=False)          # chồng lấn -> 'o'
    p.entity('cust', 'CUSTOMER', 150, 360, kind='sub')
    p.entity('supp', 'SUPPLIER /\nSUBCONTRACTOR', 660, 360, kind='sub')
    p.isa_link('partner', 'isa_p', ['cust', 'supp'], total=False)

    # quan hệ đệ quy: đối tác có người liên hệ
    p.rel('r_contact', 'has_contact', 690, 142)
    p.link('partner', 'r_contact', '1', exit_=('1', '0.3'))
    p.link('r_contact', 'partner', 'N', entry=('1', '0.7'),
           pts=[(760, 90), (400, 90)])

    p.attrs('a_partner', 'PARTNER', [
        '<u>Tax code</u> (legal identity)',
        'Partner name',
        'Partner role &#8212; <i>discriminator</i>',
        'Phone &#183; Mobile &#183; Email',
        'Address (street / city / country)',
        'Duplicate-tax-code exemption flag',
        'Cooperation status',
    ], 60, 130, w=300)
    p.attach('partner', 'a_partner')

    p.attrs('a_cust', 'CUSTOMER', [
        '<u>Customer code</u> (KH-0001)',
        '<u>Tax code</u> (unique / customers)',
        'Customer type (Individual / Company / Dealer)',
        'Contact persons',
        'Customer group (auto-computed)',
        'Quotation count &#183; Win rate &#183; Revenue',
        'Order-splitting warning',
    ], 60, 470, w=300)
    p.attach('cust', 'a_cust')

    p.attrs('a_supp', 'SUPPLIER / SUBCONTRACTOR', [
        '<u>Supplier name + Tax code</u>',
        'Phone &#183; Email (purchasing)',
        'Delivery / pickup address',
        'Cooperation status',
        '<i>no auto-generated code</i>',
    ], 620, 470, w=300)
    p.attach('supp', 'a_supp')

    # ---------------------------------------------------------- Users
    p.entity('company', 'COMPANY', 1520, 150)
    p.rel('r_employs', 'employs', 1555, 302)
    p.entity('user', 'USER', 1520, 450)
    p.rel('r_assigns', 'assigns', 1555, 602)
    p.entity('role', 'ROLE', 1520, 750)
    p.link('company', 'r_employs', '1')
    p.link('r_employs', 'user', 'N', total=True)
    p.link('user', 'r_assigns', 'M')
    p.link('r_assigns', 'role', 'N')

    p.rel('r_backup', 'backs_up', 1240, 442)
    p.link('user', 'r_backup', '1', exit_=('0', '0.3'))
    p.link('r_backup', 'user', 'N', entry=('0', '0.7'),
           pts=[(1180, 560), (1450, 560)])

    p.attrs('a_company', 'COMPANY', [
        '<u>Company name + Tax code</u>',
        'Currency (<b>must be VND</b>)',
        'Address &#183; Contact details',
        'Logo printed on documents',
    ], 1830, 130, w=300)
    p.attach('company', 'a_company')

    p.attrs('a_user', 'USER', [
        '<u>Username</u> &#183; <u>Email</u>',
        'Full name (shown on documents)',
        'Internal phone',
        'Assigned roles (may hold several)',
        'Backup approver',
        'Last sign-in &#183; Account status',
    ], 1830, 430, w=300)
    p.attach('user', 'a_user')

    p.attrs('a_role', 'ROLE', [
        '<u>Role name</u>',
        'Description of responsibilities',
        'System-role flag',
        'Number of accounts holding it',
        'Granted features &amp; operations',
    ], 1830, 730, w=300)
    p.attach('role', 'a_role')

    # ---------------------------------------------------------- notes
    p.note('<b>Chuy&#234;n bi&#7879;t ho&#225; PARTNER: b&#7897; ph&#7853;n, '
           'ch&#7891;ng l&#7845;n (partial, overlapping)</b><br/>'
           'M&#7897;t &#273;&#7889;i t&#225;c c&#243; th&#7875; v&#7915;a l&#224; '
           'Kh&#225;ch h&#224;ng v&#7915;a l&#224; Nh&#224; cung c&#7845;p '
           '(vai tr&#242; <i>Both</i>) &#8658; v&#242;ng tr&#242;n mang <b>o</b>, '
           '&#273;&#432;&#7901;ng n&#7889;i l&#7899;p cha l&#224; &#273;&#432;&#7901;ng '
           '&#273;&#417;n.<br/>Hai chuy&#234;n bi&#7879;t ho&#225; c&#242;n l&#7841;i '
           '(ITEM &#8212; sub-ERD B, BOM &#8212; sub-ERD C) l&#224; '
           '<b>to&#224;n ph&#7847;n, lo&#7841;i tr&#7915;</b>.',
           660, 900, w=430, h=170)

    p.note('<b>Quan h&#7879; v&#7899;i ch&#7913;ng t&#7915; v&#7869; &#7903; '
           'sub-ERD kh&#225;c</b> (quy &#432;&#7899;c &#167;4.0-2)<br/>'
           'CUSTOMER &#8594; RFQ / B&#225;o gi&#225; / &#272;&#417;n h&#224;ng: sub-ERD D<br/>'
           'SUPPLIER &#8594; B&#7843;ng gi&#225; NCC: sub-ERD B<br/>'
           'SUPPLIER &#8594; D&#242;ng c&#244;ng &#273;o&#7841;n (thu&#234; ngo&#224;i): '
           'sub-ERD C<br/>'
           'USER &#8594; duy&#7879;t BOM / b&#7843;n v&#7869; / y&#234;u c&#7847;u '
           'ph&#234; duy&#7879;t: sub-ERD B, C, E<br/>'
           'COMPANY &#8594; ph&#225;t h&#224;nh b&#225;o gi&#225; / &#273;&#417;n, '
           'ph&#7841;m vi c&#7845;u h&#236;nh gi&#225;: sub-ERD D, E',
           1130, 900, w=430, h=170)

    p.legend(LEGEND_TEXT, 60, 900, w=560, h=340)
    return p
