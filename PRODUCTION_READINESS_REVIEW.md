# BÁO CÁO ĐÁNH GIÁ SẴN SÀNG PRODUCTION — DLM-ERP (Odoo 17 CE)

**Ngày:** 2026-08-17 · **Phạm vi:** `dlm-erp/` (9 module) + `odoo.conf` + `scripts/`
**Phương pháp:** phân tích tĩnh source code thực tế (AST + grep + đọc file). Không suy đoán.

> ⚠️ **Giới hạn:** chưa chạy test suite (373 test) và chưa thử deploy thật.

---

## 0. Số liệu đo được

| Chỉ số | Giá trị |
|---|---|
| Python production (không tính test) | **~24.500 LOC** |
| Test | **373 test method** / 34 file |
| XML | ~15.100 LOC · **JS/SCSS/OWL** ~13.100 LOC |
| Model tự định nghĩa (`_name`) | **59** · kế thừa 23 |
| Field | 759 (M2O **143** · O2M 31 · M2M 19) · có index **36** |
| ACL rows | **308** · `ir.rule` **24** · `sudo()` **222** |
| Controller | **2** · `ir.cron` 3 · migration 25 |

LOC theo module: `dl_technical` 6442 · `dl_inventory` 6081 · `dl_sale` 3847 · `dl_config` 2530 · `dl_product` 1875 · `dl_purchase` 1409 · `dl_partner` 1202 · `dl_demo` 597 · `dl_base` 512

---

# 1. KIẾN TRÚC

```
dl_base ──► base, web, mail
  ├── dl_partner  ──► dl_base, mail, product
  ├── dl_product  ──► dl_base, product, stock, uom, dl_partner
  ├── dl_config   ──► dl_base, uom, auth_signup, mail, product
  │     └── dl_technical ──► dl_base, dl_product, dl_partner, uom, dl_config
  │            └── dl_sale ──► dl_partner, dl_product, dl_technical, dl_base, mail
  │                   └── dl_inventory ──► dl_base, dl_product, dl_partner, dl_sale, stock
  │                          └── dl_purchase ──► + dl_config, dl_sale, dl_inventory (6 module)
  └── dl_demo ──► (tất cả)
```

### ✅ Tốt
- Phân tầng rõ, **không phụ thuộc vòng**. `dl_base` mỏng (512 LOC) — đúng vai trò module gốc.
- Hạ tầng JS chung đã đẩy xuống `dl_base` (`static/src/views/dl_list_controller.js`) → tránh vòng `dl_sale ↔ dl_product`.
- 6 `AbstractModel` mixin dùng đúng chỗ.
- **XML 100% well-formed** (0 lỗi trên toàn bộ file non-static).
- 25 migration script theo version — nâng cấp schema có kiểm soát.

### ⚠️ Vấn đề

**A1 — `dl_purchase` phụ thuộc 6 module** *(Medium)* · `dl_purchase/__manifest__.py`
Chỉ 1409 LOC nhưng kéo gần như toàn hệ thống, vì vừa lo đơn mua vừa mở rộng `dl.sale.order`, `stock.picking`, `stock.lot`, `dl.pricing.approval.request`.
→ Tách module cầu nối (vd `dl_purchase_sale_link`).

**A2 — `dl_inventory` phụ thuộc `dl_sale` (ngược chiều)** *(Medium)*
`dl_inventory/models/dl_sale_order.py` + `dl_sale_order_dispatch.py` — Kho mở rộng model của Bán.
→ Đảo chiều: đưa phần "đơn bán biết về giao hàng" sang `dl_sale`.

**A3 — Không kế thừa `sale`/`purchase` chuẩn Odoo** *(High — dài hạn)*
Tự định nghĩa `dl.sale.order`, `dl.purchase.order`. Manifest **không** depend `sale`/`purchase`.
- ❌ Mất hệ sinh thái: kế toán (`account.move`), portal, `sale_stock`, báo cáo chuẩn. Muốn tích hợp kế toán phải tự viết cầu nối.
- ✅ Bù lại: **ít vỡ khi nâng cấp Odoo**.
→ Đây là *đánh đổi có chủ đích*, không phải lỗi. Nhưng phải ghi rõ: hệ thống này **không dùng được phân hệ kế toán Odoo** nếu không tích hợp riêng.

**A4 — Không có `ir.actions.report` nào** *(Medium)*
0 định nghĩa QWeb report. Chứng từ sinh bằng Python thuần:
`dl_sale/models/quotation_document.py` `_build_docx()`/`_build_pdf()` · `dl_purchase/models/purchase_document.py` · `dl_inventory/models/vendor_return_document.py`
→ **BA không sửa được mẫu chứng từ**; mỗi lần đổi layout phải sửa code + deploy.

**A5 — File data mồ côi** *(Low)* · `dl_technical/data/measurement_shape_data.xml` có trên đĩa nhưng **không khai trong manifest**.

---

# 2. CHẤT LƯỢNG CODE

### ✅ Cao hơn mặt bằng chung rõ rệt (quét AST 124 file production)

| Kiểm tra | Kết quả |
|---|---|
| `except:` trần · `print()` · `TODO/FIXME` · hard-code DB ID · `eval()` | **0** mỗi loại ✅ |
| Compute `store=True` thiếu `@api.depends` | **0** ✅ |
| XML malformed | **0** ✅ |

