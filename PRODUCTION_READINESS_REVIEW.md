# BÁO CÁO ĐÁNH GIÁ SẴN SÀNG PRODUCTION — DLM-ERP (Odoo 17 CE)

**Ngày đánh giá:** 2026-08-17
**Phạm vi:** toàn bộ `dlm-erp/` (9 module custom) + `odoo.conf` + `scripts/`
**Phương pháp:** đọc & phân tích tĩnh source code thực tế (AST + grep + đọc file). Không suy đoán.

> ⚠️ **Lưu ý phạm vi:** báo cáo dựa trên phân tích tĩnh. Tôi **chưa chạy** test suite
> (373 test method) và **chưa chạy** thử deploy thật. Các kết luận về hành vi runtime
> được suy ra từ code, đã ghi rõ chỗ nào là suy luận.

---

## 0. Số liệu tổng quan (đo thực tế)

| Chỉ số | Giá trị |
|---|---|
| Module custom | 9 |
| Python production (không tính test) | **~24.500 LOC** |
| Python test | ~7.500 LOC / **373 test method** / 34 file |
| XML (view/data/security) | ~15.100 LOC |
| JS/SCSS/OWL | ~13.100 LOC |
| Model tự định nghĩa (`_name`) | **59** |
| Model kế thừa (`_inherit`) | 23 |
| Khai báo field | 759 (M2O 143 · O2M 31 · M2M 19) |
| Dòng ACL (`ir.model.access.csv`) | 308 |
| Record rule (`ir.rule`) | 24 |
| Lời gọi `sudo()` | 222 |
| Controller HTTP | 2 |
| `ir.cron` | 3 |
| Migration script | 25 |

**LOC production theo module:**

```
dl_technical  6442   dl_inventory  6081   dl_sale  3847   dl_config  2530
dl_product    1875   dl_purchase   1409   dl_partner 1202  dl_demo 597   dl_base 512
```

---

# 1. ĐÁNH GIÁ KIẾN TRÚC

## 1.1 Đồ thị phụ thuộc (đọc từ `__manifest__.py`)

```
dl_base ──► base, web, mail
  ├── dl_partner  ──► dl_base, mail, product
  ├── dl_product  ──► dl_base, product, stock, uom, dl_partner
  ├── dl_config   ──► dl_base, uom, auth_signup, mail, product
  │     └── dl_technical ──► dl_base, dl_product, dl_partner, uom, dl_config
  │            └── dl_sale ──► dl_partner, dl_product, dl_technical, dl_base, mail
  │                   └── dl_inventory ──► dl_base, dl_product, dl_partner, dl_sale, stock
  │                          └── dl_purchase ──► dl_base, dl_partner, dl_product,
  │                                              dl_config, dl_sale, dl_inventory
  └── dl_demo ──► (tất cả 7 module trên)
```

### ✅ Điểm tốt

- **Phân tầng rõ ràng, không có phụ thuộc vòng.** `dl_base` là nền (chỉ 512 LOC — đúng vai trò module gốc), các module nghiệp vụ xếp thành chuỗi tuyến tính.
- **Hạ tầng JS dùng chung đã được đẩy xuống `dl_base`** (`dl_base/static/src/views/dl_list_controller.js`, `js/actions_menu.js`) — tránh được phụ thuộc vòng `dl_sale ↔ dl_product`. Đây là quyết định kiến trúc đúng.
- **Mixin được dùng đúng chỗ:** 6 `AbstractModel` (`dl.bom.header.mixin`, `dl.bom.line.mixin`, `dl.pricing.rule.mixin`, `dl.pricing.commercial.mixin`, `dl.quotation.pricing.service`, `dl.rfq.line.quick.wizard.base`) để chia sẻ logic thay vì copy-paste.
- **XML 100% well-formed** (kiểm tra bằng ElementTree trên toàn bộ file non-static: 0 lỗi).
- **Có migration script đầy đủ** (25 file `post-migration.py` theo version) — dấu hiệu dự án đã qua nhiều vòng nâng cấp schema có kiểm soát.

### ⚠️ Vấn đề kiến trúc

#### A1 — `dl_purchase` phụ thuộc 6 module *(Medium)*

`dlm-erp/dl_purchase/__manifest__.py` — depends: `dl_base, dl_partner, dl_product, dl_config, dl_sale, dl_inventory`.

Module này chỉ 1409 LOC nhưng kéo theo gần như toàn hệ thống. Hệ quả: không thể cài/test/gỡ `dl_purchase` độc lập; mọi thay đổi ở 6 module dưới đều có nguy cơ làm vỡ nó.

**Nguyên nhân:** `dl_purchase` vừa quản lý đơn mua (`dl.purchase.order`), vừa mở rộng `dl.sale.order` (`models/dl_sale_order_ext.py`), vừa mở rộng `stock.picking`/`stock.lot`, vừa mở rộng `dl.pricing.approval.request`.

**Đề xuất:** tách phần mở rộng liên-phân-hệ ra module cầu nối (vd `dl_purchase_sale_link`), giữ `dl_purchase` chỉ lo đơn mua.

#### A2 — `dl_inventory` phụ thuộc `dl_sale` (ngược chiều tự nhiên) *(Medium)*

`dl_inventory` chứa `models/dl_sale_order.py` (200 LOC) và `models/dl_sale_order_dispatch.py` — tức phân hệ Kho đang mở rộng model của phân hệ Bán. Về nghiệp vụ thì hợp lý (giao hàng bám đơn bán), nhưng về kiến trúc thì Kho lẽ ra là tầng dưới Bán.

**Đề xuất:** đảo chiều — đưa phần "đơn bán biết về giao hàng" sang `dl_sale` (hoặc module link riêng), để `dl_inventory` chỉ phụ thuộc `stock` + master data.

#### A3 — Không kế thừa `sale`/`purchase` chuẩn của Odoo *(High — ảnh hưởng dài hạn)*

Dự án **tự định nghĩa** `dl.sale.order`, `dl.sale.order.line`, `dl.purchase.order`, `dl.purchase.order.line` thay vì kế thừa `sale.order`/`purchase.order`. Manifest của `dl_sale` **không** depend `sale`; `dl_purchase` **không** depend `purchase`.

**Ảnh hưởng:**
- Mất toàn bộ hệ sinh thái Odoo: kế toán (`account.move`), báo cáo bán hàng chuẩn, portal khách hàng, `sale_stock`, e-commerce, EDI…
- Muốn tích hợp kế toán sau này phải tự viết cầu nối `dl.sale.order → account.move`.
- Ngược lại: **giảm rủi ro khi nâng cấp Odoo** vì không phụ thuộc nội thất của `sale`/`purchase`.

**Đánh giá:** đây là *đánh đổi có chủ đích*, không phải lỗi. Nhưng cần ghi nhận rõ trong tài liệu kiến trúc: hệ thống này **không** dùng được phân hệ kế toán Odoo mà không có công đoạn tích hợp riêng.

#### A4 — Không có `ir.actions.report` nào *(Medium)*

Kiểm tra toàn bộ XML: **0 định nghĩa `ir.actions.report`**. Toàn bộ chứng từ được sinh bằng Python thuần:

- `dl_sale/models/quotation_document.py` — `_build_docx()` (161 dòng), `_build_pdf()` (168 dòng) dùng `python-docx` + `reportlab`
- `dl_purchase/models/purchase_document.py` — `_dlm_build_pdf()` (99 dòng)
- `dl_inventory/models/vendor_return_document.py` — `_dlm_build_reject_report()` (145 dòng)

**Ảnh hưởng:** người dùng cuối/BA **không sửa được mẫu chứng từ** (QWeb template sửa được trong UI; code Python thì không). Mỗi lần đổi layout phải sửa code + deploy.

**Đề xuất:** chuyển sang QWeb report + `wkhtmltopdf` cho các chứng từ layout tĩnh. Giữ Python cho DOCX (Odoo không có engine DOCX).

#### A5 — File data mồ côi *(Low)*

`dl_technical/data/measurement_shape_data.xml` **tồn tại trên đĩa nhưng không được khai báo** trong `dl_technical/__manifest__.py`. Hoặc là file chết (nên xoá), hoặc là quên nạp (thiếu dữ liệu hình học đo lường).

---

# 2. CHẤT LƯỢNG SOURCE CODE

## ✅ Chất lượng cao hơn mặt bằng chung rõ rệt

Quét AST toàn bộ 124 file Python production:

| Kiểm tra | Kết quả |
|---|---|
| `except:` trần | **0** ✅ |
| `print()` trong code production | **0** ✅ |
| `TODO` / `FIXME` / `HACK` còn sót | **0** ✅ |
| Hard-code database ID (`browse(5)`…) | **0** ✅ |
| `eval()` / `exec()` | **0** ✅ (chỉ dùng `safe_eval`) |
| Compute `store=True` thiếu `@api.depends` | **0** ✅ |
| XML malformed | **0** ✅ |

**Mật độ comment rất cao và có giá trị thực.** Comment giải thích *tại sao* chứ không mô tả lại code. Ví dụ `dl_inventory/security/ir_rule.xml` giải thích rõ vì sao **cố ý không** thu hẹp theo `create_uid`; `dl_product/models/dl_product.py:793-796` giải thích vì sao giữ lại vế suy ngược làm lưới an toàn. Đây là tài sản bảo trì thật.

## ⚠️ Vấn đề chất lượng

#### C1 — Nuốt exception im lặng *(Medium)*

Có **2** chỗ `except Exception: pass` (không log, không xử lý):

| File | Dòng |
|---|---|
| `dl_config/models/res_users.py` | **117** |
| `dl_purchase/models/stock_lot.py` | **67** |

**Ảnh hưởng:** lỗi biến mất không dấu vết. Trên production, khi user báo "tạo user không gửi được mail" hoặc "lô hàng thiếu giá" thì log sạch trơn — không debug được.

**Sửa:**
```python
import logging
_logger = logging.getLogger(__name__)
...
except Exception:
    _logger.warning("Không đặt được giá lô %s", lot.name, exc_info=True)
```

#### C2 — Hàm quá dài *(Medium)*

15 hàm ≥ 80 dòng. Nặng nhất:

| Dòng | File:Line | Hàm |
|---:|---|---|
| 168 | `dl_sale/models/quotation_document.py:281` | `_build_pdf()` |
| 161 | `dl_sale/models/quotation_document.py:77` | `_build_docx()` |
| 145 | `dl_inventory/models/vendor_return_document.py:109` | `_dlm_build_reject_report()` |
| 143 | `dl_inventory/models/stock_warehouse.py:213` | `_dlm_setup_locations()` |
| 125 | `dl_technical/models/dl_quotation_request.py:1042` | `_dlm_suggest_candidates()` |
| 103 | `dl_sale/models/quotation_pricing_service.py:53` | `create_from_rfq()` |
| 99 | `dl_sale/models/quotation_pricing_service.py:387` | `_price_manufactured()` |

Các hàm dựng tài liệu (PDF/DOCX) dài là **chấp nhận được** — bản chất là code layout tuần tự. Đáng lo hơn là:

- **`create_from_rfq()` (103 dòng)** và **`_price_manufactured()` (99 dòng)** — đây là **logic tính giá lõi**, dài + phân nhánh nhiều ⇒ khó test từng nhánh, khó sửa an toàn.
- **`_dlm_suggest_candidates()` (125 dòng)** — thuật toán gợi ý, nên tách các bước chấm điểm ra hàm riêng.

**Đề xuất:** tách `_price_manufactured()` theo từng thành phần chi phí (vật tư / công đoạn / hao hụt / lợi nhuận) — vừa dễ test vừa khớp với cấu trúc `dl.quotation.price.component` đã có sẵn.

#### C3 — Thiếu file `.po` dịch *(Low)*

**0 file `.po`/`.pot`** trong toàn bộ 9 module. Chuỗi tiếng Việt được hard-code trực tiếp trong `_()`.

Chấp nhận được nếu hệ thống **chỉ dùng tiếng Việt**, nhưng khi đó `_()` chỉ mang tính hình thức. Nếu sau này cần song ngữ (khách nước ngoài xem báo giá), phải export lại toàn bộ.

---

# 3. TUÂN THỦ BEST PRACTICES ODOO

## ✅ Tuân thủ tốt

| Hạng mục | Đánh giá |
|---|---|
| **ACL** | 308 dòng, **100% model có ACL**, **0 dòng thiếu group** ✅ |
| **`mail.thread`** | 11 model có chatter + `mail.activity.mixin` ✅ |
| **`tracking=True`** | Dùng rộng khắp trên field nghiệp vụ quan trọng (giá, trạng thái, số lượng) ✅ |
| **`@api.constrains`** | ~70 constraint, phủ tốt (riêng `res_partner` 16 cái) ✅ |
| **`_sql_constraints`** | 9 file có, dùng đúng cho ràng buộc DB-level ✅ |
| **`@api.model_create_multi`** | Dùng đúng ở `dl_quotation.py:478` ✅ |
| **`safe_eval`** | Dùng thay `eval` ở `dl_product/models/dl_product.py:160` ✅ |
| **Partial unique index** | `dl_sale/models/dl_quotation.py:461` `init()` — dùng SQL trực tiếp vì Odoo helper không hỗ trợ UNIQUE + WHERE. **Cách làm đúng**, có comment giải thích ✅ |

**Ghi chú:** 6 model không có ACL đều là `AbstractModel` — **đúng chuẩn**, mixin không cần ACL. Không phải lỗi.

**Ghi chú 2:** các XML ID "trùng" trong `dl_product/views/menus.xml` (`menu_dl_pricing_root` ở dòng 116 và 125) là **cố ý** — pattern `<menuitem>` rồi `<record>` để xoá tường minh field cũ trên DB đã nâng cấp, có comment giải thích ở dòng 122-124. **Không phải lỗi.**

## ⚠️ Vi phạm best practice

#### B1 — Thiếu `@api.depends_context('uid')` trên compute phụ thuộc người dùng *(Medium)*

Đây là lỗi **không nhất quán trong chính codebase**: dự án **đã biết** pattern này và dùng đúng ở 2 chỗ, nhưng bỏ sót ở các chỗ tương tự.

**Dùng ĐÚNG:**
- `dl_config/models/pricing_approval.py:155` → `@api.depends_context("uid")` cho `can_resolve`
- `dl_technical/models/dl_quotation_request.py:918`

**BỎ SÓT** (compute đọc `self.env.user` nhưng không khai báo `depends_context`):

| File:Line | Field | Compute |
|---|---|---|
| `dl_product/models/dl_product.py:195` | `dlm_is_price_editor` | `_compute_dlm_is_price_editor` (đọc `user.has_group`) |
| `dl_product/models/dl_product.py:242` | `dlm_can_change_kind` | `_compute_dlm_can_change_kind` (đọc `user.has_group`) |
| `dl_technical/models/dl_quotation_request.py:542, 1358` | `is_technician` | `_compute_is_technician` |

**Nguyên nhân:** các field này còn khai `compute_sudo=True`, nghĩa là compute chạy trong môi trường superuser. Không khai `depends_context('uid')` thì khoá cache **không chứa uid** ⇒ trong cùng một transaction/worker, giá trị tính cho user A có thể phục vụ lại cho user B.

**Ảnh hưởng thực tế: THẤP về bảo mật** — vì đây là field *gating UI* (readonly ô giá bán, readonly ô loại SP), còn **chặn thật nằm ở `write()` guard** (`dl_product/models/dl_product.py:943` kiểm `self.env.su and self.env.uid != SUPERUSER_ID`). Sai cache ⇒ user thấy ô mở/khoá sai, nhưng lưu vẫn bị chặn.

**Sửa:** thêm `@api.depends_context('uid')` lên 3 compute trên (2 dòng code).

#### B2 — Multi-company không nhất quán *(Medium)*

| Model | `company_id` | `ir.rule` multi-company |
|---|---|---|
| `dl.pricing.*` (8 model, `dl_config`) | ✅ | ✅ 8 global rule `[('company_id','in',company_ids)]` |
| `dl.quotation` | ✅ có field | ❌ **không có rule** |
| `dl.sale.order` | ✅ có field | ❌ **không có rule** |
| `dl.purchase.order` | ✅ có field | ❌ **không có rule** |
| `dl.quotation.request` | ❌ **không có** | ❌ |
| `dl.bom` | ❌ **không có** | ❌ |

**Ảnh hưởng:** hệ thống hiện chỉ chạy đúng ở chế độ **một công ty**. Nếu sau này bật multi-company, dữ liệu báo giá/đơn hàng/BOM sẽ rò rỉ chéo giữa các công ty.

**Đề xuất:** nếu chốt single-company → **bỏ hẳn `company_id`** cho nhất quán, ghi rõ trong tài liệu. Nếu có kế hoạch multi-company → bổ sung `company_id` + global rule cho cả 5 model còn thiếu **trước khi có dữ liệu thật**.

#### B3 — Record rule chỉ phủ 4 model *(Medium)*

24 `ir.rule` nhưng chỉ nằm trên `res.partner`, `product.product/template/category`, `stock.picking/move/move.line`, và `dl.pricing.*`.

