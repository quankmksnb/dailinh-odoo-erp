# -*- coding: utf-8 -*-
"""Ba vết còn lại sau khi s3_apply.py dựng lại §3 của Report 4.0_TDS.docx.

1. Hộp "Transient (wizard) tables…" bị lặp: bản cũ đi theo khối dl_sale_order,
   bản mới nằm cuối §3.1. Giữ bản cuối §3.1, xoá bản cũ.
2. Bảng cột của res_users vỡ lưới (9 dòng × 10 cột) và liệt kê name / email /
   phone như cột của bảng — thực ra chúng nằm ở res_partner qua _inherits.
   Dựng lại bảng, bổ sung cột dự án thật sự thêm: dl_backup_approver_id.
3. Đánh dấu trường TOC là "dirty" để Word tự cập nhật mục lục khi mở — sau khi
   49 tiêu đề Heading 3 biến thành 6 nhóm thì mục lục cũ sai hoàn toàn.

Chạy:  venv/Scripts/python.exe .tmp_tds/s3_fix.py [--dry]
"""
import io
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document                                       # noqa: E402
from docx.oxml.ns import qn                                     # noqa: E402

import builder as B                                             # noqa: E402
import s3_groups as G                                           # noqa: E402

SRC = r"D:\FPTU\do_van_an\DLM-ERP Report\Report 4.0_TDS.docx"
DRY = '--dry' in sys.argv

USERS_ROWS = [
    ["id [Native]", "—", "BIGSERIAL", "PK", "Auto-increment"],
    ["login [Native]", "Char required", "VARCHAR", "NOT NULL, UNIQUE",
     "Khoá xác thực. Dự án dùng e-mail làm login."],
    ["password [Native]", "Char", "VARCHAR", "—",
     "Băm PBKDF2 do Odoo quản lý — không bao giờ lưu bản rõ."],
    ["active [Native]", "Boolean", "BOOL", "NOT NULL DEFAULT TRUE",
     "Khoá tài khoản = đặt false. Không xoá dòng, để mọi cột kiểm toán còn trỏ tới người thật."],
    ["login_date [Native]", "Datetime", "TIMESTAMP", "—", "Lần đăng nhập gần nhất"],
    ["partner_id [Native]", "Many2one required", "INTEGER", "FK → res_partner, NOT NULL",
     "_inherits: name, email, phone của người dùng nằm ở res_partner chứ KHÔNG phải cột của bảng "
     "này — cùng cơ chế ủy quyền như product_product → product_template."],
    ["company_id [Native]", "Many2one required", "INTEGER", "FK → res_company, NOT NULL",
     "Công ty chủ quản"],
    ["share [Native]", "Boolean", "BOOL", "—",
     "false = người dùng nội bộ. Màn Quản lý người dùng lọc theo cột này."],
    ["dl_backup_approver_id", "Many2one", "INTEGER", "FK → res_users, ON DELETE SET NULL",
     "Người duyệt dự phòng khi người này vắng hoặc quá SLA (IP-02). Đây là cột DUY NHẤT dự án "
     "thêm vào bảng res_users."],
]

USERS_NOTE = ("dl_config thêm đúng một cột. Các thao tác quản trị người dùng (tạo, khoá, gán vai "
              "trò, đặt lại mật khẩu) không thêm cột nào — chúng là method có guard Admin DLM, "
              "xem bảng ràng buộc bên dưới và §4.")


def cellt(tc):
    return ' '.join(''.join(t.text or '' for t in tc.iter(qn('w:t'))).split())


def first_cell(tbl):
    tr = tbl.find(qn('w:tr'))
    if tr is None:
        return ''
    tc = tr.find(qn('w:tc'))
    return cellt(tc) if tc is not None else ''


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(qn('w:t')))


def die(msg):
    print('DUNG: %s' % msg)
    sys.exit(1)


def main():
    doc = Document(SRC)
    body = doc.element.body
    tbls = list(body.iter(qn('w:tbl')))

    # 1. hộp Transient bị lặp -------------------------------------------------
    trans = [t for t in tbls if first_cell(t).startswith('Transient (wizard)')]
    print('hop "Transient": %d' % len(trans))
    if len(trans) != 2:
        die('cho doi dung 2 hop Transient')

    # 2. bảng cột res_users ---------------------------------------------------
    users = [t for t in tbls
             if first_cell(t) == 'Column'
             and any('login [Native]' in cellt(tc)
                     for tr in t.findall(qn('w:tr'))
                     for tc in tr.findall(qn('w:tc')))]
    print('bang cot res_users: %d (luoi %s)'
          % (len(users), [len(t.findall(qn('w:tr'))) for t in users]))
    if len(users) != 1:
        die('khong xac dinh duoc bang cot res_users')

    # 3. trường TOC -----------------------------------------------------------
    toc_p = [p for p in body.iter(qn('w:p'))
             if any('TOC' in (it.text or '') for it in p.iter(qn('w:instrText')))]
    print('doan chua truong TOC: %d' % len(toc_p))
    if len(toc_p) != 1:
        die('cho doi dung 1 truong TOC')
    begins = [f for f in toc_p[0].iter(qn('w:fldChar'))
              if f.get(qn('w:fldCharType')) == 'begin']
    if not begins:
        die('khong thay fldChar begin cua TOC')

    if DRY:
        print('--dry: khong ghi file')
        return

    shutil.copy2(SRC, SRC.replace('.docx', '.backup-%s.docx'
                                  % datetime.now().strftime('%Y%m%d-%H%M%S')))

    old = trans[0]
    old.getparent().remove(old)

    new_tbl = B.table(G.CH, USERS_ROWS, G.CW)
    note = B.para(USERS_NOTE, style='Normal')
    users[0].addprevious(new_tbl)
    new_tbl.addnext(note)
    users[0].getparent().remove(users[0])

    begins[0].set(qn('w:dirty'), 'true')

    doc.save(SRC)
    print('DA GHI: %s' % SRC)


if __name__ == '__main__':
    main()
