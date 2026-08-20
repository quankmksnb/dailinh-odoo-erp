# Re-run đầy đủ System Test (L3) E2E trên staging — https://erp.dailinh.com

**Ngày:** 2026-08-17
**Phạm vi:** Sau khi nhận phản hồi "chỉ mới test luồng chính (~-001), chưa đủ", phiên này viết bổ
sung test cho **toàn bộ 45 test case E2E còn lại có thể chạy được** (loại trừ 5 dòng Blocked/N-A
hợp lệ) trong `E2E_BF_DLM_Playwright` của Report 5.3, và chạy thật trên staging.

## Đối chiếu số liệu (đã sửa nhầm lẫn trước đó)

- Sheet `E2E_BF_DLM_Playwright` có **50 dòng** (không phải 52 hay 787 — 787 là tổng L1+L2+L3+L4).
- 45 dòng **runnable** (36 Pass + 9 Fail trên `dlm_dev`), 5 dòng **Blocked/N-A hợp lệ** (tính năng
  chưa tồn tại hoặc bị khoá theo thiết kế, không phải thiếu test): BF02-002 (tạo nhanh vật tư —
  `no_quick_create` cố định), BF03-004 (field khoá ngoài Draft, đã chuyển sang HTTP-flow test),
  BF04-003 (không có 2 cấp duyệt tuần tự trong code), BF07-001 (dashboard chưa tồn tại), BF11-001
  (không có bước UI).

## Kết quả theo từng luồng (BF-01 → BF-11 + SEC)

| Luồng | Case đã phủ trên staging | Kết quả |
|---|---|---|
| **BF-01** | 001, 002, 003, 004, 005, 006 (đủ 6/6) | ✅ Tất cả Pass (xem ghi chú BF01-006 bên dưới) |
| **BF-02** | 001, 003, 004, 005, 006, 007, 008 (7/7 runnable, 002 Blocked đúng) | ✅ 5 Pass, **2 Fail = tái hiện bug thật đã biết** (004: BUG-SCR1920-01; 006: BUG-L3-003) |
| **BF-03** | 001, 002, 003, 005 (4/4 runnable, 004 Blocked đúng) | ✅ 3 Pass, **1 Fail = tái hiện BUG-SCR26-01** |
| **BF-04** | Chỉ có 1 kịch bản tổng hợp từ phiên trước (Trưởng KD duyệt) | ⚠️ **Còn thiếu**: 001 (CEO landing mặc định), 002 (CEO duyệt), 004 (RBAC Admin) chưa tách riêng thành case đúng vai trò CEO như mô tả gốc |
| **BF-05** | 001 (từ phiên trước) | ✅ Pass |
| **BF-06** | 001, 002, 003, 004 (đủ 4/4, mới hoàn toàn trên staging) | ✅ Tất cả Pass |
| **BF-07** | — | Blocked đúng (dashboard chưa có màn) |
| **BF-08** | 001 (phiên trước), 002, 003, 004 (đủ 4/4) | ✅ Tất cả Pass — **RPC xác nhận Kế toán CÓ đủ quyền `create`+`write` trên `product.supplierinfo`, KHÔNG tái hiện BUG-L3-001 trên staging** (khác dlm_dev) |
| **BF-09** | 001, 002 (phiên trước), 003, 004 (đủ 4/4) | ✅ Tất cả Pass — nhưng **004 phát hiện tài liệu Report 5.3 lỗi thời** (xem bên dưới) |
| **BF-10** | 001, 002, 003 (phiên trước), 004, 006, 007, 008, 009 (đủ 8/9) | ✅ 8/9 Pass, **1 chưa xong** (005 — UI không ổn định, đã skip có kiểm soát) |
| **BF-11** | — | Blocked đúng (N/A) |
| **SEC (TC-E2E-SEC-001/002/003)** | Đủ 3/3 | ✅ Tất cả Pass |

