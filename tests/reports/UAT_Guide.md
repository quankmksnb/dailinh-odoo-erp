# Hướng dẫn Demo/UAT — DLM-ERP

Tài liệu này tổng hợp các luồng chính đã được test bằng Playwright, viết lại thành hướng dẫn thao tác tay để bạn tự chạy UAT. Mỗi bước ghi rõ: đăng nhập bằng tài khoản nào, bấm vào đâu, kỳ vọng thấy gì.

Môi trường: `http://127.0.0.1:8069`, database `dlm_dev`.

## Tài khoản test (đều dùng mật khẩu `Demo@2026`)

| Tài khoản | Vai trò |
|---|---|
| `admin@dlm.demo` | Admin/IT |
| `ceo@dlm.demo` | CEO |
| `truongkd@dlm.demo` | Trưởng phòng Kinh doanh |
| `sales1@dlm.demo` | BA/Sales #1 |
| `sales2@dlm.demo` | BA/Sales #2 |
| `kythuat@dlm.demo` | Kỹ thuật |
| `ketoan@dlm.demo` | Kế toán nội bộ |

---

## LUỒNG 1 — Từ RFQ tới Đơn bán hàng (luồng nghiệp vụ chính, xuyên 3 vai trò)

### 1.1. BA/Sales tạo RFQ

1. Đăng nhập `sales1@dlm.demo` — landing thẳng vào màn **Báo giá**.
2. Vào menu **Báo giá** (thanh trên) → **Tạo RFQ**.
3. Chọn **Khách hàng** (bấm ô "Khách hàng" → chọn 1 khách có sẵn, VD "Cong ty CP Dau tu Kim Long").
4. Ở bảng **"Sản phẩm thương mại"** (bảng sửa trực tiếp trên dòng): bấm "Thêm một dòng" → chọn Sản phẩm (chỉ hiện SP thương mại đã duyệt) → nhập Số lượng. Cột giá/thành tiền tự tính.
5. Ở bảng **"Sản phẩm gia công"**: bấm "Thêm một dòng" → mở dialog → nhập **Tên sản phẩm** (bắt buộc), Số lượng, có thể đính kèm Mô tả/Ảnh (không bắt buộc) → "Lưu & Đóng".
   - ⚠️ **Lưu ý đã biết:** dialog này hiện đang **chặn nhầm** Mô tả/Ảnh là bắt buộc trong khi Số lượng = 0 lại **không bị chặn** — đây là bug đã ghi nhận, cứ điền đủ Tên SP + Mô tả + SL > 0 để tránh vướng.
6. Bấm **Lưu** toàn bộ RFQ. Trạng thái tự động = **"Mới"**.
7. **Không cần làm gì thêm** — RFQ giờ chờ Kỹ thuật xử lý.

**Xem lại RFQ vừa tạo:** menu **Báo giá › Yêu cầu báo giá › Tất cả RFQ**.

### 1.2. Kỹ thuật xử lý RFQ

1. Đăng nhập `kythuat@dlm.demo` — landing vào màn RFQ cần xử lý.
2. Vào **Báo giá › Yêu cầu báo giá › RFQ cần xử lý**, mở đúng RFQ vừa tạo ở bước 1.1 (trạng thái "Mới").
3. Bấm nút **"Nhận RFQ"** (trên header form) → trạng thái chuyển **"Đang xử lý"**.
4. Ở tab **"Dòng sản phẩm"**, với mỗi dòng **gia công** (dòng thương mại không cần xử lý gì — Sales đã chọn SP sẵn): bấm icon bánh răng **"Xử lý RFQ"** trên dòng đó → mở wizard:
   - Nếu SP đã từng gia công trước đây → chọn **BOM có sẵn** hoặc tạo phiên bản mới.
   - Nếu SP hoàn toàn mới → bấm **"Tạo Product"** → hệ thống tạo SP nháp → tiếp tục chọn/tạo BOM cho SP đó.
   - Hoặc nếu không làm được → tick **"Không khả thi"** + nhập **Lý do** (bắt buộc khi tick).
   - Bấm **"Xác nhận BOM"** để hoàn tất dòng.
5. Lặp lại cho tất cả các dòng gia công. Khi **tất cả dòng đã xử lý xong**, RFQ tự chuyển **"Đã xử lý xong"**.

**Trường hợp thiếu thông tin** (VD Sales mô tả chưa rõ): bấm **"Gửi lại Sales (bổ sung)"** → nhập lý do → RFQ chuyển "**Trả lại bổ sung**", tạo nhắc việc cho Sales.

### 1.3. Sales tạo Báo giá từ RFQ

