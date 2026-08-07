"""Drop + create lại một database PostgreSQL sạch (dùng cho reset_demo_db.ps1).

Portable hơn dropdb/createdb (không cần PG client trên PATH) — dùng psycopg2 vốn
đã có sẵn trong venv Odoo. Ngắt mọi kết nối cũ trước khi drop.

Cách gọi:
    python _recreate_db.py <host> <port> <user> <password> <dbname>
"""

import sys

import psycopg2
from psycopg2 import sql


def main():
    if len(sys.argv) != 6:
        sys.stderr.write(
            "Cách dùng: python _recreate_db.py <host> <port> <user> <password> <dbname>\n"
        )
        return 2

    host, port, user, password, dbname = sys.argv[1:6]

    # Kết nối vào DB hệ thống 'postgres' để thao tác DROP/CREATE trên dbname.
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname="postgres"
    )
    conn.autocommit = True
    try:
        cur = conn.cursor()
        # Ngắt các kết nối đang mở tới dbname (nếu không sẽ không DROP được).
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid();",
            (dbname,),
        )
        cur.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
        )
        cur.execute(
            sql.SQL(
                "CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'"
            ).format(sql.Identifier(dbname))
        )
        cur.close()
    finally:
        conn.close()

    print("Da tao lai DB sach: %s" % dbname)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
