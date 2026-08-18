#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Xin cert Let's Encrypt lần đầu rồi bật HTTPS.
#  Chạy 1 lần duy nhất. Gia hạn về sau do service `certbot` tự lo.
#
#  Điều kiện: DOMAIN trong .env đã trỏ A record về IP VPS, port 80 mở.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .env ]] || { echo "✗ Thiếu file .env (cp .env.example .env rồi sửa)"; exit 1; }
set -a; source .env; set +a

: "${DOMAIN:?Chưa đặt DOMAIN trong .env}"
: "${LETSENCRYPT_EMAIL:?Chưa đặt LETSENCRYPT_EMAIL trong .env}"

STAGING="${STAGING:-0}"
staging_arg=""
if [[ "$STAGING" == "1" ]]; then
    staging_arg="--staging"
    echo "⚠  Chế độ STAGING: cert sinh ra KHÔNG hợp lệ, chỉ để kiểm tra quy trình."
fi

echo "▸ Bước 1/4 — bật nginx ở chế độ HTTP để phục vụ ACME challenge"
mkdir -p nginx/active
cp nginx/templates-http/default.conf.template nginx/active/default.conf.template
docker compose up -d --force-recreate nginx

echo "▸ Bước 2/4 — chờ nginx trả lời trên port 80"
for i in $(seq 1 30); do
    # Chỉ cần nginx trả về BẤT KỲ mã HTTP nào là đủ (Odoo có thể đang 404/500,
    # không ảnh hưởng tới đường /.well-known/).
    if curl -s -o /dev/null --max-time 3 http://localhost/; then
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "✗ nginx không lên sau 60s. Xem: docker compose logs nginx"
        exit 1
    fi
    sleep 2
done

echo "▸ Bước 3/4 — xin cert cho $DOMAIN"
docker compose run --rm --entrypoint certbot certbot \
    certonly --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$LETSENCRYPT_EMAIL" \
    --agree-tos --no-eff-email --non-interactive \
    $staging_arg

echo "▸ Bước 4/4 — chuyển nginx sang cấu hình HTTPS"
cp nginx/templates-ssl/default.conf.template nginx/active/default.conf.template
docker compose up -d --force-recreate nginx
docker compose up -d certbot

echo
echo "✓ Xong. Mở https://$DOMAIN"
if [[ "$STAGING" == "1" ]]; then
    echo "  Đang dùng cert staging. Đổi STAGING=0 trong .env, xoá cert cũ rồi chạy lại:"
    echo "    docker compose run --rm --entrypoint certbot certbot delete --cert-name $DOMAIN"
    echo "    ./init-letsencrypt.sh"
fi