Comment giải thích *tại sao*, kể cả quyết định "cố ý không làm" — vd `dl_inventory/security/ir_rule.xml` giải thích vì sao **không** lọc theo `create_uid`.

### ⚠️ Vấn đề

**C1 — Nuốt exception im lặng** *(Medium)* — `except Exception: pass`, không log:
- `dl_config/models/res_users.py:117`
- `dl_purchase/models/stock_lot.py:67`

→ Lỗi biến mất không dấu vết. Sửa: `_logger.warning(..., exc_info=True)`.

**C2 — Hàm quá dài** *(Medium)* — 15 hàm ≥80 dòng:

| Dòng | File:Line | Hàm |
|---:|---|---|
| 168 | `dl_sale/models/quotation_document.py:281` | `_build_pdf()` |
| 161 | `dl_sale/models/quotation_document.py:77` | `_build_docx()` |
| 145 | `dl_inventory/models/vendor_return_document.py:109` | `_dlm_build_reject_report()` |
| 143 | `dl_inventory/models/stock_warehouse.py:213` | `_dlm_setup_locations()` |
| 125 | `dl_technical/models/dl_quotation_request.py:1042` | `_dlm_suggest_candidates()` |
| 103 | `dl_sale/models/quotation_pricing_service.py:53` | `create_from_rfq()` |
| 99 | `dl_sale/models/quotation_pricing_service.py:387` | `_price_manufactured()` |

Hàm dựng tài liệu dài là chấp nhận được (layout tuần tự). Đáng lo là **`create_from_rfq()` + `_price_manufactured()` — logic tính giá lõi**, khó test từng nhánh.
→ Tách `_price_manufactured()` theo thành phần chi phí (vật tư/công đoạn/hao hụt/lợi nhuận) — khớp sẵn với `dl.quotation.price.component`.

**C3 — 0 file `.po`** *(Low)* — chuỗi tiếng Việt hard-code trong `_()`. OK nếu chỉ dùng tiếng Việt.

---

# 3. BEST PRACTICES ODOO

### ✅ Tuân thủ tốt

| Hạng mục | Kết quả |
|---|---|
| **ACL** | 308 dòng, **phủ 100% model**, **0 dòng thiếu group** ✅ |
| `mail.thread` | 11 model + `mail.activity.mixin` ✅ |
| `tracking=True` | Rộng khắp trên field nghiệp vụ quan trọng ✅ |
| `@api.constrains` | ~70 constraint ✅ |
| `@api.model_create_multi` | Dùng đúng (`dl_quotation.py:478`) ✅ |
| Partial unique index | `dl_sale/models/dl_quotation.py:461` `init()` — SQL trực tiếp vì Odoo helper không hỗ trợ UNIQUE+WHERE. **Đúng cách**, có comment ✅ |

**Đã kiểm tra và xác nhận KHÔNG phải lỗi:**
- 6 model không có ACL đều là `AbstractModel` → đúng chuẩn.
- XML ID "trùng" trong `dl_product/views/menus.xml:116,125` là **cố ý** — pattern `<menuitem>` + `<record>` để clear field cũ trên DB nâng cấp, có comment ở dòng 122-124.

### ⚠️ Vi phạm

**B1 — Thiếu `@api.depends_context('uid')`** *(Low)* — **không nhất quán trong chính codebase**:

Dùng ĐÚNG: `dl_config/models/pricing_approval.py:155` · `dl_technical/models/dl_quotation_request.py:918`

BỎ SÓT (compute đọc `self.env.user` nhưng không khai):

| File:Line | Field |
|---|---|
| `dl_product/models/dl_product.py:195` | `dlm_is_price_editor` |
| `dl_product/models/dl_product.py:242` | `dlm_can_change_kind` |
| `dl_technical/models/dl_quotation_request.py:542, 1358` | `is_technician` |

Các field này còn `compute_sudo=True` → compute chạy trong env superuser, khoá cache **không chứa uid** ⇒ giá trị của user A có thể phục vụ lại user B.

**Ảnh hưởng bảo mật: THẤP** — đây là field *gating UI*, chặn thật nằm ở `write()` guard (`dl_product.py:943`). Sai cache ⇒ thấy ô mở/khoá sai, nhưng lưu vẫn bị chặn.
→ Sửa: thêm decorator (2 dòng).

**B2 — Multi-company không nhất quán** *(Medium)*

| Model | `company_id` | rule multi-company |
|---|---|---|
| `dl.pricing.*` (8 model) | ✅ | ✅ 8 global rule |
| `dl.quotation` / `dl.sale.order` / `dl.purchase.order` | ✅ | ❌ **không có** |
| `dl.quotation.request` / `dl.bom` | ❌ | ❌ |

→ Hệ thống chỉ chạy đúng ở **single-company**. Chốt dứt điểm: bỏ hẳn `company_id` **hoặc** bổ sung đủ rule — **trước khi có dữ liệu thật**.

