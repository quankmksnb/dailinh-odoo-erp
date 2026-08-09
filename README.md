# DLM-ERP — Hệ thống ERP tùy chỉnh trên Odoo 17 cho Đại Linh

Dự án xây dựng các module Odoo 17 Community cho công ty cơ khí **Đại Linh**, giải quyết hai nghiệp vụ cốt lõi Phase 1:

- **IP-01** — Lập báo giá dựa trên BOM và tính giá tham số (parametric pricing)
- **IP-02** — Phê duyệt báo giá nhiều cấp có điều kiện và SLA

---

## Cấu trúc thư mục

```
dailinh-odoo-erp/
├── dlm-erp/            ← addons path (mount vào Odoo) — chỉ code trong đây
│   ├── dl_base/        ← Nền: groups (RBAC), rail/menu, home, SCSS token dùng chung
│   ├── dl_partner/     ← Khách hàng & Nhà cung cấp (kế thừa res.partner)
│   ├── dl_config/      ← Cấu hình báo giá, quản trị user, RBAC UI, đơn vị tính
│   ├── dl_product/     ← Sản phẩm + vật tư hợp nhất, giá NCC, đo lường
│   ├── dl_technical/   ← RFQ kỹ thuật, BOM, BOM tham số, bản vẽ, bán thành phẩm
│   ├── dl_inventory/   ← Xuất nhập kho (mỏng — menu + view stock.picking)
│   ├── dl_sale/        ← Báo giá, phê duyệt, đơn bán hàng, engine tính giá (IP-01/02)
│   └── dl_demo/        ← CHỈ DEV: seed dữ liệu giao dịch phủ mọi trạng thái
├── docs/               ← Tài liệu phân tích nghiệp vụ + tài liệu doanh nghiệp thật
├── scripts/            ← Tiện ích dev (reset_demo_db.ps1 — dựng lại DB demo sạch)
├── odoo-17.0/          ← Odoo Community source (không commit, không sửa)
├── venv/               ← Python virtualenv (không commit)
└── odoo.conf           ← Cấu hình server local (DB, port 8069)
```

---

## Modules

Thứ tự trong bảng cũng là **thứ tự cài đặt** (chép từ `depends` trong từng `__manifest__.py`).

| Module         | Phụ thuộc module DL                                   | Vai trò                                                                                            |
| -------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `dl_base`      | _(không)_                                             | Nền chung: 7 nhóm quyền, menu rail + home theo vai trò, model `dl.rbac.feature`, design token SCSS |
| `dl_partner`   | `dl_base`                                             | Khách hàng / NCC trên `res.partner`, phân loại tự động nhóm khách                                  |
| `dl_config`    | `dl_base`                                             | Chính sách giá (`dl.pricing.*`), ma trận phê duyệt, quản trị user, đơn vị tính                     |
| `dl_product`   | `dl_base`, `dl_partner`                               | `product.product` hợp nhất (thành phẩm + vật tư), bảng giá NCC, quy cách đo lường                  |
| `dl_technical` | `dl_base`, `dl_partner`, `dl_product`, `dl_config`    | RFQ kỹ thuật, BOM & BOM mẫu tham số, bản vẽ, bán thành phẩm                                        |
| `dl_inventory` | `dl_base`, `dl_partner`, `dl_product`                 | Xuất nhập kho (đang ở mức khung)                                                                   |
| `dl_sale`      | `dl_base`, `dl_partner`, `dl_product`, `dl_technical` | Báo giá, hòm phê duyệt, đơn bán hàng, engine tính giá, xuất Word/PDF                               |
| `dl_demo`      | cả 7 module trên                                      | Dữ liệu demo — **không cài trên môi trường thật**                                                  |

### Model chính