**Toàn bộ ~50 model nghiệp vụ custom (`dl.quotation`, `dl.sale.order`, `dl.purchase.order`, `dl.bom`, `dl.drawing`, `dl.quotation.request`…) KHÔNG có record rule nào** — chỉ có ACL cấp model.

**Nghĩa là:** mọi user thuộc nhóm BA đọc/sửa được **toàn bộ** báo giá của **mọi** nhân viên kinh doanh, không giới hạn theo người phụ trách/khách hàng.

Đây **có thể là thiết kế cố ý** (ERP nội bộ, quy mô nhỏ, cần nhìn chéo). Nhưng cần **xác nhận với đặc tả phân quyền** — nếu ma trận RBAC yêu cầu "Sales chỉ thấy khách của mình" thì đây là lỗ hổng phân quyền dữ liệu.

---

# 4. ĐÁNH GIÁ DATABASE

## Số liệu

- 759 field · **143 Many2one** · 31 One2many · 19 Many2many
- **36 field có `index=True`**
- **54 compute `store=True`** — **tất cả đều có `@api.depends`** ✅ (không có lỗi "field không bao giờ tính lại")

## ✅ Index đặt đúng chỗ

Các FK nóng và field lọc thường xuyên đã có index — ví dụ:

```
dl_sale/models/dl_quotation.py:105,141   origin_quotation_id, quotation_request_id
dl_sale/models/dl_sale_order.py:22       quotation_id
dl_purchase/models/dl_purchase_order.py:48,482  name, order_id
dl_inventory/models/stock_picking.py:213,227    dlm_origin_picking_id, dlm_sale_order_id
dl_partner/models/res_partner.py:150,163,224    dlm_code, dlm_supplier_code, dlm_name_key
dl_config/models/*.py                    state, company_id (10 chỗ)
```

Đặc biệt `dlm_name_key` (`res_partner.py:224`) có index — đúng, vì nó phục vụ check trùng tên.

## ⚠️ Vấn đề

#### D1 — 94/143 Many2one **không khai `ondelete`** *(High)*

Odoo mặc định `ondelete='set null'` khi không khai báo. Với FK **bắt buộc** (`required=True`), điều này nguy hiểm: xoá bản ghi cha ⇒ con thành `NULL` ⇒ **vi phạm NOT NULL ở tầng DB hoặc để lại dữ liệu mồ côi**.

Tập trung nhiều nhất:

| Số lượng | File |
|---:|---|
| 11 | `dl_technical/wizard/rfq_resolve_wizard.py` |
| 9 | `dl_technical/models/dl_quotation_request.py` |
| 8 | `dl_sale/models/dl_quotation.py` |
| 7 | `dl_sale/models/dl_sale_order.py` |
| 5 | `dl_config/models/pricing_approval.py` |
| 5 | `dl_purchase/models/dl_purchase_order.py` |

**Ghi chú giảm nhẹ:** với wizard (`TransientModel`) thì ít nghiêm trọng vì bản ghi tự dọn. Nhưng **`dl_quotation.py` (8) và `dl_sale_order.py` (7) là model thường trú** — đây mới là chỗ cần sửa.

**Sửa:** rà từng M2O trên model thường trú và khai tường minh:
- FK tới master data cần giữ lịch sử → `ondelete='restrict'`
- FK tới dòng cha (line → header) → `ondelete='cascade'`
- FK tham chiếu tuỳ chọn → `ondelete='set null'`

#### D2 — Bảng có nguy cơ chậm khi dữ liệu lớn

| Bảng | Rủi ro |
|---|---|
| `dl_quotation` + `dl_quotation_line` + `dl_quotation_price_component` | 9 compute store trên `dl_quotation`; mỗi báo giá sinh nhiều price component ⇒ bảng component phình nhanh nhất hệ thống |
| `stock_move` / `stock_move_line` | Kế thừa từ `stock`, vốn đã lớn; `dl_inventory` thêm compute + rule |
| `dl_bom_line` | `_compute_used_in_parent_count` quét `search_count` toàn bảng (xem P3) |

#### D3 — Field nên bổ sung index

Dựa trên domain thực tế đang được search nhiều:

| Field | Lý do |
|---|---|
| `dl.quotation.state` | Lọc theo trạng thái ở list view + cron hết hạn (`dl_sale/data/quotation_cron.xml`) |
| `dl.sale.order.state` | Tương tự |
| `dl.bom.line.material_id` | Bị `search_count` trong `_compute_used_in_parent_count` (`dl_bom.py:201`) |
| `dl.drawing.product_id` | Bị search tới 3 lần trong `_compute_drawing_ref` (`dl_bom.py:235-240`) |
| `dl.quotation.request.status` | Lọc trạng thái RFQ |

> `dl_config` đã index `state` ở 10 model — nên áp dụng cùng chuẩn cho `dl_sale`/`dl_technical`.

---

# 5. KIỂM TRA BẢO MẬT

## 🔴 CRITICAL — Phải sửa trước khi lên production

### S1 — 8 tài khoản demo mật khẩu `123456` được cài vào PRODUCTION (bao gồm tài khoản Admin)

**File:** `dlm-erp/dl_base/data/demo_users_data.xml`
**Khai báo tại:** `dlm-erp/dl_base/__manifest__.py` → key **`'data'`** (KHÔNG phải `'demo'`)

```xml
<record id="demo_user_admin" model="res.users">
    <field name="name">Admin IT</field>
    <field name="login">admin.it@gmail.com</field>
    <field name="password">123456</field>
    <field name="groups_id" eval="[(6, 0, [ref('dl_base.dl_group_admin')])]" />
</record>
```

Toàn bộ 8 tài khoản, **tất cả mật khẩu `123456`**:

| Login | Nhóm quyền |
|---|---|
| `admin.it@gmail.com` | **`dl_group_admin`** ← toàn quyền, cấu hình được RBAC |
| `ceo@gmail.com` | `dl_group_ceo` |
| `truongkd@gmail.com` | `dl_group_sales_manager` |
| `ba@gmail.com` | `dl_group_ba` |
| `kythuat@gmail.com` | `dl_group_tech` |
| `ketoan@gmail.com` | `dl_group_accountant` |
| `muahang@gmail.com` | `dl_group_purchasing` |
| `thukho@gmail.com` | `dl_group_warehouse` |

**Nguyên nhân gốc (quan trọng):**
Kiểm tra toàn bộ 9 manifest → **KHÔNG module nào có key `'demo'`**. Mọi dữ liệu demo đều nằm trong `'data'`.

⇒ **`without_demo = All` trong `odoo.conf` HOÀN TOÀN VÔ TÁC DỤNG** với các file này. Odoo chỉ bỏ qua file trong key `'demo'`; file trong `'data'` **luôn luôn được nạp**.

**Ảnh hưởng:** bất kỳ ai truy cập được tên miền production đều đăng nhập được `admin.it@gmail.com` / `123456` và chiếm **toàn quyền hệ thống** — đọc/sửa/xoá mọi dữ liệu, cấp lại quyền cho chính mình qua màn RBAC.

**Cách sửa (chọn 1):**

*Cách A — đúng chuẩn Odoo (khuyến nghị):* chuyển sang key `demo`
```python
# dl_base/__manifest__.py
'data': [
    'security/groups.xml',
    'security/ir.model.access.csv',
    'data/language_data.xml',
    'data/currency_data.xml',
    'views/login_templates.xml',
    'views/actions.xml',
    'views/menus.xml',
    # BỎ 2 dòng demo ra khỏi 'data'
],
'demo': [
    'data/demo_users_data.xml',
    'data/demo_user_language_data.xml',
],
```

*Cách B — nếu cần giữ user để bàn giao:* giữ nhưng **bắt buộc đổi mật khẩu ngay sau deploy**, và xoá tài khoản không dùng. Vẫn phải làm Cách A cho lần cài mới.

**Kiểm chứng sau khi sửa:**
```sql
SELECT login, active FROM res_users WHERE login LIKE '%@gmail.com';
-- phải rỗng trên DB production
```

> **Các file demo khác cũng đang nằm trong `'data'`** (cùng nguyên nhân, mức độ thấp hơn vì chỉ là dữ liệu mẫu, không phải tài khoản):
> - `dl_product/data/dl_demo_data.xml` (9 record sản phẩm mẫu)
> - `dl_technical/data/dl_demo_data.xml` (20 record)
> - `dl_demo/data/demo_partners.xml` (7), `demo_products.xml` (3)
>
> `dl_config/data/pricing_seed.xml` (18) và `dl_product/data/material_seed_data.xml` (29) là **seed cấu hình hợp lệ** — giữ trong `'data'` là đúng.

