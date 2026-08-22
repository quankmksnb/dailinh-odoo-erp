# Smoke-test bản đã deploy — https://erp.dailinh.com (db: `dlm_prod`)

**Ngày:** 2026-08-17
**Phạm vi:** Đây là 1 lần smoke-test bản deploy thật, KHÔNG phải chạy lại audit Report 5.3 (báo cáo
đó là của `dlm_dev` cục bộ). Không có quyền SSH/shell/DB trực tiếp vào server này — mọi kiểm tra
đều qua HTTP/trình duyệt như người dùng thật, dùng Playwright trỏ `STAGING_BASE_URL=https://erp.dailinh.com`
(project `staging`/`setup-staging`/`http-staging` mới trong `playwright.config.ts`).

## Kết quả tổng: 32/32 Pass (chưa gồm phần khoá đăng nhập tạm thời — tạm dừng theo yêu cầu)

### Nhóm nghiệp vụ (E2E, tự tạo dữ liệu do `dlm_prod` gần như trống)

| Luồng | Kết quả |
|---|---|
| BF-01: Sales tạo khách hàng mới + tạo RFQ → Kỹ thuật nhận xử lý | ✅ Pass |
| BF-01 (A4): Kỹ thuật kết luận RFQ Không khả thi | ✅ Pass |
| BF-02: Kỹ thuật tạo BOM mới + thêm dòng vật tư | ✅ Pass |
| BF-03/05/09: RFQ hàng thương mại → Báo giá → Gửi khách → Đơn bán hàng | ✅ Pass — **DH/2026/0001, đơn bán hàng đầu tiên trên hệ thống** |
| BF-04: Báo giá vượt ngưỡng → Trưởng KD duyệt → gửi khách được | ✅ Pass — **phát hiện 1 defect thật (xem bên dưới)** |
| BF-08: Kế toán full CRUD Nhà cung cấp | ✅ Pass |
| BF-10: Thủ kho nhận hàng NCC → Kiểm & cất hàng | ✅ Pass — **DL/NH/00001, phiếu kho đầu tiên trên hệ thống** |

### Bảo mật (Security)

| Kiểm tra | Kết quả |
|---|---|
| Toàn site chạy HTTPS, không mixed-content | ✅ Pass — đóng được TC-SYSSEC-003 (gap duy nhất `dlm_dev` không đóng được vì máy dev không có HTTPS) |
| `res.users` không lộ field `password`/`password_crypt` qua RPC | ✅ Pass (TC-SYSSEC-002) |
| File PDF báo giá không tải được khi chưa đăng nhập (ẩn danh) | ✅ Pass (TC-SYSSEC-001) — `GET /web/content/<id>` trả 404, không lộ nội dung |
| Kỹ thuật không đọc được model Báo giá qua RPC trực tiếp (bỏ qua UI) | ✅ Pass (TC-E2E-SEC-001) — AccessError đúng như kỳ vọng |
| RBAC menu: Kỹ thuật/BA-Sales không thấy menu ngoài phạm vi vai trò | ✅ Pass (3 test) |
| Admin/IT không được duyệt báo giá vượt ngưỡng | ✅ Pass |
| Khoá đăng nhập tạm thời sau nhiều lần sai liên tiếp | ⏸️ **Tạm dừng theo yêu cầu người dùng** — code đã viết (`tests/http-staging/stg-account-lockout.spec.ts`), sửa xong lỗi logic (probe đúng mật khẩu xen giữa các lần sai làm tự xoá bộ đếm — đã bỏ), nhưng CHƯA chạy lại lần cuối để xác nhận. Rủi ro: cooldown tính theo IP, có thể ảnh hưởng người khác dùng chung mạng khi chạy trên môi trường public — cần hỏi lại trước khi chạy. |

### Hiệu năng (Performance) — đo THẬT qua mạng Internet, không phải localhost

Số liệu cũ trong Report 5.3 (`Pass*`) đo trên `dlm_dev` cục bộ (localhost, không có độ trễ mạng) —
đây là lần đầu tiên đo qua mạng thật trên bản đã deploy:

