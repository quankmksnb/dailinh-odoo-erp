#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Backup DLM-ERP: dump Postgres + filestore.
#  Cả hai PHẢI đi cùng nhau — thiếu filestore thì attachment/ảnh mất hết.
#
#  Cron gợi ý (2h sáng hằng ngày):
#    0 2 * * * /opt/dailinh-odoo-erp/deploy/backup.sh >> /var/log/dlm-backup.log 2>&1
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

set -a; source .env; set +a

DB_NAME="${DB_NAME:-dlm_prod}"
DEST="${BACKUP_DIR:-/opt/dlm-backup}"
KEEP="${BACKUP_KEEP_DAYS:-7}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$DEST"

echo "[$(date '+%F %T')] ▸ dump database $DB_NAME"
docker compose exec -T db \
    pg_dump -U "$POSTGRES_USER" -Fc --no-owner "$DB_NAME" \
    > "$DEST/db_${STAMP}.dump"

echo "[$(date '+%F %T')] ▸ dump filestore"
docker compose exec -T odoo \
    tar czf - -C /var/lib/odoo . \
    > "$DEST/filestore_${STAMP}.tar.gz"

# Dump rỗng nghĩa là backup hỏng — báo lỗi thay vì im lặng ghi đè bản tốt.
for f in "$DEST/db_${STAMP}.dump" "$DEST/filestore_${STAMP}.tar.gz"; do
    if [[ ! -s "$f" ]]; then
        echo "✗ $f rỗng — backup THẤT BẠI"
        exit 1
    fi
done

echo "[$(date '+%F %T')] ▸ xoá bản cũ hơn $KEEP ngày"
find "$DEST" -maxdepth 1 -name 'db_*.dump'          -mtime "+$KEEP" -delete
find "$DEST" -maxdepth 1 -name 'filestore_*.tar.gz' -mtime "+$KEEP" -delete

echo "[$(date '+%F %T')] ✓ xong: $(du -sh "$DEST" | cut -f1) tại $DEST"

# ── Offsite (khuyến nghị) ────────────────────────────────────
# Backup nằm cùng máy với DB thì mất VPS là mất sạch. Cài rclone,
# `rclone config` một remote (Backblaze B2 / Google Drive / S3) rồi bỏ comment:
#
# rclone copy "$DEST/db_${STAMP}.dump"           b2:dlm-erp-backup/ --no-traverse
# rclone copy "$DEST/filestore_${STAMP}.tar.gz"  b2:dlm-erp-backup/ --no-traverse