---

### S2 — `odoo.conf` chứa secret dạng plaintext

**File:** `odoo.conf` (thư mục gốc)

```ini
db_password    = 123456
smtp_password  = qeppkjbpjwehxrad     # Gmail App Password thật
smtp_user      = quannguyenkm16122004@gmail.com
```

**✅ Giảm nhẹ quan trọng:** `odoo.conf` **đã có trong `.gitignore`** (dòng 6) và **đã kiểm chứng là KHÔNG được git theo dõi** (`git ls-files` không trả về kết quả). **Secret chưa bị lộ lên repo.**

**Nhưng vẫn phải xử lý:**
1. **Gmail App Password `qeppkjbpjwehxrad` đang nằm plaintext trên đĩa** → thu hồi và tạo lại tại Google Account, vì nó đã xuất hiện trong phiên làm việc này.
2. `db_password = 123456` — không dùng được cho production.
3. Trên VPS: `chown odoo:odoo /etc/odoo/odoo.conf && chmod 640 /etc/odoo/odoo.conf`.

---

### S3 — `list_db = True` (lộ Database Manager)

**File:** `odoo.conf:32`

Cho phép truy cập `/web/database/manager` — trang liệt kê, **tạo, sao lưu, khôi phục, XOÁ** database. Kết hợp với `admin_passwd` yếu là mất toàn bộ dữ liệu.

**✅ Giảm nhẹ:** `admin_passwd` **đã được hash bằng pbkdf2-sha512** (`odoo.conf:3`) — đây là điểm tốt, không phải plaintext.

**Sửa bắt buộc:**
```ini
list_db = False
```
và chặn thêm ở Nginx (xem §8).

---

## 🟢 Những mặt bảo mật LÀM TỐT

Cần ghi nhận — phần lớn kiến trúc bảo mật của dự án này **trên mức trung bình**:

| Hạng mục | Kết quả kiểm tra |
|---|---|
| **SQL Injection** | ✅ **Không có.** Mọi `cr.execute` đều tham số hoá bằng `%s` + list. 2 chỗ dùng f-string đã kiểm chứng an toàn: `dl_sale/migrations/17.0.1.14.0/post-migration.py:20` (tên bảng lấy từ tuple hằng `("dl_quotation","dl_sale_order")`) và `dl_sale/models/dl_quotation.py:475` (dùng `self._table` — hằng của framework, có comment giải thích) |
| **XSS** | ✅ **Không có `t-raw`** trong toàn bộ QWeb. Python dùng `Markup("...") % value` — đây là pattern **đúng**, markupsafe tự escape biến nội suy |
| **`eval()`** | ✅ Không dùng. Chỉ `safe_eval` (`dl_product/models/dl_product.py:160`) |
| **Controller** | ✅ Chỉ **2** controller. `dl_inventory/controllers/scrap_banner.py:46` dùng `auth="user"`, trả HTML tĩnh không nhận input. `dl_base/controllers/main.py` kế thừa `@http.route()` từ `web.Home` — đúng idiom, không mở route mới |
| **CSRF** | ✅ Không có route `type="http"` + `POST` tự viết ⇒ không có bề mặt CSRF mới |
| **Public/portal** | ✅ **Không có** `auth="public"` hay `auth="none"` |
| **Hard-code DB ID** | ✅ Không có |
| **`SUPERUSER_ID`** | ✅ Dùng chủ yếu trong migration (đúng). Trong model dùng để *kiểm tra* (`self.env.uid != SUPERUSER_ID`), không phải để leo quyền |

### `sudo()` — 222 lời gọi, nhưng có kỷ luật

Số lượng lớn, tuy nhiên **có 61 lần kiểm tra quyền tường minh** (`has_group` / `check_access_rights`) và pattern nhất quán là **guard trước, sudo sau**:

```python
# dl_product/models/dl_product.py:802-816
def set_dlm_waste(self, vals):
    user = self.env.user
    if not self.env.su and not (user.has_group("dl_base.dl_group_tech")
            or user.has_group("dl_base.dl_group_accountant")
            or user.has_group("dl_base.dl_group_admin")):
        raise AccessError(_("Chỉ Kỹ thuật/Kế toán/Admin được sửa hao hụt vật tư."))
    allowed = {"dlm_waste_rate", "dlm_scrap_product_id"}   # ← allowlist field
    self.sudo().write({k: v for k, v in vals.items() if k in allowed})
```

Đây là cách làm **đúng**: kiểm nhóm + allowlist field, không cho ghi field tuỳ ý.

**Màn hình RBAC (`dl_base/models/dl_rbac.py`) — thiết kế tốt:** tất cả method ghi (`create_role`, `rename_role`, `delete_role`, `set_crud`, `set_operation`) đều gọi `_check_rbac_admin()` **ở dòng đầu tiên**, raise `AccessError` nếu không phải Admin. Không có đường vòng leo quyền qua RPC.

---

## Bảng tổng hợp rủi ro bảo mật

| # | Rủi ro | Mức | File |
|---|---|---|---|
| S1 | 8 user demo `123456` (có Admin) cài vào production; `without_demo` vô hiệu | 🔴 **Critical** | `dl_base/data/demo_users_data.xml` + `dl_base/__manifest__.py` |
| S2 | Secret plaintext (SMTP app password, db password) | 🔴 **Critical** | `odoo.conf:10,49` |
| S3 | `list_db = True` — lộ Database Manager | 🟠 **High** | `odoo.conf:32` |
| S4 | `proxy_mode = False` sau Nginx | 🟠 **High** | `odoo.conf:43` |
| S5 | Thiếu record rule trên ~50 model nghiệp vụ | 🟡 **Medium** | (xem B3) |
| S6 | Multi-company không nhất quán | 🟡 **Medium** | (xem B2) |
| S7 | Nuốt exception im lặng — che dấu vết tấn công | 🟡 **Medium** | `dl_config/models/res_users.py:117`, `dl_purchase/models/stock_lot.py:67` |
| S8 | Thiếu `depends_context('uid')` — gating UI sai | 🟢 **Low** | (xem B1) |

---

# 6. ĐÁNH GIÁ HIỆU NĂNG

## ⚠️ N+1 query trong compute — đã xác minh

Quét AST tìm lời gọi ORM nằm trong vòng `for`: **145 vị trí**. Lọc ra các trường hợp thực sự nguy hiểm (compute chạy trên list view):

#### P1 — `_compute_pending_request` *(High — sửa rất dễ)*

**File:** `dl_config/models/pricing_matrix.py:103`

```python
def _compute_pending_request(self):
    for rec in self:
        req = rec._pending_requests()[:1]      # ← 1 SELECT cho MỖI dòng
        rec.pending_request_id = req
        rec.has_pending_request = bool(req)
```

**Điểm mấu chốt:** hàm `_pending_requests()` ở dòng 109-115 **đã hỗ trợ batch sẵn** (`("res_id", "in", self.ids)`), nhưng lại bị gọi trên từng `rec` ⇒ vứt bỏ khả năng batch.

**Ảnh hưởng:** list view ma trận phê duyệt N dòng ⇒ **N query**.

**Sửa (gom 1 query):**
```python
def _compute_pending_request(self):
    reqs = self._pending_requests()                     # 1 SELECT duy nhất
    by_res = {}
    for r in reqs:
        by_res.setdefault(r.res_id, r)
    for rec in self:
        req = by_res.get(rec.id)
        rec.pending_request_id = req or False
        rec.has_pending_request = bool(req)
```

#### P2 — `_compute_dlm_supplierinfo_count` *(High — sửa 1 dòng)*

**File:** `dl_partner/models/res_partner.py:258-264`

```python
@api.depends('dlm_supplierinfo_ids')          # ← đã depends vào O2M rồi!
def _compute_dlm_supplierinfo_count(self):
    for rec in self:
        rec.dlm_supplierinfo_count = self.env['product.supplierinfo'].sudo(
        ).search_count([('partner_id', '=', rec.id)])   # ← search_count thừa
```

Field đã `@api.depends('dlm_supplierinfo_ids')` — nghĩa là O2M **đã được nạp sẵn vào cache**. Gọi thêm `search_count` là hoàn toàn thừa.

**Sửa:**
```python
for rec in self:
    rec.dlm_supplierinfo_count = len(rec.dlm_supplierinfo_ids)
```
(Nếu cần `sudo` để né ACL: `len(rec.sudo().dlm_supplierinfo_ids)`.)

#### P3 — `_compute_used_in_parent_count` *(Medium)*

**File:** `dl_technical/models/dl_bom.py:196-204` — `search_count` trên `dl.bom.line` cho **mỗi** BOM.