| NFR | Kịch bản | Mục tiêu (PRD §6.1) | Đo được (staging, 1 user) | Kết quả |
|---|---|---|---|---|
| NFR-P01 | Tải Danh sách báo giá | < 4 giây | **0.39s** | ✅ Pass |
| NFR-P01 | Tải BOM sản phẩm | < 4 giây | **0.37s** | ✅ Pass |
| NFR-P02 | Mở chi tiết báo giá (dữ liệu tính giá) | < 10 giây | **0.46s** | ✅ Pass |

### NFR-P03 — tải đồng thời 50-100 user, đo bằng k6 (không phải Playwright)

Playwright chỉ mô phỏng 1 trình duyệt/lần nên KHÔNG đo được tải đồng thời thật. Đã dựng riêng
`tests/load-staging/k6-concurrent-users.js` (k6 v0.54.0, portable, không cần quyền admin) — xoay
vòng 8 tài khoản nghiệp vụ thật, kịch bản ramping-VUs: 0→50 (30s) → giữ 50 (1m) → 50→100 (30s) →
giữ 100 (1m) → về 0 (30s), mỗi vòng lặp = đăng nhập → tải Danh sách báo giá → mở 1 báo giá ngẫu
nhiên (đọc dữ liệu tính giá), có nghỉ (think time) 1-3s giữa các bước như người dùng thật. Chạy
thật ngày 2026-08-17 lúc 19:19-19:23 nhắm `https://erp.dailinh.com`:

| Chỉ số | Kết quả thực đo (50→100 user đồng thời) | Mục tiêu PRD §6.1 | Kết quả |
|---|---|---|---|
| Đăng nhập (`/web/session/authenticate`) | p95 = **8.3s**, trung bình 4.2s, 1037/1050 thành công (98.8%) | (không có mục tiêu riêng, nhưng vượt xa số liệu 1-user 0.x s) | ⚠️ Suy giảm rõ rệt |
| NFR-P01: Tải Danh sách báo giá | p95 = **7.5s** (ngưỡng k6: FAIL), trung bình 3.2s, **chỉ 609/1034 (58.8%) request trả về đúng dữ liệu** | < 4 giây | ❌ **FAIL** |
| NFR-P02: Mở chi tiết báo giá | p95 = 7.7s (< mục tiêu 10s nhưng rất sát), trung bình 3.2s, 597/605 (98.7%) thành công | < 10 giây | ⚠️ Pass nhưng sát ngưỡng, suy giảm mạnh so với 1-user (0.46s) |
| Toàn bộ HTTP request | 2689 request, 12.6 req/s, lỗi vận chuyển (timeout thật ở tầng TCP, >60s) chỉ 18/2689 (0.7%) | — | Phần lớn là **chậm**, không phải **rớt kết nối** |

**Diễn giải quan trọng**: 425/1034 (41%) lần gọi "Danh sách báo giá" (`search_read` trên
`dl.quotation`) bị tính là fail — nhưng chỉ 18 request trong cả lần chạy bị timeout thật ở tầng
mạng (60s). Nghĩa là phần lớn các lần "fail" còn lại là request có trả lời (HTTP 200) nhưng
**nội dung trả về là lỗi RPC** thay vì dữ liệu — rất có khả năng do worker Odoo/kết nối DB bị quá
tải khi 100 user gọi đồng thời (số lượng worker HTTP của server có thể đang cấu hình thấp, gây
nghẽn hàng đợi). Đáng chú ý là request "Mở chi tiết 1 báo giá" (`read` theo 1 id cụ thể) có cùng
mức độ chậm (~3.2s trung bình) nhưng tỉ lệ lỗi RẤT thấp (98.7% pass) — khác biệt lớn so với
`search_read` danh sách (58.8% pass) cho thấy vấn đề có thể liên quan riêng tới cách xử lý
`search_read` (dữ liệu lớn hơn, hoặc tranh chấp khoá/kết nối DB) hơn là do worker cạn kiệt đơn
thuần. **Cần log server-side (Odoo log / Postgres log) để xác định nguyên nhân gốc chính xác** —
phạm vi test HTTP-only từ bên ngoài chỉ xác nhận được TRIỆU CHỨNG (suy giảm mạnh + tỉ lệ lỗi cao
ở 100 user đồng thời), không xác định được NGUYÊN NHÂN gốc (số worker, cấu hình DB pool, thiếu
index...).

