"""Xoá SẠCH dữ liệu GIAO DỊCH của phân hệ Kho — giữ nguyên cấu hình kho.

Dùng khi muốn test lại luồng kho từ đầu mà không phải dựng lại cả DB
(``reset_demo_db.ps1`` xoá mọi thứ, kể cả RFQ / BOM / báo giá / đơn bán).

XOÁ:
    • stock.picking  — mọi phiếu: Nhận hàng, Kiểm hàng, Chuyển kho, Giao hàng,
                       Trả NCC, Bàn giao xưởng, Nhập TP, Bán/Hoá phế liệu.
    • stock.move / stock.move.line — dòng hàng của các phiếu trên.
    • stock.quant    — TOÀN BỘ tồn kho (kể cả tồn do kiểm kê tạo tay).
    • stock.lot      — mọi lô LO/2026/xxxxx.
    • stock.scrap, stock.package.level, stock.quant.package, procurement.group.
    • Chatter (mail.message / follower / activity / attachment) của các phiếu & lô.
    • Đưa số thứ tự phiếu (DL/NH/, DL/KC/, DL/CK/, …) và số lô LO/ về 00001.

GIỮ NGUYÊN:
    • Kho "DL", cây vị trí (Khu nhập / Kho nhà máy SX / Xưởng SX / Thành phẩm),
      11 loại hoạt động, ir.rule, ACL, nhóm quyền, RBAC.
    • Toàn bộ dữ liệu ngoài kho: sản phẩm, vật tư, giá NCC, RFQ, BOM, bản vẽ,
      báo giá, phê duyệt, đơn bán hàng, khách hàng, NCC, người dùng.
      (Chỉ reset lại cờ "Tình trạng giao hàng" trên đơn bán về "Chưa giao" —
      cờ đó là dẫn xuất của phiếu giao, phiếu mất thì cờ phải theo.)

⚠️  STOP phiên debug VS Code trước khi chạy: script cần kết nối độc quyền để
    sao lưu, và Odoo đang chạy sẽ giữ bản ghi cũ trong cache.

Cách chạy (từ thư mục gốc dự án):
    venv\\Scripts\\python.exe scripts\\purge_stock_data.py
    venv\\Scripts\\python.exe scripts\\purge_stock_data.py --dry-run   # chỉ đếm
    venv\\Scripts\\python.exe scripts\\purge_stock_data.py --no-backup
    venv\\Scripts\\python.exe scripts\\purge_stock_data.py --yes       # không hỏi
"""

import argparse
import datetime
import os
import re
import sys

import psycopg2
from psycopg2 import sql

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_PATH = os.path.join(REPO_ROOT, "odoo.conf")

# Thứ tự xoá = thứ tự phụ thuộc khoá ngoại, KHÔNG đảo được:
#   move_line → quant → move → package_level → lot → picking → scrap → group
# (quant và move_line đều trỏ tới lot; lot trỏ tới picking qua
#  dlm_receipt_picking_id ⇒ lô phải chết trước phiếu.)
DELETE_ORDER = [
    "stock_move_line",
    "stock_quant",
    "stock_move",
    "stock_package_level",
    "stock_lot",
    "stock_picking",
    "stock_scrap",
    "stock_quant_package",
    "procurement_group",
]

# Model kho có chatter — dọn kèm, nếu không mail_message trỏ tới res_id đã chết.
CHATTER_MODELS = ("stock.picking", "stock.lot", "stock.scrap", "stock.quant")

# Sequence phải kéo về 1. Lấy theo code (bảng ir_sequence) — mọi sequence của
# loại hoạt động lấy động qua stock_picking_type.sequence_id.
SEQUENCE_CODES = (
    "stock.picking",       # INT/ — phiếu nội bộ mặc định của Odoo
    "stock.lot.serial",    # LO/2026/ — số lô Đại Linh tự sinh
    "stock.scrap",         # SP/
    "stock.quant.package",  # PACK
)


def read_conf():
    """Đọc thông số DB từ odoo.conf — cùng nguồn với reset_demo_db.ps1."""
    values = {}
    with open(CONF_PATH, encoding="utf-8") as handle:
        for line in handle:
            match = re.match(r"^\s*([a-z_]+)\s*=\s*(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip()
    return dict(
        host=values.get("db_host") or "localhost",
        port=values.get("db_port") or "5432",
        user=values.get("db_user") or "odoo",
        password=values.get("db_password") or "odoo",
        dbname=values.get("db_name") or "dlm_dev",
    )


def count_rows(cur, table):
    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
    return cur.fetchone()[0]


def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s)", (table,))
    return cur.fetchone()[0] is not None