**Sửa:** dùng `read_group` gom 1 lần:
```python
@api.depends("product_id")
def _compute_used_in_parent_count(self):
    mats = self.filtered(lambda r: r.product_id.product_kind == "material_processed")
    counts = {}
    if mats:
        data = self.env["dl.bom.line"].sudo().read_group(
            [("material_id", "in", mats.product_id.ids)],
            ["material_id"], ["material_id"])
        counts = {d["material_id"][0]: d["material_id_count"] for d in data}
    for rec in self:
        rec.dlm_used_in_parent_count = counts.get(rec.product_id.id, 0)
```

#### P4 — `_compute_drawing_ref` — tối đa **3 search mỗi bản ghi** *(Medium)*

**File:** `dl_technical/models/dl_bom.py:223-245`

```python
drawing = Drawing.search(domain + [("is_current","=",True)], limit=1) \
    or Drawing.search(domain + [("status","=","confirmed")], order="version desc", limit=1) \
    or Drawing.search(domain, order="version desc", limit=1)
```

**✅ Giảm nhẹ (đã kiểm chứng):** field `drawing_id` chỉ xuất hiện ở **form view** (`dl_technical/views/bom_views.xml:190`, trong `<group>` có `groups=`), **không có trên list view**. Vậy chi phí thực tế là ~3 query mỗi lần mở form — **khó chịu nhưng không phải thảm hoạ**.

**Sửa:** gộp 3 lần search thành 1 với `order` ưu tiên:
```python
drawing = Drawing.search(domain, order="is_current desc, version desc", limit=1)
```

#### P5 — Constraint search theo từng bản ghi *(Medium)*

`dl_partner/models/res_partner.py` có **16 `@api.constrains`**, trong đó nhiều cái search từng dòng:

| Dòng | Hàm |
|---|---|
| 944 | `_check_contact_unique_name()` |
| 991 | `_check_unique_tax_code()` |
| 1027, 1037 | `_check_unique_contact_channel()` |

**Ảnh hưởng:** chỉ đau khi **import hàng loạt** (import 1000 đối tác ⇒ ~4000 query). Thao tác lẻ thì không đáng kể.

**Đề xuất:** với các ràng buộc duy nhất đơn giản (mã số thuế, `dlm_code`), thay bằng `_sql_constraints` UNIQUE — DB tự lo, nhanh hơn nhiều lần và an toàn khi chạy đồng thời.

## ⚠️ P6 — `workers = None` *(Critical cho production)*

**File:** `odoo.conf:68`

Odoo chạy chế độ **đơn tiến trình đa luồng** — do **GIL của Python**, thực tế chỉ tận dụng được ~1 CPU core. Với 8 vai trò dùng đồng thời, hệ thống sẽ **treo hàng loạt** khi có 1 request nặng (xuất PDF báo giá, nổ BOM).

Ngoài ra `limit_time_cpu`, `limit_time_real`, `limit_memory_soft/hard` đều `None` ⇒ **một request lỗi vòng lặp vô hạn sẽ ăn hết RAM và giết cả server**, không có cơ chế tự phục hồi.

Xem §7 và §8 để biết cấu hình đúng.

## ✅ Điểm hiệu năng tốt

- 36 field có index, phủ được các FK nóng
- 54 compute `store=True` — tránh tính lại khi đọc list
- `_compute_drawing_ref` chỉ ở form, không ở list (đã kiểm chứng)
- `dlm_blocked_product_ids`, `dlm_supply_level` tuy là compute nặng nhưng đều `invisible="1"` ở form đơn lẻ, không nằm trên list

---

# 7. KHẢ NĂNG TRIỂN KHAI PRODUCTION

## 🔴 Phát hiện lớn nhất: KHÔNG CÓ BẤT KỲ TÀI SẢN TRIỂN KHAI NÀO

Tìm kiếm toàn bộ repo (trừ `odoo-17.0/`, `venv/`):

| Thành phần | Trạng thái |
|---|---|
| `Dockerfile` | ❌ **Không có** |
| `docker-compose.yml` | ❌ **Không có** |
| Nginx config | ❌ **Không có** |
| `requirements.txt` (cho module custom) | ❌ **Không có** |
| systemd service unit | ❌ **Không có** |
| Script backup | ❌ **Không có** |
| Script deploy / CI-CD | ❌ **Không có** |
| Tài liệu deploy | ❌ **Không có** (README chỉ có `pip install` cho dev) |

`scripts/` chỉ chứa tiện ích **dev**: `reset_demo_db.ps1` (PowerShell — Windows), `_recreate_db.py`, `purge_stock_data.py`.

⇒ **Dự án hiện ở trạng thái "chạy được trên máy dev Windows", chưa có đường đi lên Linux production.**

## Phân tích `odoo.conf` hiện tại

| Tham số | Giá trị hiện tại | Production | Mức |
|---|---|---|---|
| `addons_path` | `D:\FPTU\...` (Windows) | `/opt/odoo/odoo-17.0/addons,/opt/odoo/dlm-erp` | 🔴 Critical |
| `data_dir` | `c:\users\admin\appdata\...` | `/var/lib/odoo` | 🔴 Critical |
| `workers` | `None` | `5` (xem §8) | 🔴 Critical |
| `db_password` | `123456` | mật khẩu mạnh ≥24 ký tự | 🔴 Critical |
| `smtp_password` | plaintext trong file | biến môi trường / file 640 | 🔴 Critical |
| `list_db` | `True` | `False` | 🟠 High |
| `proxy_mode` | `False` | `True` | 🟠 High |
| `dbfilter` | `^dlm_dev$` | `^dlm_prod$` | 🟠 High |
| `logfile` | rỗng (ra stdout) | `/var/log/odoo/odoo.log` | 🟠 High |
| `limit_time_cpu` | `None` | `600` | 🟠 High |
| `limit_time_real` | `None` | `1200` | 🟠 High |
| `limit_memory_soft` | `None` | `2147483648` (2GB) | 🟠 High |
| `limit_memory_hard` | `None` | `2684354560` (2.5GB) | 🟠 High |
| `http_interface` | `127.0.0.1` | `127.0.0.1` ✅ giữ nguyên | ✅ |
| `admin_passwd` | pbkdf2-sha512 hash | ✅ giữ (đổi giá trị) | ✅ |
| `db_name` | `dlm_dev` | `dlm_prod` | 🟡 Medium |
| `without_demo` | `All` | ⚠️ **vô tác dụng** — xem S1 | 🔴 Critical |
| `max_cron_threads` | `2` | `2` ✅ | ✅ |
| `gevent_port` | `8072` | `8072` ✅ (cần cho longpolling) | ✅ |

## Phụ thuộc Python ngoài

Từ manifest:
- `dl_sale` → `docx` (**pip: `python-docx`**), `reportlab`
- `dl_purchase` → `reportlab`

⚠️ Tên import (`docx`) ≠ tên gói pip (`python-docx`). Cần tạo `requirements.txt`:

```
# requirements-dlm.txt
python-docx==1.1.2
reportlab==4.2.5
```

## `odoo.conf` production đề xuất (đầy đủ)

```ini
[options]
; ── Đường dẫn ────────────────────────────────────────────
addons_path = /opt/odoo/odoo-17.0/addons,/opt/odoo/dlm-erp
data_dir    = /var/lib/odoo

; ── Database ─────────────────────────────────────────────
db_host     = 127.0.0.1
db_port     = 5432
db_user     = odoo
db_password = <MẬT_KHẨU_MẠNH_>=24_KÝ_TỰ>
db_name     = dlm_prod
dbfilter    = ^dlm_prod$
db_maxconn  = 32
db_sslmode  = prefer
list_db     = False

; ── Bảo mật ──────────────────────────────────────────────
admin_passwd = <HASH_pbkdf2_MỚI>
proxy_mode   = True

; ── HTTP (chỉ nghe localhost — Nginx là cổng ra duy nhất) ─
http_enable    = True
http_interface = 127.0.0.1
http_port      = 8069
gevent_port    = 8072

; ── Workers & giới hạn (VPS 2 vCPU / 8GB) ────────────────
workers               = 5
max_cron_threads      = 2
limit_time_cpu        = 600
limit_time_real       = 1200
limit_time_real_cron  = 1800
limit_request         = 8192
limit_memory_soft     = 2147483648
limit_memory_hard     = 2684354560

; ── Log ──────────────────────────────────────────────────
logfile    = /var/log/odoo/odoo.log
log_level  = warn
log_handler = :INFO
syslog     = False

; ── Email (KHÔNG để mật khẩu ở đây nếu tránh được) ───────
smtp_server   = smtp.gmail.com
smtp_port     = 587
smtp_ssl      = True
smtp_user     = <email>
smtp_password = <APP_PASSWORD_MỚI_SAU_KHI_THU_HỒI>
email_from    = <email>

; ── Khác ─────────────────────────────────────────────────
without_demo        = All
server_wide_modules = base,web
unaccent            = True     ; ← BẬT: tìm kiếm tiếng Việt không dấu
transient_age_limit = 1.0
```