**B3 — Record rule chỉ phủ 4 nhóm model** *(Medium)*
24 rule chỉ nằm trên `res.partner`, `product.*`, `stock.*`, `dl.pricing.*`.
**~50 model nghiệp vụ custom (`dl.quotation`, `dl.sale.order`, `dl.bom`, `dl.drawing`…) KHÔNG có rule nào** — chỉ ACL cấp model.
⇒ Mọi user nhóm BA đọc/sửa được **toàn bộ** báo giá của **mọi** nhân viên.
→ Có thể là thiết kế cố ý (ERP nội bộ nhỏ). **Cần đối chiếu ma trận RBAC trong đặc tả** — nếu spec yêu cầu "Sales chỉ thấy khách của mình" thì đây là lỗ hổng.

---

# 4. DATABASE

### ✅ Tốt
- **36 index** phủ đúng FK nóng: `quotation_request_id`, `origin_quotation_id`, `dlm_sale_order_id`, `dlm_code`, `dlm_name_key`, `state`/`company_id` (10 chỗ ở `dl_config`)…
- **54 compute `store=True` — tất cả đều có `@api.depends`** ✅
- `_sql_constraints` ở 9 file.

### ⚠️ D1 — 94/143 Many2one **không khai `ondelete`** *(High)*

Odoo mặc định `set null` ⇒ dữ liệu mồ côi hoặc vi phạm NOT NULL.

| SL | File |
|---:|---|
| 11 | `dl_technical/wizard/rfq_resolve_wizard.py` |
| 9 | `dl_technical/models/dl_quotation_request.py` |
| **8** | **`dl_sale/models/dl_quotation.py`** |
| **7** | **`dl_sale/models/dl_sale_order.py`** |
| 5 | `dl_config/models/pricing_approval.py` · `dl_purchase/models/dl_purchase_order.py` |

**Giảm nhẹ:** wizard (`TransientModel`) ít nghiêm trọng vì tự dọn. **Ưu tiên sửa model thường trú** (`dl_quotation`, `dl_sale_order`, `dl_purchase_order`).
→ Master data giữ lịch sử: `restrict` · line→header: `cascade` · tham chiếu tuỳ chọn: `set null`.

### ⚠️ D2 — Field nên bổ sung index

| Field | Lý do |
|---|---|
| `dl.quotation.state` · `dl.sale.order.state` | Lọc list view + cron hết hạn |
| `dl.bom.line.material_id` | Bị `search_count` ở `dl_bom.py:201` |
| `dl.drawing.product_id` | Bị search 3 lần ở `dl_bom.py:235-240` |
| `dl.quotation.request.status` | Lọc trạng thái RFQ |

> `dl_config` đã index `state` ở 10 model — áp cùng chuẩn cho `dl_sale`/`dl_technical`.

---

# 5. BẢO MẬT

## 🔴 CRITICAL

### S1 — 8 tài khoản demo mật khẩu `123456` cài vào PRODUCTION (có Admin)

**File:** `dl_base/data/demo_users_data.xml` · khai trong `dl_base/__manifest__.py` key **`'data'`** (KHÔNG phải `'demo'`)

```xml
<record id="demo_user_admin" model="res.users">
    <field name="login">admin.it@gmail.com</field>
    <field name="password">123456</field>
    <field name="groups_id" eval="[(6, 0, [ref('dl_base.dl_group_admin')])]" />
</record>
```

| Login | Nhóm |
|---|---|
| `admin.it@gmail.com` | **`dl_group_admin`** ← toàn quyền, cấu hình được RBAC |
| `ceo@` · `truongkd@` · `ba@` · `kythuat@` · `ketoan@` · `muahang@` · `thukho@` | 7 vai trò còn lại |

**Nguyên nhân gốc:** kiểm tra cả 9 manifest → **KHÔNG module nào có key `'demo'`**.
⇒ **`without_demo = All` HOÀN TOÀN VÔ TÁC DỤNG.** Odoo chỉ bỏ qua file trong key `'demo'`; file trong `'data'` **luôn được nạp**.

**Sửa:**
```python
# dl_base/__manifest__.py — bỏ 2 dòng demo khỏi 'data', thêm key 'demo'
'demo': ['data/demo_users_data.xml', 'data/demo_user_language_data.xml'],
```
DB đã cài: `UPDATE res_users SET active=false WHERE login LIKE '%@gmail.com';`
Kiểm chứng: `SELECT login FROM res_users WHERE login LIKE '%@gmail.com';` → phải rỗng.

> Các file demo khác cũng trong `'data'` (mức thấp hơn — chỉ dữ liệu mẫu): `dl_product/data/dl_demo_data.xml` (9) · `dl_technical/data/dl_demo_data.xml` (20) · `dl_demo/data/*` (10).
> `dl_config/data/pricing_seed.xml` (18) và `dl_product/data/material_seed_data.xml` (29) là **seed cấu hình hợp lệ** — giữ nguyên.

### S2 — Secret plaintext trong `odoo.conf`

`odoo.conf:10` `db_password=123456` · `odoo.conf:49` Gmail App Password `qeppkjbpjwehxrad`

**✅ Giảm nhẹ (đã kiểm chứng):** file **đã gitignore và KHÔNG được git theo dõi** (`git ls-files` rỗng). **Secret chưa lộ lên repo.**
→ Vẫn phải: thu hồi + tạo lại app password; đặt mật khẩu DB mạnh; `chmod 640`.

