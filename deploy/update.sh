#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Deploy code mới lên prod.
#    ./update.sh                    → pull code, upgrade TẤT CẢ module dl_*
#    ./update.sh dl_sale dl_product → chỉ upgrade module chỉ định (nhanh hơn nhiều)
#
#  Luôn backup trước khi upgrade: upgrade module có thể đổi schema, không rollback được.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

set -a; source .env; set +a
DB_NAME="${DB_NAME:-dlm_prod}"

ALL_MODULES="dl_base,dl_config,dl_partner,dl_product,dl_technical,dl_sale,dl_inventory,dl_purchase"
if [[ $# -gt 0 ]]; then
    MODULES="$(IFS=,; echo "$*")"
else
    MODULES="$ALL_MODULES"
fi

echo "▸ backup trước khi upgrade"
./backup.sh

echo "▸ pull code mới"
git -C .. pull --ff-only

echo "▸ rebuild image (nếu requirements.txt / Dockerfile đổi)"
docker compose build odoo

echo "▸ dừng odoo và upgrade module: $MODULES"
docker compose stop odoo
docker compose run --rm odoo \
    odoo -d "$DB_NAME" -u "$MODULES" \
    --stop-after-init --workers=0 --max-cron-threads=0 --no-http

echo "▸ khởi động lại"
docker compose up -d odoo

echo "✓ Xong. Theo dõi log: docker compose logs -f odoo"