1. Đăng nhập lại `sales1@dlm.demo`.
2. Vào **Báo giá › Yêu cầu báo giá › Tất cả RFQ**, mở RFQ đã "Đã xử lý xong".
3. Bấm **"Đánh dấu đã tạo báo giá"** (nếu có) hoặc từ danh sách Báo giá bấm **"+ Thêm"** để tạo báo giá mới, gắn với RFQ nguồn.
4. Ở màn **Chi tiết báo giá**: kiểm tra bảng dòng (đã copy từ RFQ), chỉnh Chiết khấu (%)/VAT (%) nếu cần.
   - ⚠️ **Lưu ý đã biết:** nút "+ Thêm dòng" ở bảng "Chi tiết báo giá" hiện **không bấm được** (bug Critical, lỗi CSS) — nếu cần thêm dòng mới ngoài dòng đã copy từ RFQ, thao tác này sẽ không hoạt động, báo lại cho Dev.
5. Bấm **Lưu**. Hệ thống tự tính giá + tự kiểm tra ngưỡng phê duyệt:
   - Nếu **không vượt ngưỡng** → banner xanh "Báo giá đã sẵn sàng gửi khách" → bấm **"Gửi khách hàng"** luôn.
   - Nếu **vượt ngưỡng** (chiết khấu quá trần hoặc bán dưới giá sàn) → xem Luồng 2 bên dưới (Phê duyệt).

### 1.4. Gửi khách & tạo đơn bán hàng

1. Sau khi báo giá ở trạng thái **"Đã duyệt nội bộ"** (hoặc bỏ qua bước duyệt nếu không vượt ngưỡng): bấm **"Gửi khách hàng"** → trạng thái "Đã gửi khách".
2. Đánh dấu khách đồng ý (nút tương ứng) → trạng thái "**Khách đồng ý**".
3. Bấm **"Tạo đơn bán hàng"** → hệ thống copy toàn bộ dòng + tiền sang **Đơn bán hàng** mới, khóa báo giá ở "**Đã lên đơn**", tự chuyển sang màn Chi tiết Đơn bán hàng.

**Xem đơn bán hàng:** menu **Báo giá › Đơn bán hàng**.

---

## LUỒNG 2 — Phê duyệt báo giá vượt ngưỡng (Trưởng KD / CEO)

1. Ở bước 1.3, nếu báo giá vượt ngưỡng (chiết khấu/giá sàn), hệ thống tự tạo 1 **yêu cầu phê duyệt**, hiện banner đỏ ngay trên form báo giá.
2. Đăng nhập bằng người duyệt phù hợp:
   - Vượt **mức trung bình** → `truongkd@dlm.demo` (Trưởng phòng Kinh doanh).
   - Vượt **mức cao** (VD dưới giá sàn, hoặc giá trị rất lớn) → `ceo@dlm.demo` (Giám đốc).
3. Vào menu **Phê duyệt** (chỉ hiện với 2 role trên) → thấy danh sách các yêu cầu **"Chờ duyệt"**, có đếm số việc cần xử lý ngay trên menu.
4. Mở 1 yêu cầu → xem thông tin: Lý do phát sinh phê duyệt, Cấp duyệt xác định, Giá thành & lợi nhuận nội bộ.
5. Bấm **"Tác vụ"** ở góc trên form → chọn **"Phê duyệt"** hoặc **"Từ chối"**.
6. Quay lại báo giá gốc (SCR-27) → banner cập nhật theo kết quả duyệt → nếu Phê duyệt, báo giá chuyển "Đã duyệt nội bộ", tiếp tục Luồng 1 bước 1.4.

**Lưu ý test RBAC theo cấp:** Trưởng KD chỉ thấy nút Phê duyệt/Từ chối cho yêu cầu đúng cấp "Trưởng kinh doanh" của mình; CEO thấy đủ cho cả 2 cấp.

---

## LUỒNG 3 — Kế toán quản lý Giá bán & Bảng giá NCC

1. Đăng nhập `ketoan@dlm.demo` — landing vào **Bảng giá Vật tư**.
2. **Duyệt giá bán sản phẩm thương mại mới:** vào **Sản phẩm & Vật tư › Sản phẩm**, tìm SP thương mại đang "Nháp" chưa có giá (do Sales tạo) → mở form → nhập **Giá bán** (chỉ Kế toán/Admin sửa được trường này) → Lưu. Sau đó Sales mới duyệt được SP này.
3. **Cập nhật Bảng giá NCC:** vào **Bảng giá › Bảng giá Vật tư** → tìm dòng vật tư cần cập nhật:
   - Dòng "Nháp" → bấm **"Duyệt"** → chuyển "Đã duyệt".
   - Dòng "Đã duyệt" → bấm **"Áp dụng"** → chuyển "Đang áp dụng" — **lưu ý:** nếu vật tư đó đang có 1 dòng "Đang áp dụng" khác (từ NCC khác), dòng cũ sẽ **tự động** chuyển về "Đã duyệt" (mỗi vật tư chỉ tối đa 1 dòng đang áp dụng).