def show_summary(cur, tables):
    print("  Bảng dữ liệu kho:")
    total = 0
    for table in tables:
        rows = count_rows(cur, table)
        total += rows
        print("    %-24s %d" % (table, rows))
    cur.execute(
        "SELECT count(*) FROM mail_message WHERE model = ANY(%s)",
        (list(CHATTER_MODELS),))
    messages = cur.fetchone()[0]
    print("    %-24s %d" % ("mail_message (chatter)", messages))
    return total + messages


def backup(conn_params, dbname):
    """Sao lưu bằng CREATE DATABASE ... TEMPLATE — không cần pg_dump trên PATH.

    Phải ngắt hết kết nối tới DB nguồn: Postgres không cho copy DB đang có
    người dùng. Đây cũng là lý do phải Stop debug VS Code trước.
    """
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    backup_name = "%s_bak_kho_%s" % (dbname, stamp)
    params = dict(conn_params, dbname="postgres")
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()", (dbname,))
        busy = cur.fetchone()[0]
        if busy:
            raise SystemExit(
                "  ✗ DB '%s' còn %d kết nối đang mở (Odoo/pgAdmin còn chạy?).\n"
                "    Hãy STOP phiên debug VS Code rồi chạy lại, hoặc dùng "
                "--no-backup nếu chấp nhận không sao lưu." % (dbname, busy))
        cur.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(backup_name), sql.Identifier(dbname)))
        cur.close()
    finally:
        conn.close()
    return backup_name


def purge(cur, tables):
    deleted = {}
    for table in tables:
        cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))
        deleted[table] = cur.rowcount

    # Chatter: mail_notification / tracking_value / partner_rel đều ondelete
    # cascade từ mail_message nên xoá message là đủ.
    cur.execute("DELETE FROM mail_message WHERE model = ANY(%s)",
                (list(CHATTER_MODELS),))
    deleted["mail_message"] = cur.rowcount
    cur.execute("DELETE FROM mail_followers WHERE res_model = ANY(%s)",
                (list(CHATTER_MODELS),))
    deleted["mail_followers"] = cur.rowcount
    cur.execute("DELETE FROM mail_activity WHERE res_model = ANY(%s)",
                (list(CHATTER_MODELS),))
    deleted["mail_activity"] = cur.rowcount
    cur.execute("DELETE FROM ir_attachment WHERE res_model = ANY(%s)",
                (list(CHATTER_MODELS),))
    deleted["ir_attachment"] = cur.rowcount
    return deleted


def reset_sequences(cur):
    """Kéo số thứ tự phiếu & lô về 1.

    Sequence Odoo ``implementation='standard'`` giữ bộ đếm trong một sequence
    Postgres tên ``ir_sequence_%03d`` theo id — đổi mỗi cột ``number_next`` là
    KHÔNG đủ, số vẫn chạy tiếp từ chỗ cũ.
    """
    cur.execute("""
        SELECT DISTINCT s.id, s.code, s.prefix, s.implementation
        FROM ir_sequence s
        LEFT JOIN stock_picking_type pt ON pt.sequence_id = s.id
        WHERE pt.id IS NOT NULL OR s.code = ANY(%s)
        ORDER BY s.id
    """, (list(SEQUENCE_CODES),))
    rows = cur.fetchall()
    for seq_id, code, prefix, implementation in rows:
        cur.execute(
            "UPDATE ir_sequence SET number_next = 1 WHERE id = %s", (seq_id,))
        if implementation == "standard":
            pg_seq = "ir_sequence_%03d" % seq_id
            cur.execute("SELECT to_regclass(%s)", (pg_seq,))
            if cur.fetchone()[0] is not None:
                cur.execute(
                    sql.SQL("ALTER SEQUENCE {} RESTART WITH 1").format(
                        sql.Identifier(pg_seq)))
    # Dải số theo năm (LO/2026/) nằm ở bảng con — xoá để năm sau đếm lại từ đầu.
    cur.execute("""
        DELETE FROM ir_sequence_date_range
        WHERE sequence_id IN (SELECT id FROM ir_sequence WHERE code = ANY(%s))
    """, (list(SEQUENCE_CODES),))
    return [(prefix or code) for _id, code, prefix, _impl in rows]