| Model                                                                                                 | Module         | Mô tả                                                                        |
| ----------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------- |
| `dl.quotation` / `dl.quotation.line`                                                                  | `dl_sale`      | Báo giá và dòng báo giá                                                      |
| `dl.quotation.price.component`                                                                        | `dl_sale`      | Bóc tách cấu phần giá (vật tư / công đoạn / markup)                          |
| `dl.quotation.pricing.service`                                                                        | `dl_sale`      | Engine tính giá & tạo báo giá từ RFQ (`AbstractModel`, tách để test độc lập) |
| `dl.sale.order` / `dl.sale.order.line`                                                                | `dl_sale`      | Đơn bán hàng sinh từ báo giá đã chốt                                         |
| `dl.quotation.request` (+ `.line`)                                                                    | `dl_technical` | RFQ — yêu cầu báo giá do Sales nhập, Kỹ thuật xử lý                          |
| `dl.bom` / `dl.bom.line` / `dl.bom.operation.line`                                                    | `dl_technical` | Định mức vật tư và công đoạn                                                 |
| `dl.bom.template` (+ `.param`)                                                                        | `dl_technical` | BOM mẫu tham số — nhập D×R×C sinh ra dòng vật tư                             |
| `dl.drawing`                                                                                          | `dl_technical` | Bản vẽ kỹ thuật                                                              |
| `dl.pricing.profit.rule`, `.discount.rule`, `.waste.rule`, `.operation.rule`, `.cost.adjustment.rule` | `dl_config`    | Chính sách giá có phiên bản (revision / apply / approval)                    |
| `dl.pricing.approval.matrix` / `.request`                                                             | `dl_config`    | Ma trận phê duyệt theo ngưỡng + phiếu phê duyệt                              |
| `dl.rbac.feature`                                                                                     | `dl_base`      | Màn phân quyền theo tính năng                                                |

### Vòng đời chính

```
RFQ         new → processing → returned ⇄ supplemented → confirmed → quoted
                                                                   ↘ cancelled

Báo giá     draft → approved (duyệt nội bộ) → sent → accepted → ordered
                                              ↓        ↓
                            revision_requested / rejected / expired / superseded / cancelled

BOM         draft → confirmed → locked → archived
```

---

## Yêu cầu cài đặt

| Thành phần     | Phiên bản | Ghi chú              |
| -------------- | --------- | -------------------- |
| Python         | 3.10+     |                      |
| Odoo Community | 17.0      |                      |
| PostgreSQL     | 15+       |                      |
| `python-docx`  | mới nhất  | Xuất báo giá `.docx` |
| `reportlab`    | 4.x       | Xuất báo giá PDF     |

> **Không cần `wkhtmltopdf`.** Việc xuất Word/PDF làm bằng Python thuần
> (`python-docx` + `reportlab`, nhúng sẵn font Montserrat của Odoo để đúng tiếng Việt).

---

## Cài đặt local (Windows)

**1. Clone repo**

```bash
git clone https://github.com/quankmksnb/dailinh-odoo-erp.git
cd dailinh-odoo-erp
git checkout develop
```

**2. Tạo virtualenv và cài thư viện**

```bash
python -m venv venv
venv\Scripts\activate
pip install -r odoo-17.0/requirements.txt
pip install python-docx reportlab
```

**3. Tạo database PostgreSQL**

```bash
createdb -U odoo dlm_dev
```

**4. Khởi động Odoo, init module**

```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev -i dl_base,dl_partner,dl_product,dl_config,dl_technical,dl_inventory,dl_sale --dev=all
```

Muốn có sẵn dữ liệu để test thì thêm `,dl_demo` vào cuối `-i`.

**5. Truy cập**

```
http://127.0.0.1:8069
```

Sau lần đầu init, chạy bình thường (bỏ `-i`):

```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev --dev=all
```

