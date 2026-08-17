# Triển khai DLM-ERP lên VPS (Ubuntu + Docker Compose)

Stack: `nginx` (TLS, reverse proxy) → `odoo:17.0` (+ custom addons `dlm-erp/`) → `postgres:16`.
Tất cả chạy trong Docker Compose trên đúng 1 VPS. Postgres **không** publish port ra host.

```
deploy/
├── docker-compose.yml          stack chính
├── Dockerfile                  odoo:17.0 + python-docx + font
├── requirements.txt
├── .env.example        →  .env         (secrets, KHÔNG commit)
├── odoo.conf.template  →  odoo.conf    (config prod, KHÔNG commit)
├── nginx/
│   ├── templates-http/         cấu hình HTTP dùng lúc xin cert
│   ├── templates-ssl/          cấu hình HTTPS dùng lúc chạy thật
│   └── active/                 bản đang dùng (do script copy vào, KHÔNG commit)
├── init-letsencrypt.sh         xin cert lần đầu + bật HTTPS
├── update.sh                   deploy code mới + upgrade module
├── backup.sh                   dump DB + filestore
└── restore.sh                  khôi phục
```

---

## 0. Chuẩn bị trước khi SSH

- **DNS**: tạo bản ghi `A` cho domain (vd `erp.dailinh.vn`) trỏ về IP VPS. Chờ propagate,
  kiểm tra bằng `dig +short erp.dailinh.vn` — phải ra đúng IP. Làm trước, vì
  Let's Encrypt giới hạn 5 lần xin cert thất bại/giờ cho mỗi domain.
- **Postgres native**: bạn đã cài `postgresql` bằng apt. Stack này dùng Postgres trong
  container nên bản native chỉ tổ ăn RAM → tắt ở bước 1.

---

## 1. Cài đặt nền trên VPS

```bash
ssh root@<IP-VPS>

# ── Tắt Postgres native (Postgres sẽ chạy trong Docker) ──
systemctl disable --now postgresql || true

# ── Cập nhật + tiện ích ──
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw

# ── Docker Engine + Compose plugin (repo chính chủ, KHÔNG dùng docker.io của Ubuntu) ──
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker compose version    # phải ra v2.x

# ── Swap 4 GB: Odoo hay phình lúc build asset, hết RAM là OOM-kill worker ──
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf

# ── Firewall ──
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

> **Lưu ý UFW + Docker**: Docker ghi thẳng vào iptables nên port do Docker publish
> có thể lọt qua UFW. Ở đây chỉ nginx publish 80/443 — đúng thứ ta muốn mở — nên
> không có rò rỉ. Tuyệt đối đừng thêm `ports:` cho `db` hay `odoo`.

---

## 2. Lấy code về

```bash
git clone https://github.com/quankmksnb/dailinh-odoo-erp.git /opt/dailinh-odoo-erp
cd /opt/dailinh-odoo-erp
git checkout main
cd deploy
```

Repo private thì dùng Personal Access Token:
`git clone https://<user>:<token>@github.com/quankmksnb/dailinh-odoo-erp.git /opt/dailinh-odoo-erp`

Thư mục `odoo-17.0/` bị gitignore và **không cần** — Odoo core nằm trong image.

```bash
# Script viết trên Windows có thể dính CRLF → bash báo "bad interpreter"
sed -i 's/\r$//' *.sh
chmod +x *.sh
```

---

## 3. Điền secrets

```bash
cp .env.example .env
openssl rand -base64 24        # copy kết quả làm POSTGRES_PASSWORD
nano .env                      # điền DOMAIN, LETSENCRYPT_EMAIL, POSTGRES_PASSWORD
chmod 600 .env
```

Lần đầu nên đặt `STAGING=1` để chạy thử toàn bộ quy trình cert mà không đốt quota.

---

## 4. Build image

```bash
docker compose build          # ~2-3 phút
```

---

## 5. Tạo file cấu hình Odoo

```bash
cp odoo.conf.template odoo.conf

# Sinh hash cho master password (mật khẩu không hiện lên màn hình, không vào history)
read -rsp "Master password: " MP; echo
docker compose run --rm -e MP="$MP" --entrypoint python3 odoo -c \
  "import os;from passlib.context import CryptContext;print(CryptContext(['pbkdf2_sha512']).hash(os.environ['MP']))"
unset MP
```

Copy chuỗi `$pbkdf2-sha512$...` vào dòng `admin_passwd =` trong `odoo.conf`, rồi:

```bash
chmod 644 odoo.conf      # container chạy bằng user odoo (uid 101), cần đọc được
```

---

## 6. Khởi tạo database

```bash
docker compose run --rm odoo odoo \
  -d dlm_prod \
  -i dl_base,dl_config,dl_partner,dl_product,dl_technical,dl_sale,dl_inventory,dl_purchase \
  --without-demo=all --stop-after-init --workers=0 --max-cron-threads=0 --no-http
```

Chạy 3–6 phút. Kết thúc phải thấy `Modules loaded.` và **không có** dòng `ERROR`.
Module `dl_demo` cố ý không cài — đó là dữ liệu demo.

> Muốn nạp sẵn tiếng Việt: thêm `--load-language=vi_VN` vào lệnh trên.

---

## 7. Bật HTTPS

```bash
./init-letsencrypt.sh
```

Script tự làm: nginx HTTP → xin cert qua ACME webroot → đổi sang nginx HTTPS.

Nếu bạn để `STAGING=1`, sau khi thấy chạy trót lọt thì đổi `STAGING=0` trong `.env` và:

```bash
docker compose run --rm --entrypoint certbot certbot delete --cert-name <DOMAIN>
./init-letsencrypt.sh
```

---

## 8. Chạy toàn bộ stack

```bash
docker compose up -d
docker compose ps             # cả 4 service phải Up, db phải healthy
docker compose logs -f odoo
```

Mở `https://<DOMAIN>` → đăng nhập `admin` / `admin` → **đổi mật khẩu ngay lập tức**
(Settings → Users → Administrator).

---

## 9. Backup tự động

```bash
mkdir -p /opt/dlm-backup
./backup.sh                   # chạy tay 1 lần cho chắc
crontab -e
```

Thêm:

```cron
0 2 * * * /opt/dailinh-odoo-erp/deploy/backup.sh >> /var/log/dlm-backup.log 2>&1
```

Backup nằm cùng máy với DB thì mất VPS là mất sạch. Bật thêm ít nhất một trong hai:

- **Snapshot tự động của nhà cung cấp VPS** (bật trong panel).
- **Offsite bằng rclone**: `apt install rclone && rclone config` (Backblaze B2 rẻ nhất),
  rồi bỏ comment 2 dòng cuối `backup.sh`.

Và **diễn tập restore 1 lần** trên DB tạm — backup chưa test thì coi như chưa có.

---

## Vận hành hằng ngày

| Việc | Lệnh |
|---|---|
| Deploy code mới (toàn bộ) | `./update.sh` |
| Deploy code mới (1 vài module) | `./update.sh dl_sale dl_product` |
| Xem log | `docker compose logs -f odoo` |
| Khởi động lại Odoo | `docker compose restart odoo` |
| Vào psql | `docker compose exec db psql -U odoo -d dlm_prod` |
| Vào odoo shell | `docker compose run --rm odoo odoo shell -d dlm_prod` |
| Backup thủ công | `./backup.sh` |
| Khôi phục | `./restore.sh <db.dump> <filestore.tar.gz>` |
| Dọn image cũ | `docker image prune -f` |

---

## Sự cố thường gặp

**`Database dlm_prod does not exist`** — chưa chạy bước 6, hoặc `dbfilter` trong
`odoo.conf` không khớp tên DB.

**Trang trắng / CSS vỡ** — asset chưa build lại sau khi đổi code:
`docker compose run --rm odoo odoo -d dlm_prod -u web --stop-after-init --workers=0`

**Đăng nhập xong bị đá ra, hoặc redirect về `http://`** — `proxy_mode` chưa `True`,
hoặc nginx thiếu header `X-Forwarded-Proto`.

**Chat/thông báo không realtime** — websocket không tới được `odoo:8072`,
kiểm tra block `location /websocket` trong `nginx/active/default.conf.template`.

**Certbot lỗi `Connection refused` / `Timeout`** — DNS chưa trỏ đúng IP, hoặc UFW
chặn port 80. Kiểm tra: `dig +short <DOMAIN>` và `ufw status`.

**Odoo bị OOM-kill (log có `Memory limit exceeded`)** — giảm `workers` xuống 2
trong `odoo.conf` rồi `docker compose restart odoo`.

**`pip install` lỗi `externally-managed-environment` lúc build** — sửa `Dockerfile`,
đổi `--break-system-packages` thành cách tạo venv, hoặc dùng
`pip3 install --no-cache-dir -r ... --root-user-action=ignore`.