def reset_derived_flags(cur):
    """Cờ dẫn xuất từ phiếu kho phải theo phiếu mà về mặc định.

    ``dl_sale_order.dlm_delivery_state`` là computed-stored đọc
    ``dlm_picking_ids`` — phiếu đã xoá thì mọi đơn đều "Chưa giao". Không có
    phiếu nào để trigger recompute, nên set thẳng ở đây.
    """
    cur.execute(
        "UPDATE dl_sale_order SET dlm_delivery_state = 'nothing' "
        "WHERE dlm_delivery_state IS DISTINCT FROM 'nothing'")
    return cur.rowcount


def main():
    parser = argparse.ArgumentParser(
        description="Xoá dữ liệu giao dịch kho, giữ cấu hình kho.")
    parser.add_argument("-d", "--database", help="Tên DB (mặc định: odoo.conf)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ đếm, không xoá gì.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Bỏ qua bước sao lưu DB.")
    parser.add_argument("--yes", action="store_true",
                        help="Không hỏi xác nhận.")
    args = parser.parse_args()

    params = read_conf()
    if args.database:
        params["dbname"] = args.database
    dbname = params["dbname"]

    print("")
    print("=" * 66)
    print("  XOÁ DỮ LIỆU GIAO DỊCH KHO — Dai Linh ERP")
    print("=" * 66)
    print("  DB: %s (%s@%s:%s)" % (dbname, params["user"], params["host"],
                                   params["port"]))
    print("")

    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()
    tables = [t for t in DELETE_ORDER if table_exists(cur, t)]
    total = show_summary(cur, tables)
    print("")

    if args.dry_run:
        print("  --dry-run: không xoá gì. Tổng %d dòng sẽ bị xoá." % total)
        cur.close()
        conn.close()
        return 0

    if not total:
        print("  Không có dữ liệu kho nào để xoá.")
        cur.close()
        conn.close()
        return 0

    if not args.yes:
        print("  ⚠️  Thao tác này KHÔNG hoàn tác được.")
        answer = input("  Gõ 'yes' để xoá %d dòng trên: " % total)
        if answer.strip() != "yes":
            print("  Đã huỷ.")
            cur.close()
            conn.close()
            return 1

    # Sao lưu TRƯỚC khi mở transaction xoá — CREATE DATABASE cần kết nối riêng
    # và không chạy được bên trong transaction.
    if not args.no_backup:
        cur.close()
        conn.close()
        print("")
        print("  [1/3] Sao lưu DB...")
        backup_name = backup(params, dbname)
        print("        ✓ Bản sao: %s" % backup_name)
        print("        (khôi phục: DROP DATABASE %s; "
              "CREATE DATABASE %s TEMPLATE %s;)" % (dbname, dbname, backup_name))
        conn = psycopg2.connect(**params)
        conn.autocommit = False
        cur = conn.cursor()
    else:
        backup_name = None
        print("")
        print("  [1/3] Bỏ qua sao lưu (--no-backup).")

    print("  [2/3] Xoá dữ liệu...")
    deleted = purge(cur, tables)
    for table, rows in deleted.items():
        if rows:
            print("        - %-24s %d" % (table, rows))

    print("  [3/3] Reset số thứ tự + cờ dẫn xuất...")
    prefixes = reset_sequences(cur)
    print("        - sequence về 1: %s" % ", ".join(sorted(prefixes)))
    orders = reset_derived_flags(cur)
    print("        - đơn bán reset cờ giao hàng: %d" % orders)

    conn.commit()

    print("")
    remaining = show_summary(cur, tables)
    cur.close()
    conn.close()

    print("")
    print("=" * 66)
    print("  ✅ XONG. Còn lại %d dòng." % remaining)
    print("=" * 66)
    print("  → Start lại phiên debug VS Code, mở http://127.0.0.1:8069")
    print("  → Kho DL, cây vị trí và 11 loại hoạt động vẫn nguyên.")
    if backup_name:
        print("  → Xoá bản sao khi không cần: DROP DATABASE %s;" % backup_name)
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