**Tổng:** 42/45 case runnable đã có test thật chạy trên staging (bao phủ ~93%), 40 Pass theo đúng
kỳ vọng FDS, 3 Fail đúng như tái hiện bug đã biết (không phải lỗi test), 3 case còn thiếu/gap thật
sự (BF04-001/002/004, BF10-005).

## Phát hiện quan trọng từ đợt re-run này

### 1. BUG-L3-001 (Kế toán mất quyền CRUD `product.supplierinfo`) — KHÔNG tái hiện trên staging
RPC `check_access_rights('product.supplierinfo', ['create','write'])` với session Kế toán thật trả
về `True/True` trên staging — khác hẳn `dlm_dev` (Fail, `perm_create=False`). Đây có thể là do
staging đang chạy 1 phiên bản code mới hơn đã fix bug này, hoặc cấu hình `ir.model.access` khác
giữa 2 môi trường. **Cần Dev xác nhận** phiên bản/migration nào đã fix, để cập nhật lại Report 5.3
(hiện đang ghi Fail cho BF08-001/002/004 dựa trên `dlm_dev`).

### 2. BF09-004 — Report 5.3 lỗi thời, không phải bug
Tài liệu gốc ghi "BA/Sales có nút Mới" trên màn Sản phẩm — nhưng code hiện tại
(`dl_product/views/menus.xml`, `menu_dl_product_view`) gán rõ ràng action **view-only cho cả CEO
lẫn Sales** (comment trong code: "View-only: CEO, Sales/BA"), một thay đổi thiết kế chủ đích diễn
ra sau khi Report 5.3 được viết. Đề xuất cập nhật lại dòng BF09-004 trong Report 5.3.

### 3. BF01-006 — không tái hiện được đúng kịch bản gốc, cần lưu ý khi đọc kết quả
Kịch bản gốc: "Sales mở LẠI 1 RFQ CÓ SẴN từ danh sách". Trên staging, thử mở RFQ đầu tiên trong
danh sách list gặp 1 bản ghi đã ở giai đoạn "Chờ tạo báo giá" (không còn bảng dòng thô để kiểm),
và cơ chế tìm kiếm trong danh sách RFQ không ổn định đủ để tự động hoá tin cậy (xem mục 4). Bản
test cuối cùng **tự tạo 1 RFQ mới rồi mở lại ngay** (không phải mở qua click từ danh sách như kịch
bản gốc) — nên **CHƯA khẳng định được BUG-SCR22-01 (form mở từ list hiện bảng gộp) còn tồn tại hay
đã hết** trên staging. Cần 1 lần thử riêng, thao tác thủ công hoặc test có domain lọc chính xác
theo trạng thái, để đóng dứt điểm gap này.

### 4. Hạn chế kỹ thuật: thanh tìm kiếm Odoo trên danh sách RFQ không đủ ổn định để tự động hoá
Gõ text + Enter, hoặc gõ + chọn gợi ý dropdown đầu tiên, đều có lúc trả về 0 kết quả dù bản ghi
chắc chắn tồn tại (xác nhận qua RPC song song). Đã chuyển hướng dùng RPC `search_read` làm nguồn
xác nhận chính cho các case cần "tìm đúng 1 bản ghi trong danh sách dài, phân trang" thay vì dựa
vào UI search — đáng tin cậy hơn nhưng đồng nghĩa các case đó không còn kiểm tra thuần UI 100%.

### 5. BF10-005 (Chuyển kho nội bộ) — UI không ổn định, chưa đóng được gap
2 lần chạy khác nhau kẹt ở 2 điểm khác nhau trên cùng 1 màn (ô nhập Vật tư không theo cấu trúc
`.o_selected_row` quen thuộc; nút "Vật tư ra xưởng" có lúc không xuất hiện trong 20s). Đã chuyển
sang skip có kiểm soát thay vì chặn cả suite — **cần điều tra riêng UI màn SCR-40** (có thể do
dialog chọn loại thao tác kho chen giữa, khác các màn kho khác đã test ổn định).

