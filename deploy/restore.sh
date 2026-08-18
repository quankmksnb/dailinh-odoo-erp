#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Khôi phục từ backup.
#    ./restore.sh /opt/dlm-backup/db_20260817_020000.dump \
#                 /opt/dlm-backup/filestore_20260817_020000.tar.gz
#
#  XOÁ database dlm_prod hiện tại. Chỉ chạy khi đã chắc chắn.
#  Nên diễn tập restore ít nhất 1 lần — backup chưa test = chưa có backup.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

set -a; source .env; set +a

DUMP="${1:?Thiếu đường dẫn file .dump}"
FILESTORE="${2:?Thiếu đường dẫn file filestore .tar.gz}"
DB_NAME="${DB_NAME:-dlm_prod}"

[[ -s "$DUMP" ]]      || { echo "✗ Không đọc được $DUMP"; exit 1; }
[[ -s "$FILESTORE" ]] || { echo "✗ Không đọc được $FILESTORE"; exit 1; }

read -rp "Sẽ XOÁ database '$DB_NAME' và ghi đè filestore. Gõ 'yes' để tiếp tục: " ok
[[ "$ok" == "yes" ]] || { echo "Huỷ."; exit 1; }

echo "▸ dừng odoo (giải phóng connection tới DB)"
docker compose stop odoo

echo "▸ tạo lại database $DB_NAME"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $DB_NAME;"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE $DB_NAME OWNER $POSTGRES_USER TEMPLATE template0;"

echo "▸ nạp dump"
docker compose exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$DB_NAME" --no-owner --role="$POSTGRES_USER" < "$DUMP"

echo "▸ nạp filestore"
docker compose run --rm -T --entrypoint sh odoo \
    -c 'rm -rf /var/lib/odoo/* && tar xzf - -C /var/lib/odoo' < "$FILESTORE"

echo "▸ khởi động lại"
docker compose up -d odoo

echo "✓ Xong. Kiểm tra: docker compose logs -f odoo"
