# Danh sách lỗi/defect còn tồn đọng — System Test (L3)

**Ngày tổng hợp:** 2026-08-17
**Nguồn:** tổng hợp từ audit Report 5.3 (`dlm_dev`, 71 test case) + smoke-test bản deploy thật
(`https://erp.dailinh.com`, xem `tests/reports/staging-smoke-2026-08-17.md`) + đo tải k6 mới nhất.
Đây là **danh sách lỗi**, khác với "Việc CHƯA làm" (những phần chưa test được) — 2 việc này liệt
kê tách riêng ở cuối file.

---

## A. Defect SẢN PHẨM thật (bug code, không phải lỗi test)

### 1. [Nghiêm trọng] Báo giá vượt ngưỡng phê duyệt KHÔNG bị chặn ngay sau khi tạo mới
- **Trạng thái:** Xác nhận thật, chưa fix.
- **Vị trí code:** `dlm-erp/dl_sale/models/dl_quotation.py` — override `create()` không gọi
  `reevaluate_quotation()`; chỉ `write()` mới gọi hàm này, và chỉ khi field nằm trong
  `_REEVAL_TRIGGER_FIELDS = {'discount_pct', 'line_ids', 'partner_id'}`.
- **Mô tả:** Khi Sales tạo 1 báo giá MỚI (header + dòng cùng lúc, đúng thao tác UI thật — 1 lần
  Lưu) có giá trị vượt ngưỡng duyệt (vd > 20,000,001đ cần Trưởng KD duyệt), ngay sau khi Lưu:
  `approval_state` = `not_required` và nút "Gửi khách hàng" **hiện sẵn, bấm gửi được luôn** —
  không có banner "Báo giá cần phê duyệt", không có cổng chặn nào. Chỉ khi có 1 lần SỬA tiếp theo
  (vd đổi Chiết khấu, dù đổi về đúng giá trị đang có) mới kích hoạt đánh giá lại đúng.
- **Rủi ro thật:** Sales có thể tạo 1 báo giá giá trị rất lớn rồi gửi thẳng cho khách ngay lập
  tức mà không qua bất kỳ ai duyệt — **bỏ qua hoàn toàn cơ chế kiểm soát giá trị đơn hàng lớn**.
- **Cách tái hiện:** 2 cách độc lập đều xác nhận — (a) RPC trực tiếp: `write(id, {discount_pct:
  <giá trị không đổi>})` làm `approval_required` lật False→True ngay lập tức dù giá trị dòng
  không hề thay đổi thật; (b) trình duyệt thật: banner chỉ xuất hiện SAU khi sửa+lưu lại, không
  phải ngay sau khi tạo.
- **Test tái hiện:** `dailinh-odoo-erp/tests/screens-staging/stg-bf04-approval-flow.spec.ts`.
- **Đề xuất fix:** gọi `reevaluate_quotation()` (hoặc phần logic tương đương) trong `create()`
  luôn, không chỉ trong `write()`.

### 2. [Vừa] Field "Quốc gia" bắt buộc trên màn Tạo khách hàng nhưng không có dấu hiệu UI nào
- **Trạng thái:** Xác nhận thật, chưa fix.
- **Vị trí:** màn "Khách hàng" → "Tạo Khách hàng" (loại Doanh nghiệp), field `country_id`.
- **Mô tả:** `country_id` là required nhưng không hiện viền đỏ, không có class
  `.o_field_invalid`, không có toast lỗi. Bỏ trống rồi bấm "Lưu" thì nút Lưu **im lặng không phản
  hồi gì** — không có request `web_save` nào được gửi đi (xác nhận qua network listener). Người
  dùng thật sẽ không hiểu vì sao "Lưu không hoạt động".
- **Test tái hiện:** `tests/screens-staging/stg-bf01-rfq-flow.spec.ts` (đã phải tự thêm bước điền
  Quốc gia để vượt qua bug này khi viết test).
- **Đề xuất fix:** hiện chỉ báo required chuẩn OWL (`.o_required_modifier` cần có style/toast rõ
  ràng) cho field này, hoặc bỏ required nếu không thật sự cần thiết.

### 3. [Cần Dev xác nhận] Nút "+ Thêm NCC" không hiện khi danh sách Nhà cung cấp rỗng
- **Trạng thái:** Xác nhận là lỗi hiển thị, KHÔNG phải lỗi phân quyền.
- **Vị trí:** màn "Nhà cung cấp / Thầu phụ" (vai trò Kế toán).
- **Mô tả:** Khi danh sách trống, toolbar không hiện nút "+ Thêm NCC" — chỉ có placeholder giữa
  trang "Tạo mới tài liệu", bấm vào KHÔNG mở form tạo mới (không có phản hồi). Đã xác nhận qua
  RPC trực tiếp: Kế toán **CÓ** quyền `create` thật trên model (không phải AccessError, không
  phải BUG-L3-001 tái diễn) — vấn đề thuần là control tạo-mới không render đúng khi list rỗng.
  Phải tạo bản ghi qua RPC thay vì qua UI để tiếp tục test BF-08.