> **Lưu ý `unaccent = True`:** hệ thống này toàn tiếng Việt và có logic so trùng tên
> (`_dlm_normalize_name` ở `dl_product/models/dl_product.py:820` **cố ý giữ dấu**).
> Bật `unaccent` giúp người dùng gõ không dấu vẫn tìm ra. Cần cài extension:
> `CREATE EXTENSION IF NOT EXISTS unaccent;` trên DB.

---

# 8. HẠ TẦNG VPS

## Cấu hình đề xuất

| Hạng mục | Đề xuất | Lý do (dựa trên số liệu đo được) |
|---|---|---|
| **OS** | **Ubuntu 24.04 LTS** | LTS đến 2029. Python 3.12 mặc định — khớp `.pyc` hiện tại (`cpython-312`), không phải build lại |
| **PostgreSQL** | **16** | Đã chốt trong dự án. Odoo 17 hỗ trợ chính thức; có `pg_get_constraintdef()` mà dự án cần |
| **CPU** | **2 vCPU** (tối thiểu) — 4 nếu >20 user đồng thời | Công thức Odoo: `workers = 2×core + 1` ⇒ 2 core = 5 worker, đủ cho ~15-20 user đồng thời |
| **RAM** | **8 GB** | 5 worker × ~250MB (worker Odoo tải nặng do 24.5k LOC + OWL assets) ≈ 1.5GB, + cron 2×250MB, + PostgreSQL ~2GB shared_buffers, + OS ~1GB, + dư cho build assets ≈ 8GB. **4GB sẽ chật khi build asset lần đầu** |
| **Ổ cứng** | **60 GB NVMe** | Odoo core ~1GB + custom ~50MB + filestore (bản vẽ kỹ thuật `dl.drawing` + ảnh RFQ `dl.quotation.request.line.image` — **đây là phần phình nhanh nhất**) + DB + backup 7 ngày |
| **Swap** | **4 GB** | Đệm cho lúc build assets & pg_dump. Đặt `vm.swappiness=10` để không swap sớm |
| **Triển khai** | **Docker Compose** | Đã chốt trong dự án. Lý do: pin chính xác Python 3.12 + PostgreSQL 16 + `python-docx`/`reportlab`, rollback bằng đổi tag, tách biệt khỏi OS |
| **Nginx** | Reverse proxy + TLS | Bắt buộc: Odoo không nên hứng traffic trực tiếp |
| **SSL** | Let's Encrypt (certbot) | Miễn phí, tự gia hạn |
| **Firewall** | UFW: chỉ mở 22, 80, 443 | **Đóng 5432 và 8069 khỏi Internet** |
| **Backup** | `pg_dump` + filestore, hằng ngày, giữ 7-30 ngày, **có off-site** | Backup cùng máy = không phải backup |
| **Monitoring** | Netdata (nhẹ) hoặc Prometheus + node_exporter | Cảnh báo RAM/disk/worker |
| **Log rotate** | logrotate, giữ 14 ngày, nén | `logfile` sẽ phình nhanh với `log_handler=:INFO` |

## Vì sao Docker chứ không Native?

**Ưu tiên Docker cho dự án này** vì:
1. Cần **chính xác** Python 3.12 (file `.pyc` hiện tại là `cpython-312`) — Ubuntu 24.04 có sẵn nhưng Docker đảm bảo không lệch khi OS cập nhật.
2. Có phụ thuộc ngoài (`python-docx`, `reportlab`) + `wkhtmltopdf` nếu chuyển sang QWeb report → dễ pin trong image.
3. Rollback nhanh khi deploy hỏng (đổi tag image), quan trọng vì dự án **chưa có CI**.

## `docker-compose.yml` đề xuất

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    secrets: [db_password]
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 10s
      retries: 5

  odoo:
    build: .
    depends_on:
      db: {condition: service_healthy}
    volumes:
      - odoo-data:/var/lib/odoo          # filestore + sessions
      - ./dlm-erp:/opt/odoo/dlm-erp:ro   # module custom (read-only)
      - ./odoo.conf:/etc/odoo/odoo.conf:ro
      - ./logs:/var/log/odoo
    ports:
      - "127.0.0.1:8069:8069"            # CHỈ localhost — Nginx ở host
      - "127.0.0.1:8072:8072"
    restart: unless-stopped

secrets:
  db_password:
    file: ./secrets/db_password.txt      # chmod 600, trong .gitignore

volumes:
  pgdata:
  odoo-data:
```

`Dockerfile`:
```dockerfile
FROM odoo:17.0
USER root
COPY requirements-dlm.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements-dlm.txt
USER odoo
```

## Nginx — cấu hình đầy đủ (kèm chặn Database Manager)

```nginx
upstream odoo      { server 127.0.0.1:8069; }
upstream odoochat  { server 127.0.0.1:8072; }

server {
    listen 80;
    server_name erp.dailinh.vn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name erp.dailinh.vn;

    ssl_certificate     /etc/letsencrypt/live/erp.dailinh.vn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/erp.dailinh.vn/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # ── Header bảo mật ──────────────────────────────────
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options    nosniff always;
    add_header X-Frame-Options           SAMEORIGIN always;
    add_header Referrer-Policy           strict-origin-when-cross-origin always;

    # ── CHẶN Database Manager (lớp phòng thủ thứ 2 cho S3) ──
    location ~* ^/web/database/(manager|create|duplicate|drop|backup|restore) {
        return 404;
    }

    # ── Upload bản vẽ kỹ thuật (dl.drawing) cần body lớn ──
    client_max_body_size 50M;

    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;   # ← proxy_mode=True cần header này
    proxy_read_timeout 1200s;                     # khớp limit_time_real

    location /websocket {
        proxy_pass http://odoochat;
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://odoo;
        proxy_redirect off;
    }

    location ~* /web/static/ {
        proxy_cache_valid 200 90m;
        expires 864000;
        proxy_pass http://odoo;
    }

    gzip on;
    gzip_types text/css text/plain application/javascript application/json image/svg+xml;
}
```

## Firewall

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # cân nhắc đổi port + fail2ban
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
# KHÔNG mở 5432, 8069, 8072
```

## Backup — script đề xuất

```bash
#!/bin/bash
# /opt/odoo/backup.sh — chạy 02:00 hằng ngày
set -euo pipefail
DEST=/var/backups/odoo
DATE=$(date +%F)
mkdir -p "$DEST"

docker compose exec -T db pg_dump -U odoo -Fc dlm_prod \
    > "$DEST/dlm_prod_$DATE.dump"

tar czf "$DEST/filestore_$DATE.tar.gz" \
    -C /var/lib/docker/volumes/odoo-data/_data filestore

find "$DEST" -name '*.dump'    -mtime +30 -delete
find "$DEST" -name '*.tar.gz'  -mtime +30 -delete

# BẮT BUỘC: đẩy off-site
rclone copy "$DEST" remote:dlm-erp-backup --max-age 25h
```

```cron
0 2 * * * /opt/odoo/backup.sh >> /var/log/odoo/backup.log 2>&1
```

> ⚠️ **Backup phải được kiểm chứng bằng restore thử.** Backup chưa từng restore = chưa có backup.
> Filestore chứa **bản vẽ kỹ thuật** — mất filestore là mất tài sản trí tuệ, DB không cứu được.

## Log rotation

```
/var/log/odoo/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su odoo odoo
}
```

---

# 9. KHẢ NĂNG MỞ RỘNG