**Dựng lại DB demo sạch** (xoá và tạo lại từ đầu — xem [`scripts/README.md`](scripts/README.md)):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reset_demo_db.ps1
```

> Nếu đang chạy Odoo qua trình debug của VS Code thì **Stop debug trước** khi reset DB —
> trình debug tự khởi động lại tiến trình, kill tay sẽ sinh nhiều server cùng bind port 8069.

---

## Phân quyền

Định nghĩa tại `dl_base/security/groups.xml`.

| Group           | Định danh XML                    | Mô tả                                                    |
| --------------- | -------------------------------- | -------------------------------------------------------- |
| CEO             | `dl_base.dl_group_ceo`           | Phê duyệt báo giá, cấu hình kinh doanh, override margin  |
| Admin/IT        | `dl_base.dl_group_admin`         | Quản trị hệ thống, cấu hình kỹ thuật, tạo user           |
| BA/Sales        | `dl_base.dl_group_ba`            | Tạo/sửa RFQ và báo giá, xem lịch sử phê duyệt            |
| Kỹ thuật        | `dl_base.dl_group_tech`          | Xử lý RFQ, BOM, bản vẽ, vật tư — không thấy giá bán cuối |
| Trưởng phòng KD | `dl_base.dl_group_sales_manager` | Phê duyệt báo giá theo ngưỡng, xem giá tham khảo         |
| Mua hàng        | `dl_base.dl_group_purchasing`    | Sở hữu giá mua: NCC, bảng giá NCC, giá vốn               |
| Kế toán nội bộ  | `dl_base.dl_group_accountant`    | Chỉ-xem giá                                              |

Sau khi đăng nhập, người dùng được đưa thẳng vào màn nghiệp vụ chính của vai trò mình.

---

## Quy trình phát triển (cho team)

### Nhánh làm việc

```
develop                ← nhánh tích hợp, base của mọi PR
feature/[tên]-[người]  ← nhánh cá nhân (vd feature/quotation-approval-quannm)
```

### Tạo branch và PR

```bash
git checkout develop
git pull origin develop
git checkout -b feature/A1-them-truong-quotation

git push origin feature/A1-them-truong-quotation
# Tạo PR vào develop trên GitHub
```

### Commit message convention

```
feat(A1): thêm validity_date, discount vào dl.quotation
fix(B3): sửa compute subtotal bị lỗi khi qty = 0
refactor(D3): tách form quotation thành 2 tab notebook
```

### Update module sau khi sửa code

```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev -u dl_sale --dev=all
```

Sửa Python hoặc XML đều phải `-u <module>` để nạp lại. Sửa nhiều module thì
liệt kê cách nhau bởi dấu phẩy.

### Chạy test

```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev -u dl_technical --test-enable --stop-after-init
```

Hiện có test ở `dl_technical/tests/` và `dl_sale/tests/`.

---

## Trạng thái Phase 1

- [x] `dl_base` — RBAC, menu rail, home theo vai trò, màn phân quyền
- [x] `dl_partner` — Khách hàng / NCC, phân nhóm khách tự động
- [x] `dl_product` — Sản phẩm + vật tư hợp nhất, bảng giá NCC có duyệt
- [x] `dl_config` — Chính sách giá có phiên bản, ma trận phê duyệt, quản trị user
- [x] `dl_technical` — RFQ, BOM, bản vẽ, BOM mẫu tham số (D×R×C)
- [x] `dl_sale` — Engine tính giá từ BOM, vòng đời báo giá, đơn bán hàng, xuất Word/PDF
- [x] Luồng phê duyệt nhiều cấp (IP-02) theo ngưỡng giá trị / chiết khấu / giá sàn
- [x] Record rules + phân quyền dữ liệu theo vai trò
- [ ] SLA + escalation + notification (mới có nền: đếm ngày chờ, activity)
- [ ] `dl_inventory` — mới ở mức khung, chưa có model nghiệp vụ
- [ ] Test cho `dl_config` (rule giá) và `dl_product` (công thức vật tư)

---

## Tài liệu tham khảo

- Tài liệu phân tích nghiệp vụ và thiết kế: thư mục [`docs/`](docs/) — xem [`docs/README.md`](docs/README.md)
- Dữ liệu thật của doanh nghiệp: `docs/tài liệu doanh nghiệp/`
- [Odoo 17 Developer Documentation](https://www.odoo.com/documentation/17.0/developer.html)
- [OWL Framework](https://github.com/odoo/owl)