**Kết luận NFR-P03**: hệ thống **KHÔNG đạt** mục tiêu ở tải 100 user đồng thời cho màn Danh sách
báo giá (p95 7.5s so với mục tiêu <4s, tỉ lệ lỗi 41%). Ở mức 50 user (nửa đầu bài đo) tình hình có
thể tốt hơn nhưng số liệu k6 hiện tại là tổng hợp toàn bộ 3.5 phút (gồm cả đoạn 100 user) nên chưa
tách riêng được ngưỡng 50 user — nếu cần số liệu tách riêng 50 user, chạy lại với
`MAX_VUS=50 k6 run tests/load-staging/k6-concurrent-users.js`. File script không chứa mật khẩu
(đọc qua biến môi trường `DLM_STAGING_PASSWORD`), an toàn để commit.

## Defect thật phát hiện được (không phải lỗi test)

1. **[BUG] Báo giá vượt ngưỡng phê duyệt KHÔNG bị chặn ngay sau khi tạo mới.** `dl_quotation.py`
   override `create()` không gọi `reevaluate_quotation()` — chỉ `write()` mới gọi (khi field trong
   `_REEVAL_TRIGGER_FIELDS` đổi). Nghĩa là 1 báo giá MỚI TẠO vượt ngưỡng (tạo cả header+dòng trong
   1 lần Lưu, đúng như thao tác UI thật) vẫn hiện nút "Gửi khách hàng" và `approval_state` =
   `not_required` **ngay sau khi tạo** — chỉ khi có 1 lần sửa tiếp theo (vd đổi Chiết khấu) mới
   kích hoạt đánh giá lại đúng. Xác nhận 2 cách: RPC trực tiếp (`write(discount_pct=<không đổi>)`
   lật `approval_required` False→True ngay lập tức) và tái hiện qua trình duyệt thật (banner chỉ
   xuất hiện SAU khi sửa+lưu lại, không phải ngay sau khi tạo). **Rủi ro thật**: Sales có thể tạo
   báo giá giá trị lớn rồi gửi khách ngay mà không qua cổng duyệt nào, nếu không có thao tác sửa
   nào xen giữa. File tái hiện: `tests/screens-staging/stg-bf04-approval-flow.spec.ts`.

2. **[Bug UX]** Màn "Tạo khách hàng" (Doanh nghiệp): field **Quốc gia** bắt buộc nhưng không có
   dấu hiệu nào trên UI. Bỏ trống thì nút "Lưu thủ công" im lặng không phản hồi (không toast lỗi,
   không class `.o_field_invalid`) — người dùng thật sẽ không hiểu vì sao Lưu "không hoạt động".
   File: `tests/screens-staging/stg-bf01-rfq-flow.spec.ts`.

3. **[Cần Dev xác nhận]** Màn "Nhà cung cấp / Thầu phụ" (Kế toán): khi danh sách rỗng, nút
   "+ Thêm NCC" không hiện trên toolbar — chỉ có placeholder "Tạo mới tài liệu" ở giữa trang,
   bấm vào KHÔNG mở form tạo mới. Đã xác nhận qua RPC: Kế toán **CÓ** quyền `create` thật (không
   phải AccessError, không phải BUG-L3-001 tái diễn) — thuần là vấn đề hiển thị nút Tạo khi list
   rỗng. File: `tests/screens-staging/stg-bf08-supplier-price.spec.ts`.

## Phát hiện đáng chú ý khác (không phải lỗi, là quan sát thật về môi trường)

1. **Database gần như trống lúc bắt đầu** — trước khi chạy: `res.partner` chỉ có 10 bản ghi (9 user
   nội bộ + "My Company"), `product.product` có 37 bản ghi demo, `dl.quotation.request` = 0,
   `partner_role=supplier` = 0. Chưa chạy `seed_qa_data.py` — mọi luồng phải tự tạo dữ liệu (đặt
   tên thật, không kiểu "QA Test", theo đúng yêu cầu). Sau phiên này, hệ thống đã có dữ liệu demo
   thực tế: khách hàng, NCC, RFQ, báo giá, đơn bán hàng, phiếu kho đầu tiên.