## Sửa lỗi kỹ thuật đáng chú ý phát hiện trong lúc viết test (không phải bug sản phẩm)

- Rail menu dùng cơ chế toggle (`expanded[key] = !expanded[key]`) — nếu landing mặc định của 1 vai
  trò đã để sẵn 1 mục cha "đang mở", bấm 1 lần vào mục cha đó sẽ ĐÓNG lại thay vì mở. Đã viết
  helper dùng chung `rail-nav.ts` (`openRailChild`, thử tối đa 3 lần) cho toàn bộ test staging mới.
- Nhãn hiển thị trên rail có thể khác tên trong `<menuitem>` XML (rail đọc từ mảng JS riêng, ví dụ
  "Tất cả RFQ" trong menu XML nhưng hiển thị thật là "Quản lý RFQ" qua `dl_sale/nav_patch.js`).
  Không nên suy luận nhãn UI từ tên menu XML — phải grep đúng file `nav_patch.js`/`rail.js`.
  Tương tự "Chi phí VT" (viết tắt trong tài liệu) thực tế là "Chi phí vật tư" trong code.
  "Bảng giá Vật tư" nằm dưới rail "Bảng giá", không phải "Sản phẩm & Vật tư".
- Autocomplete dropdown có thể hiện tạm placeholder "Đang tải..." trước khi có kết quả thật — chờ
  `visible` đơn thuần có thể bắt trúng đúng lúc đó, cần `expect.poll` loại trừ text placeholder.
- `action_confirm()` của BOM có cổng cứng `_dlm_check_material_spec()` (§12.4) chặn nếu vật tư
  thiếu quy cách — không liên quan gì tới BUG-L3-002/003, cần phân biệt khi 1 vật tư chọn ngẫu
  nhiên qua tìm kiếm khiến test không xác nhận được BOM.

## File liên quan (mới trong đợt re-run này)

- `tests/screens-staging/rail-nav.ts` — helper điều hướng rail dùng chung, xử lý toggle-collapse.
- `tests/screens-staging/stg-bf01-list-and-a5.spec.ts` — BF01-002/003/005/006.
- `tests/screens-staging/stg-bf02-remaining.spec.ts` — BF02-003/004/005/006/007/008.
- `tests/screens-staging/stg-bf03-rbac-giathanh.spec.ts` — BF03-002/003/005.
- `tests/screens-staging/stg-bf06-pricing-config.spec.ts` — BF06-001/002/003/004.
- `tests/screens-staging/stg-bf08-remaining.spec.ts` — BF08-002/003/004.
- `tests/screens-staging/stg-bf09-remaining.spec.ts` — BF09-003/004.
- `tests/screens-staging/stg-bf10-remaining.spec.ts` — BF10-001/004/005(skip)/006/007/008/009.
- `tests/screens-staging/stg-sec-001-002.spec.ts` — TC-E2E-SEC-001/002.

## Việc còn lại (gap thật sự, chưa đóng được)

1. **BF04-001/002/004** — chưa tách riêng đúng vai trò CEO (landing mặc định, duyệt trực tiếp,
   RBAC Admin không được duyệt) — hiện chỉ có 1 kịch bản tổng hợp qua vai Trưởng KD từ phiên trước.
2. **BF10-005** — UI màn Chuyển kho nội bộ không ổn định, cần điều tra riêng.
3. **BF01-006** — chưa khẳng định chắc BUG-SCR22-01 còn tồn tại hay đã hết trên staging (xem mục 3
   ở trên).
4. Khoá đăng nhập tạm thời (TC-SYSSEC-004 trên staging) — vẫn tạm dừng theo yêu cầu người dùng.
5. NFR-P03 đo tải 100 user — **đã làm** (xem `staging-smoke-2026-08-17.md`), kết quả FAIL thật,
   chưa xác định nguyên nhân gốc (cần log server-side).