### S3 — `list_db = True` (`odoo.conf:32`)
Lộ `/web/database/manager` — tạo/backup/**xoá** database.
**✅ Giảm nhẹ:** `admin_passwd` **đã hash pbkdf2-sha512** (`odoo.conf:3`).
→ `list_db = False` + chặn ở Nginx.

## 🟢 Những mặt LÀM TỐT

| Hạng mục | Kết quả |
|---|---|
| **SQL Injection** | ✅ **0**. Mọi `cr.execute` tham số hoá. 2 chỗ f-string đã xác minh an toàn: `dl_sale/migrations/17.0.1.14.0/post-migration.py:20` (tên bảng từ tuple hằng) · `dl_sale/models/dl_quotation.py:475` (`self._table` — hằng framework) |
| **XSS** | ✅ **0 `t-raw`** trong toàn bộ QWeb. Python dùng `Markup("...") % value` — **pattern đúng**, markupsafe tự escape |
| **`eval()`** | ✅ Không dùng — chỉ `safe_eval` (`dl_product.py:160`) |
| **Controller** | ✅ Chỉ **2**. `scrap_banner.py:46` `auth="user"`, trả HTML tĩnh. `main.py` kế thừa `@http.route()` từ `web.Home` — đúng idiom |
| **CSRF / public** | ✅ Không route `type="http"`+POST tự viết; **0** `auth="public"`/`"none"` |
| **`SUPERUSER_ID`** | ✅ Chủ yếu trong migration (đúng); trong model dùng để *kiểm tra*, không leo quyền |

**`sudo()` — 222 lời gọi nhưng có kỷ luật.** Có **61 guard quyền tường minh**, pattern nhất quán *guard trước → sudo sau → allowlist field*:

```python
# dl_product/models/dl_product.py:802-816
def set_dlm_waste(self, vals):
    if not self.env.su and not (user.has_group("...tech") or ...):
        raise AccessError(_("Chỉ Kỹ thuật/Kế toán/Admin..."))
    allowed = {"dlm_waste_rate", "dlm_scrap_product_id"}   # ← allowlist
    self.sudo().write({k: v for k, v in vals.items() if k in allowed})
```

**Màn RBAC (`dl_base/models/dl_rbac.py`):** mọi method ghi (`create_role`, `set_crud`, `set_operation`…) gọi `_check_rbac_admin()` **ở dòng đầu tiên** → không có đường leo quyền qua RPC.

## Tổng hợp rủi ro bảo mật

| # | Rủi ro | Mức | File |
|---|---|---|---|
| S1 | 8 user demo `123456` (có Admin); `without_demo` vô hiệu | 🔴 **Critical** | `dl_base/data/demo_users_data.xml` + manifest |
| S2 | Secret plaintext | 🔴 **Critical** | `odoo.conf:10,49` |
| S3 | `list_db = True` | 🟠 High | `odoo.conf:32` |
| S4 | `proxy_mode = False` sau Nginx | 🟠 High | `odoo.conf:43` |
| S5 | Thiếu record rule ~50 model | 🟡 Medium | §B3 |
| S6 | Multi-company không nhất quán | 🟡 Medium | §B2 |
| S7 | Nuốt exception — che dấu vết | 🟡 Medium | `res_users.py:117`, `stock_lot.py:67` |
| S8 | Thiếu `depends_context('uid')` | 🟢 Low | §B1 |

---

# 6. HIỆU NĂNG

Quét AST: **145 vị trí** gọi ORM trong vòng `for`. Lọc ra các trường hợp thực sự nguy hiểm:

### P1 — `_compute_pending_request` *(High — sửa rất dễ)*
`dl_config/models/pricing_matrix.py:103`

```python
def _compute_pending_request(self):
    for rec in self:
        req = rec._pending_requests()[:1]      # ← 1 SELECT cho MỖI dòng
```

**Mấu chốt:** `_pending_requests()` (dòng 109-115) **đã hỗ trợ batch sẵn** (`("res_id","in",self.ids)`) nhưng bị gọi trên từng `rec` ⇒ vứt bỏ khả năng batch. List view N dòng ⇒ **N query**.

```python
def _compute_pending_request(self):
    by_res = {}
    for r in self._pending_requests():          # 1 SELECT duy nhất
        by_res.setdefault(r.res_id, r)
    for rec in self:
        req = by_res.get(rec.id)
        rec.pending_request_id = req or False
        rec.has_pending_request = bool(req)
```

### P2 — `_compute_dlm_supplierinfo_count` *(High — sửa 1 dòng)*
`dl_partner/models/res_partner.py:258-264`

```python
@api.depends('dlm_supplierinfo_ids')          # ← đã depends vào O2M
def _compute_dlm_supplierinfo_count(self):
    for rec in self:
        rec.dlm_supplierinfo_count = self.env['product.supplierinfo'].sudo(
        ).search_count([('partner_id','=',rec.id)])   # ← thừa hoàn toàn
```
O2M **đã nạp sẵn vào cache** → thay bằng `len(rec.sudo().dlm_supplierinfo_ids)`.

### P3 — `_compute_used_in_parent_count` *(Medium)* · `dl_technical/models/dl_bom.py:196-204`
`search_count` cho **mỗi** BOM → gom bằng `read_group`:
```python
data = self.env["dl.bom.line"].sudo().read_group(
    [("material_id","in",mats.product_id.ids)], ["material_id"], ["material_id"])
counts = {d["material_id"][0]: d["material_id_count"] for d in data}
```

### P4 — `_compute_drawing_ref` — tối đa **3 search/bản ghi** *(Medium)* · `dl_bom.py:223-245`
**✅ Giảm nhẹ (đã kiểm chứng):** `drawing_id` chỉ ở **form view** (`bom_views.xml:190`), **không có trên list** ⇒ ~3 query mỗi lần mở form, không phải thảm hoạ.
→ Gộp: `Drawing.search(domain, order="is_current desc, version desc", limit=1)`

### P5 — Constraint search từng bản ghi *(Medium)*
`res_partner.py` có **16 `@api.constrains`**, nhiều cái search từng dòng (L944, 991, 1027, 1037).
Chỉ đau khi **import hàng loạt** (1000 đối tác ⇒ ~4000 query).
→ Ràng buộc duy nhất đơn giản (MST, `dlm_code`) nên chuyển sang `_sql_constraints` UNIQUE.

### P6 — `workers = None` *(Critical)* · `odoo.conf:68`
Đơn tiến trình đa luồng — do **GIL** chỉ tận dụng ~1 core. `limit_time_*`/`limit_memory_*` đều `None` ⇒ **một request lỗi vòng lặp ăn hết RAM và giết cả server**, không tự phục hồi.

---

# 7. SẴN SÀNG PRODUCTION

## 🔴 KHÔNG CÓ BẤT KỲ TÀI SẢN TRIỂN KHAI NÀO

| Thành phần | Trạng thái |
|---|---|
| Dockerfile · docker-compose · Nginx conf · `requirements.txt` · systemd · script backup · CI/CD · tài liệu deploy | ❌ **Không có cái nào** |

`scripts/` chỉ có tiện ích **dev**: `reset_demo_db.ps1` (PowerShell/Windows), `_recreate_db.py`, `purge_stock_data.py`.
⇒ Dự án ở trạng thái *"chạy được trên máy dev Windows"*, chưa có đường lên Linux.

## Phân tích `odoo.conf`

| Tham số | Hiện tại | Production | Mức |
|---|---|---|---|
| `addons_path` | `D:\FPTU\...` | `/opt/odoo/...` | 🔴 |
| `data_dir` | `c:\users\admin\...` | `/var/lib/odoo` | 🔴 |
| `workers` | `None` | `5` | 🔴 |
| `db_password` | `123456` | mạnh ≥24 ký tự | 🔴 |
| `smtp_password` | plaintext | secret file | 🔴 |
| `without_demo` | `All` | ⚠️ **vô tác dụng** (S1) | 🔴 |
| `list_db` | `True` | `False` | 🟠 |
| `proxy_mode` | `False` | `True` | 🟠 |
| `dbfilter` | `^dlm_dev$` | `^dlm_prod$` | 🟠 |
| `logfile` | rỗng | `/var/log/odoo/odoo.log` | 🟠 |
| `limit_time_cpu/real` | `None` | `600`/`1200` | 🟠 |
| `limit_memory_soft/hard` | `None` | 2GB/2.5GB | 🟠 |
| `http_interface` | `127.0.0.1` | ✅ giữ | ✅ |
| `admin_passwd` | pbkdf2 hash | ✅ giữ (đổi giá trị) | ✅ |
| `unaccent` | `False` | `True` | 🟢 |

## Phụ thuộc Python ngoài

⚠️ Tên import ≠ tên gói pip: `dl_sale` khai `docx` → pip là **`python-docx`**.

```
# requirements-dlm.txt
python-docx==1.1.2
reportlab==4.2.5
```

## `odoo.conf` production đề xuất

```ini
[options]
addons_path = /opt/odoo/odoo-17.0/addons,/opt/odoo/dlm-erp
data_dir    = /var/lib/odoo

db_host = 127.0.0.1
db_port = 5432
db_user = odoo
db_password = <MẬT_KHẨU_MẠNH_>=24_KÝ_TỰ>
db_name  = dlm_prod
dbfilter = ^dlm_prod$
; ⚠️ db_maxconn là pool CHO MỖI TIẾN TRÌNH, không phải toàn cục.
;    Tổng ≈ (workers + max_cron_threads + 1) × db_maxconn = (5+2+1) × 8 = 64
;    < max_connections=100 của PostgreSQL.
;    ĐỪNG đặt 32: 8 × 32 = 256 ⇒ "FATAL: sorry, too many clients already".
db_maxconn = 8
db_sslmode = prefer
list_db    = False

admin_passwd = <HASH_pbkdf2_MỚI>
proxy_mode   = True

http_enable    = True
http_interface = 127.0.0.1
http_port      = 8069
gevent_port    = 8072

workers              = 5
max_cron_threads     = 2
limit_time_cpu       = 600
limit_time_real      = 1200
limit_time_real_cron = 1800
limit_request        = 8192
limit_memory_soft    = 2147483648
limit_memory_hard    = 2684354560

logfile   = /var/log/odoo/odoo.log
log_level = warn

smtp_server = smtp.gmail.com
smtp_port   = 587
smtp_ssl    = True
smtp_user   = <email>
smtp_password = <APP_PASSWORD_MỚI_SAU_KHI_THU_HỒI>
email_from  = <email>

without_demo        = All
server_wide_modules = base,web
unaccent            = True     ; ← BẬT: tìm tiếng Việt không dấu
transient_age_limit = 1.0
```

> `unaccent`: hệ thống toàn tiếng Việt, logic so trùng tên (`dl_product.py:820`) **cố ý giữ dấu**. Bật `unaccent` để gõ không dấu vẫn tìm ra. Cần `CREATE EXTENSION IF NOT EXISTS unaccent;`

---

# 8. HẠ TẦNG VPS

## Cấu hình đề xuất

| Hạng mục | Đề xuất | Lý do (dựa trên số liệu đo) |
|---|---|---|
| **OS** | **Ubuntu 24.04 LTS** | LTS đến 2029; Python 3.12 mặc định — khớp `.pyc` hiện tại (`cpython-312`) |
| **PostgreSQL** | **16** | Đã chốt trong dự án; có `pg_get_constraintdef()` |
| **CPU** | **2 vCPU** (4 nếu >20 user đồng thời) | `workers = 2×core + 1` = 5 → ~15-20 user đồng thời |
| **RAM** | **8 GB** | 5 worker×250MB + 2 cron×250MB + PG ~2.5GB + OS ~1GB ≈ 6.5-7.5GB. **4GB sẽ chật khi build assets** |
| **Ổ cứng** | **60 GB NVMe** (100GB tốt hơn) | Odoo ~1GB + filestore (**bản vẽ `dl.drawing` + ảnh RFQ — phần phình nhanh nhất**) + DB + backup |
| **Swap** | **4 GB**, `vm.swappiness=10` | Đệm lúc build assets & `pg_dump` |
| **Triển khai** | **Docker Compose** | Pin chính xác Python 3.12 + PG16 + `python-docx`/`reportlab`; rollback bằng đổi tag (quan trọng vì **chưa có CI**) |
| **Firewall** | UFW: chỉ 22/80/443 | **Đóng 5432, 8069, 8072 khỏi Internet** |

### ✅ Đối chiếu gói KVM 2 (2 vCPU / 8GB / 100GB NVMe / 8TB)

**Phù hợp** — khớp đúng khuyến nghị, dư 40GB đĩa cho filestore. Băng thông 8TB thừa xa cho ERP nội bộ.

**Điều kiện để "vừa đủ" (PostgreSQL chạy cùng máy):**
- `workers = 5`, `db_maxconn = 8` (xem cảnh báo §7)
- PostgreSQL: `shared_buffers=2GB` · `effective_cache_size=4GB` · `work_mem=16MB` · `maintenance_work_mem=256MB` · `max_connections=100`
- Swap 4GB bắt buộc (đệm lúc build assets lần đầu — đây là lúc RAM căng nhất)
- Nếu RAM chạm ngưỡng: hạ `workers` xuống 4 **hoặc** `shared_buffers` xuống 1.5GB

**Khi nào cần nâng cấp:** >20 user đồng thời, hoặc filestore vượt ~50GB, hoặc `load average` thường xuyên >2.

## Docker Compose

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    secrets: [db_password]
    volumes: [pgdata:/var/lib/postgresql/data]
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 10s
      retries: 5
    command: >
      postgres -c shared_buffers=2GB -c effective_cache_size=4GB
               -c work_mem=16MB -c maintenance_work_mem=256MB
               -c max_connections=100

  odoo:
    build: .
    depends_on:
      db: {condition: service_healthy}
    volumes:
      - odoo-data:/var/lib/odoo
      - ./dlm-erp:/opt/odoo/dlm-erp:ro
      - ./odoo.conf:/etc/odoo/odoo.conf:ro
      - ./logs:/var/log/odoo
    ports:
      - "127.0.0.1:8069:8069"     # CHỈ localhost — Nginx ở host
      - "127.0.0.1:8072:8072"
    restart: unless-stopped

secrets:
  db_password: {file: ./secrets/db_password.txt}   # chmod 600, gitignore

volumes: {pgdata: , odoo-data: }
```

```dockerfile
FROM odoo:17.0
USER root
COPY requirements-dlm.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements-dlm.txt
USER odoo
```

## Nginx

```nginx
upstream odoo     { server 127.0.0.1:8069; }
upstream odoochat { server 127.0.0.1:8072; }

server { listen 80; server_name erp.dailinh.vn; return 301 https://$host$request_uri; }

server {
    listen 443 ssl http2;
    server_name erp.dailinh.vn;

    ssl_certificate     /etc/letsencrypt/live/erp.dailinh.vn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/erp.dailinh.vn/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # CHẶN Database Manager — lớp phòng thủ thứ 2 cho S3
    location ~* ^/web/database/(manager|create|duplicate|drop|backup|restore) { return 404; }

    client_max_body_size 50M;          # upload bản vẽ kỹ thuật

    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;    # proxy_mode=True cần header này
    proxy_read_timeout 1200s;                      # khớp limit_time_real

    location /websocket {
        proxy_pass http://odoochat;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    location / { proxy_pass http://odoo; proxy_redirect off; }
    location ~* /web/static/ { proxy_cache_valid 200 90m; expires 864000; proxy_pass http://odoo; }

    gzip on;
    gzip_types text/css text/plain application/javascript application/json image/svg+xml;
}
```

## Backup

```bash
#!/bin/bash
set -euo pipefail
DEST=/var/backups/odoo; DATE=$(date +%F); mkdir -p "$DEST"
docker compose exec -T db pg_dump -U odoo -Fc dlm_prod > "$DEST/dlm_prod_$DATE.dump"
tar czf "$DEST/filestore_$DATE.tar.gz" -C /var/lib/docker/volumes/odoo-data/_data filestore
find "$DEST" -mtime +30 -delete
rclone copy "$DEST" remote:dlm-erp-backup --max-age 25h   # BẮT BUỘC off-site
```
`0 2 * * * /opt/odoo/backup.sh >> /var/log/odoo/backup.log 2>&1`

> ⚠️ **Backup chưa từng restore = chưa có backup.** Filestore chứa **bản vẽ kỹ thuật** — mất là mất tài sản trí tuệ, DB không cứu được.

logrotate: `daily · rotate 14 · compress · copytruncate · su odoo odoo`

---

# 9. KHẢ NĂNG MỞ RỘNG

| Khía cạnh | Điểm | Nhận xét |
|---|---|---|
| **Thêm module** | 🟢 Tốt | **RBAC tự mở rộng** — mỗi module khai `data/rbac_features.xml` là chức năng **tự hiện** trong ma trận phân quyền (`dl_base/models/dl_rbac.py:27-29`). Thiết kế xuất sắc |
| **Nâng cấp Odoo** | 🟡 TB-Khá | ✅ Không phụ thuộc `sale`/`purchase`; 25 migration script. ⚠️ Kế thừa sâu `stock` (`stock.quant._apply_inventory` override ở `stock_quant.py:41`); **~13k LOC OWL/SCSS là chỗ dễ vỡ nhất** khi lên Odoo 18/19 |
| **Tăng user** | 🟠 Cần xử lý | Chặn bởi `workers=None`. Sau khi sửa: ~15-20 user đồng thời |
| **API** | 🟡 TB | ✅ XML-RPC/JSON-RPC chuẩn cho 59 model; method service đã guard tốt nên **an toàn khi expose**. ⚠️ Chưa có REST riêng/versioning/rate limit |
| **Bảo trì** | 🟢 Tốt | **373 test**, 25 migration, comment chất lượng cao. ⚠️ Thiếu CI |

**Rào cản lớn nhất:** không có CI (373 test tồn tại nhưng không ai đảm bảo được chạy trước deploy) · không có staging · chứng từ sinh bằng Python (§A4).

---

# 10. PHÂN LOẠI RỦI RO

## 🔴 CRITICAL — chặn deploy

| # | Vấn đề | File | Ảnh hưởng | Ưu tiên |
|---|---|---|---|---|
| **R1** | Admin demo `123456`; `without_demo` vô hiệu do không module nào có key `'demo'` | `dl_base/data/demo_users_data.xml` + `__manifest__.py` | **Chiếm toàn quyền hệ thống từ Internet** | **P0** |
| **R2** | Secret plaintext (đã kiểm chứng: **chưa lộ lên git**) | `odoo.conf:10,49` | App password lộ ⇒ gửi mail mạo danh | **P0** |
| **R3** | `workers=None` + `limit_*` trống | `odoo.conf:68` | ~1 core do GIL; 1 request lỗi giết server | **P0** |
| **R4** | Không có tài sản triển khai nào | toàn repo | Không rollback, **không backup ⇒ mất là vĩnh viễn** | **P0** |
| **R5** | `addons_path`/`data_dir` đường dẫn Windows | `odoo.conf:2,5` | **Odoo không khởi động nổi trên Linux** | **P0** |

## 🟠 HIGH

| # | Vấn đề | File | Ưu tiên |
|---|---|---|---|
| R6 | `list_db=True` | `odoo.conf:32` | P0 |
| R7 | `proxy_mode=False` sau Nginx (sai IP client, URL `http://` trong mail) | `odoo.conf:43` | P0 |
| R8 | `dbfilter=^dlm_dev$` | `odoo.conf:15` | P1 |
| R9 | 94 M2O thiếu `ondelete` | `dl_quotation.py`(8), `dl_sale_order.py`(7), `dl_purchase_order.py`(5) | P1 |
| R10 | N+1 trong compute | `pricing_matrix.py:103`, `res_partner.py:263`, `dl_bom.py:201,235` | P1 |
| R11 | Không có backup | — | P0 |

## 🟡 MEDIUM

R12 thiếu record rule ~50 model (§B3) · R13 multi-company (§B2) · R14 nuốt exception (`res_users.py:117`, `stock_lot.py:67`) · R15 hàm tính giá quá dài · R16 không có QWeb report · R17 `dl_purchase` phụ thuộc 6 module · R18 không có CI

## 🟢 LOW

R19 thiếu `depends_context('uid')` (`dl_product.py:195,242`) · R20 file data mồ côi (`measurement_shape_data.xml`) · R21 không có `.po` · R22 `unaccent=False` · R23 rác `.tmp_*` trong repo

---

# 11. TỔNG KẾT

| # | Hạng mục | Điểm | Căn cứ |
|---|---|---:|---|
| 1 | Kiến trúc | **7.0** | Phân tầng rõ, không vòng, RBAC tự mở rộng. Trừ: `dl_purchase` 6 deps, `dl_inventory→dl_sale` ngược, không QWeb report |
| 2 | Chất lượng code | **8.0** | 0 bare except/print/TODO/hard-code ID; comment giải thích *tại sao*. Trừ: 15 hàm ≥80 dòng, 2 chỗ nuốt exception |
| 3 | Database | **7.0** | 36 index đúng chỗ, 54 compute store đều có depends. Trừ: 94 M2O thiếu `ondelete` |
| 4 | Bảo mật | **4.0** | Kiến trúc tốt (0 SQLi/XSS/eval, ACL 100%, sudo có guard). **Bị kéo xuống bởi R1** |
| 5 | Hiệu năng | **6.0** | Index & compute store hợp lý. Trừ: `workers=None`, 4 N+1 |
| 6 | Bảo trì | **8.0** | 373 test, 25 migration. Trừ: không CI |
| 7 | Sẵn sàng Production | **2.5** | **Không có artifact triển khai nào**; conf là file dev Windows |

### 🎯 Tổng: **6.1 / 10**

> Dự án có **chất lượng kỹ thuật nội tại tốt** nhưng **chưa được chuẩn bị để rời máy dev**. Khoảng cách nằm ở **vận hành**, không nằm ở **code**.

## Phần A — PHẢI làm TRƯỚC deploy (2-3 ngày công)

**Bảo mật (~2h):** R1 chuyển demo sang key `'demo'` → kiểm chứng DB mới không còn user `@gmail.com` · R2 thu hồi Gmail app password + mật khẩu DB mạnh · R6 `list_db=False` + chặn Nginx · đổi `admin_passwd`

**Cấu hình (~1h):** R5 đường dẫn Linux · R3 `workers=5` + `db_maxconn=8` + `limit_*` · R7 `proxy_mode=True` · R8 `dbfilter`/`db_name` · `logfile` · `unaccent=True` + `CREATE EXTENSION`

**Hạ tầng (~1 ngày):** R4 Dockerfile + compose + `requirements-dlm.txt` · Nginx + Let's Encrypt · UFW · R11 backup + cron + off-site · **restore thử** · logrotate

**Kiểm chứng (~0.5 ngày):** chạy 373 test trên môi trường sạch · cài mới từ DB trống trên Linux · đăng nhập thử **8 vai trò** · xác nhận **không tài khoản demo nào tồn tại**

## Phần B — SAU deploy

**Tháng đầu:** R10 sửa 4 N+1 (~1h, lợi ích rõ) · R9 `ondelete` · R14 logging · R18 CI chạy 373 test · staging · R12 đối chiếu record rule với đặc tả
**Quý đầu:** R13 chốt single/multi-company · R15 tách hàm tính giá · R16 QWeb report · R17 tách module · bổ sung index (§D2) · monitoring

## Phần C — KẾT LUẬN

### ❌ KHÔNG nên deploy Production ngay.

**Chỉ mình R1 cũng đủ chặn:** `admin.it@gmail.com` / `123456` với `dl_group_admin` **được tạo tự động trên mọi DB mới**, kể cả khi `without_demo = All` — vì file khai trong key `'data'` và **không module nào có key `'demo'`**. Đưa lên tên miền public = giao toàn quyền cho bất kỳ ai; mà `123456` thì không cần đoán. Kẻ tấn công đọc được toàn bộ báo giá, giá vốn, khách hàng/NCC, bản vẽ kỹ thuật, và tự cấp thêm quyền qua chính màn RBAC.

Cộng thêm: **không backup** (mất là vĩnh viễn), `addons_path` Windows (**Odoo không khởi động nổi trên Linux**), `workers=None` (sập khi vài người dùng cùng lúc).

### ✅ Nhưng khoảng cách là **vận hành**, không phải **code**

Cần nói rõ để đánh giá công bằng — phần lõi **tốt hơn đa số dự án Odoo custom cùng quy mô**:
- **0** SQL injection, **0** XSS, **0** `eval()`, **0** bare except, **0** hard-code DB ID
- ACL phủ **100%** model; 222 `sudo()` nhưng **61** guard tường minh, pattern nhất quán
- RBAC guard `_check_rbac_admin()` ở **dòng đầu mọi method ghi** — không có đường leo quyền qua RPC
- **373 test method** — hiếm thấy
- **0** compute `store=True` thiếu `@api.depends` — lỗi kinh điển mà dự án không mắc

**Cả 5 Critical đều là lỗi cấu hình/đóng gói, không phải lỗi logic nghiệp vụ.** Không hạng mục nào đòi viết lại kiến trúc.

| Giai đoạn | Thời gian |
|---|---|
| Phần A (5 Critical + 3 High) | **2-3 ngày công** |
| Kiểm chứng (test, cài sạch Linux, 8 vai trò, restore backup) | **0.5 ngày** |
| **Go-live** | sau khi A xong **và** kiểm chứng đạt |

> Sau Phần A, điểm "Sẵn sàng Production" từ **2.5 → ~8.0/10**, đủ điều kiện go-live.

---

*Phân tích tĩnh tại commit hiện hành nhánh `develop`. Chưa chạy test suite, chưa thử deploy — nằm trong bước Kiểm chứng.*