4. **Quản lý NCC:** vào menu **NCC / Thầu phụ** → có thể tạo mới, sửa, Vô hiệu hóa/Kích hoạt lại. Lưu ý: NCC **không** validate chặt SĐT/Email/MST như Khách hàng (có thể nhập sai định dạng vẫn lưu được — đây là thiết kế có chủ đích theo FDS).

---

## LUỒNG 4 — Admin quản lý User & Phân quyền

1. Đăng nhập `admin@dlm.demo` — landing vào **Quản lý người dùng**.
2. **Tạo user mới:** bấm **"Tạo người dùng"** → nhập Họ tên, Email (bắt buộc đúng định dạng, nút Lưu chỉ bật khi hợp lệ), chọn Vai trò → **"Lưu & gửi lời mời"** → hệ thống tạo user + gửi email mời đặt mật khẩu, danh sách tự chọn user mới.
   - ⚠️ Nếu email trùng với user có sẵn, hệ thống báo lỗi đúng — nhưng **sẽ mất hết dữ liệu đã nhập trong form** (bug UX đã ghi nhận), phải nhập lại từ đầu.
3. **Khóa/Mở khóa tài khoản:** chọn 1 user ở list bên trái → bấm "Khóa tài khoản" (có dialog xác nhận) → trạng thái chuyển "Bị khóa", nút đổi thành "Mở khóa". Không thể tự khóa tài khoản đang đăng nhập (có dialog chặn).
4. **Phân quyền (RBAC):** vào **Cấu hình › Phân quyền** → chọn 1 vai trò ở sidebar → xem ma trận CRUD (Xem/Thêm/Sửa/Xóa) theo từng chức năng.
   - ⚠️ **Bug Critical đã biết:** hiện KHÔNG tick/untick được bất kỳ checkbox CRUD nào (kể cả cho chính Admin/IT) — hệ thống báo lỗi "không được phép truy cập dữ liệu Models". Đây là lỗi cấu hình quyền lõi Odoo, không phải bug thao tác — không cần tốn thời gian thử lại nhiều lần, đã confirm và báo Dev.

---

## LUỒNG 5 — Trưởng phòng Kinh doanh giám sát

1. Đăng nhập `truongkd@dlm.demo`.
2. Xem **Báo giá** (chỉ đọc — không có nút "Thêm").
3. Xem **NCC / Thầu phụ** (chỉ đọc).
4. Vào **Phê duyệt** xử lý các yêu cầu đúng cấp của mình (xem Luồng 2).
   - ⚠️ Bug đã biết: hiện **vẫn thấy và bấm được nút "Thêm đơn bán hàng"** dù theo FDS vai trò này không được tạo đơn — cẩn thận nếu vô tình bấm nhầm sẽ tạo dữ liệu rác.

---

## Checklist nhanh cho UAT

- [ ] Tạo RFQ (Sales) → Xử lý RFQ (Kỹ thuật) → Tạo Báo giá (Sales) → Gửi khách → Tạo đơn bán hàng
- [ ] Báo giá vượt ngưỡng → xuất hiện yêu cầu phê duyệt → Trưởng KD/CEO duyệt đúng cấp
- [ ] Kế toán cập nhật giá bán SP thương mại, duyệt/áp dụng Bảng giá NCC
- [ ] Admin tạo user, khóa/mở khóa tài khoản
- [ ] Kiểm tra các màn RBAC ẩn/hiện đúng theo từng vai trò (cột Giá thành, nút Thêm, nút Vô hiệu hóa...)

## Các bug đã biết — tránh mất thời gian test lại, xem chi tiết đầy đủ tại `bug-log.md`

| Màn | Vấn đề | Mức độ |
|---|---|---|
| SCR-27 (Chi tiết báo giá) | Nút "+ Thêm dòng" không bấm được | **Critical** |
| SCR-04 (Phân quyền RBAC) | Không tick được checkbox CRUD nào | **Critical** |
| SCR-32 (Cấu hình Hệ thống) | Menu biến mất hoàn toàn | **Critical** |
| SCR-24 (Kỹ thuật) | "Cấu hình Báo giá" bị lộ cho Kỹ thuật | **Critical** |
| SCR-28 (Trưởng KD) | Tạo được đơn bán hàng trái phép | Major |
| SCR-19/20 | Menu "Đo lường" không có điểm vào | Major |
| SCR-23 (RFQ gia công) | SL=0 không bị chặn; Mô tả/Ảnh bị bắt buộc nhầm | Major |
| SCR-21 (Trưởng KD) | Thiếu nút "Mới" | Minor |
| SCR-34 | Màn "Công ty" chưa được lập trình | Minor |
| SCR-03 (Tạo user) | Mất dữ liệu form khi lỗi trùng email | Minor |