- **Test tái hiện:** `tests/screens-staging/stg-bf08-supplier-price.spec.ts`.
- **Đề xuất:** kiểm tra view definition của action "Nhà cung cấp / Thầu phụ" — có thể thiếu
  `<button type="object" class="oe_highlight">` chuẩn hoặc control "Create" bị ẩn nhầm theo
  domain/context.

### 4. [Nghiêm trọng, MỚI PHÁT HIỆN] Hệ thống KHÔNG chịu được tải 100 user đồng thời — màn Danh sách báo giá
- **Trạng thái:** Xác nhận thật bằng công cụ đo tải k6 (2026-08-17), là gap NFR-P03 mà audit
  Report 5.3 trước đây chưa từng đo được (dữ liệu cũ chỉ đo 1 user trên localhost).
- **Mô tả:** Khi mô phỏng 50→100 user đăng nhập + thao tác đồng thời qua mạng thật (script
  `tests/load-staging/k6-concurrent-users.js`), màn "Danh sách báo giá"
  (`search_read` trên `dl.quotation`) có tỉ lệ **41% request trả về lỗi/không đúng dữ liệu**, p95
  = 7.5s (mục tiêu PRD §6.1 là < 4s). Đăng nhập cũng suy giảm mạnh (p95 8.3s, so với ~0.5s ở tải
  thấp). Chỉ 18/2689 request là timeout thật ở tầng mạng — phần lớn "lỗi" là request có phản hồi
  (HTTP 200) nhưng nội dung là lỗi RPC, gợi ý nghẽn ở tầng worker Odoo hoặc connection pool
  Postgres khi tải cao, KHÔNG phải do mạng hay do k6.
- **Điểm đáng chú ý:** request "Mở chi tiết 1 báo giá" (`read` theo id đơn lẻ) có cùng mức độ
  chậm (~3.2s) nhưng tỉ lệ lỗi rất thấp (98.7%) — khác biệt lớn so với `search_read` danh sách
  (58.8%), gợi ý vấn đề có thể riêng ở cách xử lý truy vấn danh sách/domain rỗng hơn là do cạn
  kiệt worker đơn thuần.
- **Hạn chế của phép đo này:** chỉ đo được TRIỆU CHỨNG từ bên ngoài qua HTTP — chưa có quyền xem
  log Odoo/Postgres server-side nên chưa xác định được NGUYÊN NHÂN gốc chính xác (số worker HTTP
  cấu hình, kích thước connection pool, thiếu index, v.v.).
- **File:** `tests/load-staging/k6-concurrent-users.js`, kết quả chi tiết trong
  `tests/reports/staging-smoke-2026-08-17.md` mục "NFR-P03".
- **Đề xuất:** người có quyền truy cập server (deploy owner) cần xem log Odoo lúc tải cao để xác
  định nguyên nhân — khả năng cao cần tăng số worker HTTP (`--workers`) hoặc kiểm tra
  `db_maxconn`/pool size, hoặc thêm index cho các field hay lọc/sắp xếp trên `dl.quotation`.

### 5. [Major] Không có giới hạn dung lượng file đính kèm ở tầng server (NFR-P05)
- **Trạng thái:** Xác nhận thật (BUG-L3-004, đã ghi trong Report 5.3/Defect Register).
- **Mô tả:** grep toàn repo `dlm-erp` xác nhận KHÔNG có bất kỳ cơ chế chặn kích thước file nào ở
  tầng server (PRD yêu cầu giới hạn 15MB cho file đính kèm). Test upload thật 16MB qua
  `ir.attachment.create` (base64) **thành công**, không bị chặn.
- **Test tái hiện:** `tests/http/http-flows-attachment-size.spec.ts` (chạy trên `dlm_dev`; chưa
  chạy lại trên staging nhưng bug nằm ở code chung, không phụ thuộc môi trường).
- **Đề xuất fix:** thêm validation kích thước ở `ir.attachment.create` override hoặc ở tầng
  controller upload, theo đúng giới hạn PRD.

---

## B. Defect kế thừa từ audit `dlm_dev` trước đó (chưa xác nhận lại trên staging)