| Khía cạnh | Điểm | Nhận xét dựa trên code |
|---|---|---|
| **Thêm module mới** | 🟢 **Tốt** | Kiến trúc phân tầng rõ, `dl_base` mỏng (512 LOC). Đặc biệt: **hệ RBAC tự mở rộng** — mỗi module khai `data/rbac_features.xml` là chức năng mới **tự hiện** trong ma trận phân quyền (`dl_base/models/dl_rbac.py:27-29`). Đây là thiết kế xuất sắc |
| **Nâng cấp Odoo** | 🟡 **Trung bình-Khá** | ✅ Thuận lợi: không phụ thuộc `sale`/`purchase` (ít bị vỡ khi Odoo đổi nội thất); có 25 migration script theo version. ⚠️ Rủi ro: kế thừa sâu `stock` (`stock.picking` 3 file, `stock.move`, `stock.quant._apply_inventory` override ở `stock_quant.py:41`); ~13k LOC OWL/SCSS bám vào internal của `web` — **OWL là chỗ dễ vỡ nhất khi lên Odoo 18/19** |
| **Tăng số user** | 🟠 **Cần xử lý trước** | Chặn cứng bởi `workers = None`. Sau khi sửa: 2 vCPU/5 worker ≈ 15-20 user đồng thời. Muốn hơn phải tăng vCPU + sửa N+1 (§6) |
| **Tích hợp API** | 🟡 **Trung bình** | ✅ Có sẵn XML-RPC/JSON-RPC chuẩn Odoo cho toàn bộ 59 model. ⚠️ **Chưa có REST API riêng**, chưa có versioning, chưa có rate limit. Các method service (`create_role`, `set_crud`, `set_dlm_waste`…) đã guard tốt nên **an toàn khi expose qua RPC** |
| **Bảo trì** | 🟢 **Tốt** | **373 test method / 34 file** — hiếm gặp ở dự án quy mô này. Comment giải thích *tại sao*. Migration có kỷ luật. ⚠️ Thiếu CI để chạy test tự động |

## Rào cản mở rộng lớn nhất

1. **Không có CI/CD** — 373 test tồn tại nhưng không có gì đảm bảo chúng được chạy trước khi deploy.
2. **Không có staging** — không có đường kiểm chứng migration trước khi chạm production.
3. **Chứng từ sinh bằng Python** (§A4) — mỗi lần đổi mẫu báo giá phải sửa code + deploy, không giao được cho BA.

---

# 10. PHÂN LOẠI RỦI RO

## 🔴 CRITICAL — Chặn deploy

### R1. Tài khoản Admin demo mật khẩu `123456` cài vào production
- **File:** `dlm-erp/dl_base/data/demo_users_data.xml` · `dlm-erp/dl_base/__manifest__.py`
- **Nguyên nhân:** file demo khai trong key `'data'` thay vì `'demo'`; **không module nào có key `'demo'`** ⇒ `without_demo = All` vô hiệu hoàn toàn
- **Ảnh hưởng:** chiếm toàn quyền hệ thống từ Internet. Mất/sửa/xoá toàn bộ dữ liệu doanh nghiệp
- **Sửa:** chuyển 2 file sang key `'demo'` (§5-S1). Nếu DB đã cài: `UPDATE res_users SET active=false WHERE login LIKE '%@gmail.com';` + đổi mật khẩu tài khoản thật
- **Ưu tiên:** **P0 — làm đầu tiên**

### R2. Secret plaintext trong `odoo.conf`
- **File:** `odoo.conf:10` (`db_password=123456`), `odoo.conf:49` (Gmail app password)
- **Giảm nhẹ:** ✅ file **đã gitignore và chưa từng bị commit** (đã kiểm chứng bằng `git ls-files`)
- **Ảnh hưởng:** app password đã lộ trong phiên làm việc ⇒ có thể dùng gửi mail mạo danh
- **Sửa:** thu hồi + tạo lại Gmail app password; đặt mật khẩu DB mạnh; `chmod 640` file conf; dùng Docker secrets
- **Ưu tiên:** **P0**

### R3. `workers = None` — không chịu được tải production
- **File:** `odoo.conf:68`; kèm `limit_time_*`, `limit_memory_*` đều `None`
- **Nguyên nhân:** cấu hình dev giữ nguyên
- **Ảnh hưởng:** ~1 core do GIL; 1 request lỗi ăn hết RAM, không có cơ chế tự phục hồi
- **Sửa:** `workers = 5` + đủ bộ `limit_*` (§7)
- **Ưu tiên:** **P0**

### R4. Không có tài sản triển khai nào
- **Phạm vi:** toàn repo — thiếu Dockerfile, compose, Nginx conf, requirements.txt, systemd, backup, tài liệu deploy
- **Ảnh hưởng:** deploy thủ công không lặp lại được; không rollback được; **không có backup ⇒ mất dữ liệu là vĩnh viễn**
- **Sửa:** tạo bộ artifact ở §7-§8
- **Ưu tiên:** **P0**

### R5. `addons_path` / `data_dir` là đường dẫn Windows
- **File:** `odoo.conf:2,5`
- **Ảnh hưởng:** Odoo **không khởi động được** trên Linux
- **Sửa:** đổi sang đường dẫn Linux (§7)
- **Ưu tiên:** **P0**

## 🟠 HIGH — Sửa trước hoặc ngay sau deploy

### R6. `list_db = True` — lộ Database Manager
- **File:** `odoo.conf:32` · **Sửa:** `list_db=False` + chặn ở Nginx · **Ưu tiên: P0**

### R7. `proxy_mode = False` sau Nginx
- **File:** `odoo.conf:43`
- **Ảnh hưởng:** Odoo đọc sai IP client (log/bảo mật sai); sinh URL `http://` trong email ⇒ redirect lỗi
- **Sửa:** `proxy_mode=True` + Nginx gửi `X-Forwarded-Proto` · **Ưu tiên: P0**

### R8. `dbfilter = ^dlm_dev$` — tên DB dev
- **File:** `odoo.conf:15` · **Sửa:** `^dlm_prod$` · **Ưu tiên: P1**

### R9. 94 Many2one không khai `ondelete`
- **File:** tập trung ở `dl_sale/models/dl_quotation.py` (8), `dl_sale/models/dl_sale_order.py` (7), `dl_purchase/models/dl_purchase_order.py` (5)
- **Ảnh hưởng:** mặc định `set null` ⇒ dữ liệu mồ côi hoặc vi phạm NOT NULL
- **Sửa:** khai tường minh trên **model thường trú** (wizard bỏ qua được) · **Ưu tiên: P1**

### R10. N+1 query trong compute
- **File:** `dl_config/models/pricing_matrix.py:103` · `dl_partner/models/res_partner.py:263` · `dl_technical/models/dl_bom.py:201,235`
- **Sửa:** gom batch / `read_group` / dùng `len()` (§6 có code sẵn) · **Ưu tiên: P1**

### R11. Không có backup
- **Ảnh hưởng:** mất filestore = mất toàn bộ **bản vẽ kỹ thuật** · **Sửa:** script §8 + **restore thử** · **Ưu tiên: P0**

## 🟡 MEDIUM

| # | Vấn đề | File | Sửa | Ưu tiên |
|---|---|---|---|---|
| R12 | Thiếu record rule trên ~50 model nghiệp vụ | (§B3) | Đối chiếu ma trận RBAC trong đặc tả; bổ sung rule nếu spec yêu cầu | P2 |
| R13 | Multi-company không nhất quán | (§B2) | Chốt single-company (bỏ `company_id`) **hoặc** bổ sung đủ rule | P2 |
| R14 | Nuốt exception im lặng | `dl_config/models/res_users.py:117`, `dl_purchase/models/stock_lot.py:67` | Thêm `_logger.warning(..., exc_info=True)` | P2 |
| R15 | Hàm tính giá quá dài | `quotation_pricing_service.py:53,387` | Tách theo thành phần chi phí | P2 |
| R16 | Không có `ir.actions.report` | (§A4) | Chuyển chứng từ layout tĩnh sang QWeb | P3 |
| R17 | `dl_purchase` phụ thuộc 6 module | `dl_purchase/__manifest__.py` | Tách module cầu nối | P3 |
| R18 | Không có CI | — | GitHub Actions chạy 373 test | P2 |

## 🟢 LOW

| # | Vấn đề | File | Sửa |
|---|---|---|---|
| R19 | Thiếu `@api.depends_context('uid')` | `dl_product/models/dl_product.py:195,242`; `dl_quotation_request.py:542,1358` | Thêm decorator (2 dòng) |
| R20 | File data mồ côi | `dl_technical/data/measurement_shape_data.xml` | Thêm vào manifest hoặc xoá |
| R21 | Không có file `.po` | toàn bộ module | Export nếu cần đa ngữ |
| R22 | `unaccent = False` | `odoo.conf:62` | Bật + `CREATE EXTENSION unaccent` |
| R23 | Thư mục rác `.tmp_*` trong repo | `.tmp_tds/`, `.tmp_erd/`, `.tmp_init.log` | Thêm vào `.gitignore` |

---

# 11. BÁO CÁO TỔNG KẾT

## Điểm số

