# DLM-ERP — Hệ thống ERP tùy chỉnh trên Odoo 17 cho Đại Linh

Dự án xây dựng các module Odoo 17 cho công ty cơ khí **Đại Linh**, giải quyết hai nghiệp vụ cốt lõi Phase 1:

- **IP-01** — Lập báo giá dựa trên BOM và tính giá tham số (parametric pricing)
- **IP-02** — Phê duyệt báo giá nhiều cấp có điều kiện và SLA

---

## Cấu trúc thư mục

```
dailinh-odoo-erp/
├── dlm-erp/                  ← addons path (mount vào Odoo)
│   ├── dl_base/              ← Module gốc: groups, home dashboard
│   └── dl_sale/              ← CRM & Báo giá: customer, supplier, quotation
├── odoo-17.0/                ← Odoo Community source (không commit)
├── venv/                     ← Python virtualenv (không commit)
└── odoo.conf                 ← Cấu hình server local
```

---

## Modules

### `dl_base` — DLM-ERP Base

Module nền, cần cài trước tất cả module khác.

**Chức năng:**
- Định nghĩa 4 nhóm quyền: `CEO`, `Admin/IT`, `BA/Sales`, `Kỹ thuật`
- Home dashboard (OWL component) với 5 card trỏ đến các module Phase 1
- Menu gốc `DLM-ERP` và 5 menu con: CRM & Báo giá / Kỹ thuật / Vật tư / Báo cáo / Cấu hình

**Phụ thuộc:** `base`, `web`

---

### `dl_sale` — CRM & Báo giá

Module nghiệp vụ chính, xử lý IP-01 và IP-02.

**Models:**

| Model | Mô tả |
|---|---|
| `res.partner` (extend) | Thêm `is_dlm_customer`, `is_dlm_supplier`, `customer_type` (cá nhân/doanh nghiệp/đại lý), `tax_code` |
| `dl.quotation` | Header báo giá: khách hàng, ngày, trạng thái, tổng tiền, ghi chú. Tích hợp `mail.thread` |
| `dl.quotation.line` | Dòng báo giá: mô tả, SL, đơn giá, thành tiền |

**Trạng thái báo giá hiện tại:** `draft → sent → approved / rejected`

**Phụ thuộc:** `dl_base`, `mail`

---

## Yêu cầu cài đặt

| Thành phần | Phiên bản |
|---|---|
| Python | 3.10+ |
| Odoo Community | 17.0 |
| PostgreSQL | 15+ |
| wkhtmltopdf | 0.12.6 (để in PDF) |

---

## Cài đặt local (Windows)

> Xem file `odoo.conf` để biết cấu hình DB và port đang dùng.

**1. Clone repo**
```bash
git clone https://github.com/quankmksnb/dailinh-odoo-erp.git
cd dailinh-odoo-erp
git checkout feature/init-project
```

**2. Tạo virtualenv và cài thư viện**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r odoo-17.0/requirements.txt
```

**3. Tạo database PostgreSQL**
```bash
createdb -U odoo dlm_dev
```

**4. Khởi động Odoo, init module**
```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev -i dl_base,dl_sale --dev=all
```

**5. Truy cập**
```
http://127.0.0.1:8069
```

Sau lần đầu init, chạy bình thường (bỏ `-i`):
```bash
python odoo-17.0/odoo-bin -c odoo.conf -d dlm_dev --dev=all
```

---

## Phân quyền

| Group | Định danh XML | Mô tả |
|---|---|---|
| CEO | `dl_base.dl_group_ceo` | Phê duyệt báo giá, cấu hình kinh doanh, override margin |
| Admin/IT | `dl_base.dl_group_admin` | Quản trị hệ thống, cấu hình kỹ thuật, tạo user |
| BA/Sales | `dl_base.dl_group_ba` | Tạo và chỉnh sửa báo giá, xem lịch sử phê duyệt |
| Kỹ thuật | `dl_base.dl_group_tech` | Quản lý BOM, bản vẽ, vật tư — không thấy giá bán cuối |

---

## Quy trình phát triển (cho team)

### Nhánh làm việc

```
main               ← production-ready, merge qua PR từ feature/init-project
feature/init-project ← nhánh tích hợp Phase 1 (đây là nhánh làm việc chính)
feature/[mã]-[tên]  ← nhánh cá nhân cho từng bài tập
```

### Tạo branch và PR

```bash
# Tạo branch từ feature/init-project
git checkout feature/init-project
git pull origin feature/init-project
git checkout -b feature/A1-them-truong-quotation

# Làm xong, đẩy lên
git push origin feature/A1-them-truong-quotation
# Tạo PR vào feature/init-project trên GitHub
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

---

## Bài tập thực hành

File tracking: `DLM_BaiTap_ThucHanh.xlsx` (xem trong thư mục tài liệu)

| Nhóm | Bài | Nội dung tóm tắt | Tuần |
|---|---|---|---|
| A — Model & Fields | A1–A4 | Thêm trường quotation, model sản phẩm, liên kết product | 1–2 |
| B — Business Logic | B1–B4 | Sequence, constraint, BOM + state machine | 2–3 |
| C — Phân quyền | C1–C3 | Groups, model access, record rules | 1–4 |
| D — Views | D1–D4 | Kanban, search/filter, form nâng cao, approval dashboard | 1–4 |
| E — Nâng cao | E1–E2 | Tính giá từ BOM, cảnh báo giá hết hạn | 4–5 |

---

## Roadmap Phase 1

- [x] `dl_base` — Home dashboard, groups, menu structure
- [x] `dl_sale` — Customer/Supplier (res.partner extend), Quotation skeleton
- [ ] BOM mẫu theo nhóm sản phẩm (`dl.bom`, `dl.bom.line`)
- [ ] Tính giá tham số (parametric pricing engine)
- [ ] Luồng phê duyệt nhiều cấp (IP-02): pending → cấp 1 → CEO
- [ ] Record rules phân quyền dữ liệu
- [ ] Màn hình phê duyệt đầy đủ căn cứ (IP-02 §6.8)
- [ ] SLA + escalation + notification

---

## Tài liệu tham khảo

- Tài liệu phân tích nghiệp vụ: `Phan_tich_sau_IP01_IP02_v2.docx`
- [Odoo 17 Developer Documentation](https://www.odoo.com/documentation/17.0/developer.html)
- [OWL Framework](https://github.com/odoo/owl)