2. **`web.base.url` lưu là `http://erp.dailinh.com`** dù site chỉ phục vụ qua HTTPS thật — có thể
   khiến link tự sinh (email, PDF) trỏ sai giao thức. Đáng sửa trong System Parameters.
3. **`admin.it@gmail.com`/`admin@example.com` không có quyền `Administration/Settings`** của Odoo
   — đúng thiết kế RBAC (Admin/IT là vai trò nghiệp vụ, không phải superuser kỹ thuật).
4. **Mật khẩu `123456` dùng chung mọi tài khoản** — không phải lỗi code (đã xác nhận hash/salt qua
   RPC không lộ), nhưng là rủi ro vận hành trước khi có dữ liệu khách hàng thật.
5. **Tài liệu hướng dẫn (00_Guide + các sheet Template_*) trong Report 5.3 có nội dung MockMvc/
   Java-Spring generic** (route `/login`, `/orders/{id}`, actor Customer/Staff) không khớp dự án
   Odoo/Python này — đã sửa lại toàn bộ (§3a giờ mô tả đúng Playwright APIRequestContext gọi
   JSON-RPC `/web/session/authenticate`/`/web/dataset/call_kw`, ví dụ minh hoạ dùng route Odoo
   thật) trong cả 2 file `Report 5.3_SystemTests_L3_final.xlsx` và `_vn.xlsx`.

## Việc CHƯA làm trên môi trường này

- Chưa chạy lại toàn bộ 71 test case L3 gốc — vì seed data không khớp `dlm_dev`, mỗi luồng phải
  viết lại theo hướng tự tạo dữ liệu (đã làm cho 7 luồng chính, còn BF-06/BF-07 và các nhánh phụ
  chưa làm).
- **Khoá đăng nhập tạm thời** — tạm dừng theo yêu cầu, code đã sẵn sàng chạy lại khi được xác nhận.
- ~~Đo tải đồng thời 50-100 user~~ — **đã làm** bằng k6 (xem mục Hiệu năng ở trên,
  `tests/load-staging/k6-concurrent-users.js`) — phát hiện **NFR-P03 FAIL thật** ở màn Danh sách
  báo giá dưới tải 100 user đồng thời. Vẫn còn thiếu: log server-side để xác định nguyên nhân gốc
  (worker/DB pool/index), và số liệu tách riêng cho đúng mốc 50 user (hiện đang gộp chung với
  đoạn 100 user trong 1 lần chạy).

## File liên quan

- `tests/fixtures/roles.staging.ts` — tài khoản staging (mật khẩu qua `DLM_STAGING_PASSWORD`, gitignore).
- `tests/screens-staging/auth.staging.setup.ts` — đăng nhập 8 role, storageState riêng (`tests/.auth-staging/`).
- `tests/screens-staging/stg-rbac-spotcheck.spec.ts`, `stg-security-extra.spec.ts` — bảo mật.
- `tests/screens-staging/stg-performance.spec.ts` — hiệu năng đo qua mạng thật.
- `tests/screens-staging/stg-bf01-rfq-flow.spec.ts`, `stg-bf01-rfq-resolve.spec.ts`,
  `stg-bf02-bom-create.spec.ts`, `stg-bf03-09-quotation-pipeline.spec.ts`,
  `stg-bf04-approval-flow.spec.ts`, `stg-bf08-supplier-price.spec.ts`,
  `stg-bf10-warehouse-receive.spec.ts` — các luồng nghiệp vụ.
- `tests/http-staging/stg-account-lockout.spec.ts` — khoá đăng nhập (đã viết, CHƯA chạy lại lần cuối).
- `tests/load-staging/k6-concurrent-users.js` — đo tải đồng thời 50-100 user thật bằng k6 (NFR-P03). Chạy:
  `DLM_STAGING_PASSWORD=<mật khẩu> k6 run tests/load-staging/k6-concurrent-users.js` (biến `MAX_VUS` tuỳ chỉnh số user tối đa, mặc định 100).
- Chạy: `STAGING_BASE_URL=https://erp.dailinh.com DLM_STAGING_PASSWORD=<mật khẩu> npx playwright test --project=staging` (hoặc dùng `.env.staging`, đã gitignore). Riêng `http-staging`: `--project=http-staging`.