| # | Hạng mục | Điểm | Căn cứ |
|---|---|---:|---|
| 1 | **Kiến trúc** | **7.0**/10 | Phân tầng rõ, không phụ thuộc vòng, mixin đúng chuẩn, RBAC tự mở rộng. Trừ điểm: `dl_purchase` phụ thuộc 6 module, `dl_inventory→dl_sale` ngược chiều, không có QWeb report |
| 2 | **Chất lượng code** | **8.0**/10 | 0 bare except, 0 print, 0 TODO, 0 hard-code ID, comment giải thích *tại sao*. Trừ: 15 hàm ≥80 dòng, 2 chỗ nuốt exception |
| 3 | **Database** | **7.0**/10 | 36 index đúng chỗ, 54 compute store đều có depends, partial unique index đúng cách. Trừ: 94 M2O thiếu `ondelete`, multi-company không nhất quán |
| 4 | **Bảo mật** | **4.0**/10 | Kiến trúc tốt (0 SQLi, 0 XSS, 0 eval, ACL 100%, sudo có guard, RBAC chặt). **Nhưng bị kéo xuống bởi R1** — admin/`123456` public là lỗ hổng chiếm quyền hoàn toàn |
| 5 | **Hiệu năng** | **6.0**/10 | Index & compute store hợp lý. Trừ: `workers=None`, 4 N+1 trong compute, `limit_*` để trống |
| 6 | **Khả năng bảo trì** | **8.0**/10 | 373 test, 25 migration, comment chất lượng cao, RBAC khai báo. Trừ: không có CI |
| 7 | **Sẵn sàng Production** | **2.5**/10 | **Không có bất kỳ artifact triển khai nào**; `odoo.conf` là file dev Windows nguyên vẹn; không backup |

### 🎯 Điểm tổng: **6.1 / 10**

> **Diễn giải:** đây là dự án có **chất lượng kỹ thuật nội tại tốt** (code, test, kiến trúc, tư duy bảo mật đều trên mức trung bình rõ rệt) nhưng **hoàn toàn chưa được chuẩn bị để rời khỏi máy dev**. Khoảng cách nằm ở **vận hành**, không nằm ở **code**.

---

## Phần A — PHẢI hoàn thành TRƯỚC khi lên Production

**Nhóm 1 — Bảo mật (P0, ~2 giờ)**
- [ ] **R1** Chuyển `demo_users_data.xml` + `demo_user_language_data.xml` sang key `'demo'`. Kiểm chứng: DB mới không còn user `@gmail.com`
- [ ] **R2** Thu hồi Gmail app password `qeppkjbpjwehxrad` → tạo mới. Đặt `db_password` mạnh
- [ ] **R6** `list_db = False` + chặn `/web/database/*` ở Nginx
- [ ] Đổi `admin_passwd` sang hash mới

**Nhóm 2 — Cấu hình (P0, ~1 giờ)**
- [ ] **R5** `addons_path` + `data_dir` sang đường dẫn Linux
- [ ] **R3** `workers = 5` + đủ bộ `limit_time_*` / `limit_memory_*`
- [ ] **R7** `proxy_mode = True`
- [ ] **R8** `dbfilter = ^dlm_prod$`, `db_name = dlm_prod`
- [ ] `logfile = /var/log/odoo/odoo.log`
- [ ] `unaccent = True` + `CREATE EXTENSION unaccent`

**Nhóm 3 — Hạ tầng (P0, ~1 ngày)**
- [ ] **R4** `Dockerfile` + `docker-compose.yml` + `requirements-dlm.txt`
- [ ] Nginx + Let's Encrypt + security header
- [ ] UFW (chỉ 22/80/443)
- [ ] **R11** Script backup DB + filestore, cron hằng ngày, off-site
- [ ] **Restore thử backup vào DB tạm** ← không bỏ qua bước này
- [ ] logrotate

**Nhóm 4 — Kiểm chứng (P0, ~0.5 ngày)**
- [ ] Chạy **373 test** trên môi trường sạch: `odoo -d test_dlm -i all --test-enable --stop-after-init`
- [ ] Cài mới từ DB trống trên Linux — xác nhận 9 module cài không lỗi
- [ ] Đăng nhập thử **cả 8 vai trò**, xác nhận ma trận phân quyền đúng đặc tả
- [ ] Xác nhận **không tài khoản demo nào tồn tại**

> **Ước tính: 2-3 ngày công** cho toàn bộ Phần A.

---

## Phần B — Nên làm SAU khi triển khai

**Tháng đầu**
- [ ] **R10** Sửa 4 N+1 (§6 đã có code sẵn) — ~1 giờ, lợi ích rõ rệt
- [ ] **R9** Khai `ondelete` cho M2O trên model thường trú
- [ ] **R14** Thay `except Exception: pass` bằng logging
- [ ] **R18** CI GitHub Actions chạy 373 test mỗi PR
- [ ] Dựng **staging** trùng cấu hình production
- [ ] **R12** Đối chiếu record rule với ma trận RBAC trong đặc tả

**Quý đầu**
- [ ] **R13** Chốt dứt điểm single/multi-company
- [ ] **R15** Tách `_price_manufactured()` / `create_from_rfq()`
- [ ] **R16** Chuyển chứng từ layout tĩnh sang QWeb (để BA tự sửa mẫu)
- [ ] **R17** Tách module cầu nối cho `dl_purchase`
- [ ] Bổ sung index: `dl.quotation.state`, `dl.sale.order.state`, `dl.bom.line.material_id`, `dl.drawing.product_id`
- [ ] Monitoring (Netdata) + cảnh báo

---

## Phần C — KẾT LUẬN

### ❌ **KHÔNG nên triển khai Production ngay.**

**Lý do quyết định — chỉ cần một mình R1 cũng đủ để chặn:**

Tài khoản `admin.it@gmail.com` / `123456` với nhóm `dl_group_admin` **sẽ được tạo tự động** trên mọi database mới, kể cả khi đã đặt `without_demo = All` — vì file được khai trong key `'data'` chứ không phải `'demo'`, và **không module nào trong dự án có key `'demo'`**.

Đưa lên tên miền public nghĩa là **giao toàn quyền hệ thống cho bất kỳ ai đoán được mật khẩu mặc định** — mà `123456` thì không cần đoán. Kẻ tấn công có thể đọc toàn bộ báo giá, giá vốn, danh sách khách hàng/nhà cung cấp, bản vẽ kỹ thuật, và tự cấp thêm quyền qua chính màn hình RBAC.

Cộng thêm: **không có backup** (mất là mất vĩnh viễn), `addons_path` Windows (**Odoo không khởi động nổi trên Linux**), và `workers=None` (sập khi vài người dùng cùng lúc).

### ✅ Nhưng tin tốt: khoảng cách là **vận hành**, không phải **code**

Cần nói rõ để đánh giá công bằng — phần lõi của dự án này **tốt hơn đa số dự án Odoo custom cùng quy mô**:

- **0** lỗi SQL injection, **0** XSS, **0** `eval()`, **0** bare except, **0** hard-code DB ID
- ACL phủ **100%** model; 222 `sudo()` nhưng có **61** guard quyền tường minh, pattern "kiểm tra trước, sudo sau" nhất quán
- Màn hình RBAC guard `_check_rbac_admin()` ở **dòng đầu mọi method ghi** — không có đường leo quyền qua RPC
- **373 test method** — hiếm thấy
- Comment giải thích *tại sao*, kể cả những quyết định "cố ý không làm" (vd `ir_rule.xml` giải thích vì sao không lọc theo `create_uid`)
- **0** compute `store=True` thiếu `@api.depends` — lỗi kinh điển mà dự án này không mắc

**Toàn bộ 5 hạng mục Critical đều là lỗi cấu hình/đóng gói, không phải lỗi logic nghiệp vụ.** Không có hạng mục nào đòi viết lại kiến trúc.

### 📅 Lộ trình

| Giai đoạn | Thời gian | Nội dung |
|---|---|---|
| **Phần A** | **2-3 ngày công** | 5 Critical + 3 High (checklist ở trên) |
| **Kiểm chứng** | **0.5 ngày** | Chạy test, cài sạch trên Linux, thử 8 vai trò, **restore thử backup** |
| **Go-live** | | Sau khi Phần A xong **và** kiểm chứng đạt |
| **Phần B** | 1-3 tháng | Tối ưu & củng cố |

> **Sau khi hoàn thành Phần A, điểm "Sẵn sàng Production" sẽ từ 2.5 lên khoảng 8.0/10, và hệ thống đủ điều kiện go-live.**

---

*Báo cáo dựa trên phân tích tĩnh source code tại commit hiện hành trên nhánh `develop`.
Chưa chạy test suite và chưa thử deploy thực tế — khuyến nghị thực hiện ở bước Kiểm chứng.*