### 6. [BUG-L3-001] Kế toán mất quyền CRUD trên 1 số màn (regression)
- **Trạng thái:** Đã ghi nhận trong Report 5.3 từ trước, phát hiện lại khi rerun full-suite trên
  `dlm_dev` ngày 2026-08-16 (~19 spec fail, phần lớn liên quan bug này). **Chưa điều tra/fix**
  trong phiên này (ngoài phạm vi lúc đó: "bổ sung test còn thiếu", không phải "sửa lại 70 test
  cũ").
- **Lưu ý quan trọng:** đã xác nhận riêng trên staging (BF-08) rằng vấn đề "+ Thêm NCC" (mục A.3)
  **KHÔNG PHẢI** cùng nguyên nhân với BUG-L3-001 — Kế toán vẫn CÓ quyền `create` thật trên
  staging, khác với mô tả gốc của BUG-L3-001 (mất quyền CRUD thật). Cần làm rõ liệu BUG-L3-001 đã
  được fix một phần hay đây là 2 lỗi khác nhau trùng triệu chứng.
- **Đề xuất:** cần 1 phiên triage riêng, chạy lại toàn bộ ~19 spec fail trên `dlm_dev` để xác
  định spec nào còn thật sự do BUG-L3-001, spec nào là false-positive/lỗi test cũ đã lỗi thời.

### 7. Các spec fail khác chưa điều tra (rerun full-suite 2026-08-16)
- **Trạng thái:** Not Investigated — phát hiện khi chạy `--project=chromium --project=http`,
  quan sát fail rải rác ở `scr-07-12-ketoan`, `scr-27-send-quotation`, `scr-28-sales-order`,
  `scr-36-39/40-46` (các màn kho). Chưa rõ đây là regression thật hay do dữ liệu demo/thứ tự chạy
  test đã đổi khác so với lúc các spec đó được viết.
- **Đề xuất:** phiên triage riêng, chạy lẻ từng spec (không phụ thuộc thứ tự) để phân loại rõ.

---

## C. Test còn "Not Run" / "Blocked" (không phải bug, nhưng vẫn là gap còn tồn đọng)

### 8. TC-SYSSEC-004 — Khoá đăng nhập tạm thời sau nhiều lần sai (staging)
- **Trạng thái:** Code đã viết và đã sửa xong 1 lỗi logic thật (thiết kế cũ probe mật khẩu đúng
  xen giữa các lần sai làm tự reset bộ đếm lỗi của Odoo — `_assert_can_auth()` pop bộ đếm khi
  đăng nhập thành công — đã sửa thành N lần sai liên tiếp không probe giữa chừng). **CHƯA chạy
  lại để xác nhận** vì người dùng yêu cầu tạm dừng ("khoan đừng chạy khóa đăng nhập nữa") — lệnh
  tạm dừng này vẫn đang có hiệu lực, chưa được gỡ.
- **File:** `tests/http-staging/stg-account-lockout.spec.ts`.
- **Ghi chú:** trên `dlm_dev`, cơ chế tương đương (`TC-SYSSEC-004` gốc) đã Pass — đây chỉ là bản
  xác nhận lại trên môi trường staging, không phải nghi ngờ tính năng không hoạt động.

### 9. TC-SYSSEC-003 — HTTPS toàn site
- **Trạng thái:** ĐÃ ĐÓNG trên staging (Pass) — không còn là gap. Ghi lại ở đây chỉ để đối chiếu:
  đây từng là gap duy nhất "Not Run" trên `dlm_dev` (máy dev không có HTTPS), staging là môi
  trường duy nhất kiểm chứng được, và đã Pass.

### 10. NFR-P03 (50-100 user đồng thời)
- **Trạng thái:** ĐÃ ĐO ĐƯỢC (không còn "chưa test được") nhưng kết quả là **FAIL thật** — xem
  mục A.4 ở trên. Chuyển từ "gap về công cụ đo" sang "defect thật cần fix".

### 11. BF-06/BF-07 và các nhánh phụ trên staging
- **Trạng thái:** Not Run trên staging — mới làm 7/9+ luồng chính (BF-01×2, BF-02, BF-03/05/09,
  BF-04, BF-08, BF-10). BF-06 (ma trận CEO) và BF-07 (dashboard điều hành) chưa có bản
  staging-only tương ứng (BF-07 vốn đã Blocked trên `dlm_dev` — màn dashboard chưa tồn tại trong
  code, không phải thiếu test).

---

## Tổng kết ưu tiên xử lý (đề xuất)

| # | Defect | Mức độ | Trạng thái |
|---|---|---|---|
| 1 | Approval bypass khi tạo báo giá mới vượt ngưỡng | **Nghiêm trọng** | Chưa fix |
| 4 | Không chịu tải 100 user đồng thời (màn Danh sách báo giá) | **Nghiêm trọng** | Chưa fix, cần log server để tìm nguyên nhân gốc |
| 5 | Không giới hạn dung lượng file đính kèm (NFR-P05) | Major | Chưa fix |
| 6 | Kế toán mất quyền CRUD 1 số màn (BUG-L3-001) | Major | Chưa điều tra lại |
| 2 | Field Quốc gia required không có UI feedback | Vừa (UX) | Chưa fix |
| 3 | Nút "+ Thêm NCC" không hiện khi list rỗng | Vừa (UI) | Chưa fix, đã loại trừ nguyên nhân phân quyền |
| 7 | ~19 spec fail rải rác chưa điều tra | Chưa rõ mức độ | Cần triage riêng |
| 8 | Khoá đăng nhập tạm thời (staging) chưa xác nhận lại | Thấp (đã Pass ở dlm_dev) | Tạm dừng theo yêu cầu người dùng |
| 11 | BF-06/BF-07 chưa có bản staging | Thấp | Chưa làm |
