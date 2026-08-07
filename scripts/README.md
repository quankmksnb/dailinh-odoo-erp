# scripts/ — Tái tạo DB demo

Bộ script để **xóa DB cũ, tạo lại DB sạch và nạp đầy đủ dữ liệu demo test** —
chạy lại bất cứ lúc nào, không cần nhờ ai tạo DB.

## Cách chạy

1. **STOP phiên debug VS Code** (server chạy qua debugpy, tự respawn — phải tắt
   trước khi drop DB).
2. Mở PowerShell tại thư mục gốc dự án và chạy:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\reset_demo_db.ps1
   ```

   Gõ `yes` khi được hỏi. Script sẽ:
   - Drop + create lại DB (mặc định `dlm_dev`, đọc thông số từ `odoo.conf`).
   - Cài toàn bộ module + `dl_demo`, chạy `post_init_hook` seed dữ liệu.
3. **Start lại phiên debug VS Code**, mở http://127.0.0.1:8069.

> Đổi tên DB: `... reset_demo_db.ps1 -Database dlm_test`

## Tài khoản demo (mật khẩu chung `123456`)

| Vai trò        | Đăng nhập            |
| -------------- | -------------------- |
| CEO            | `ceo@gmail.com`      |
| Admin / IT     | `admin.it@gmail.com` |
| Trưởng phòng KD| `truongkd@gmail.com` |
| BA / Sales     | `ba@gmail.com`       |
| Kỹ thuật       | `kythuat@gmail.com`  |
| Kế toán        | `ketoan@gmail.com`   |
| Mua hàng       | `muahang@gmail.com`  |

## Dữ liệu demo gồm gì (module `dlm-erp/dl_demo`)

- **Khách hàng** phủ 3 nhóm tự động: mới (Cơ khí Tân Tiến), cũ (Minh Long),
  thân thiết (Thành Đô) + khách cá nhân + NCC (Hòa Phát, Đại Bàng, Phú Thịnh).
- **Giá NCC** (product.supplierinfo) ở trạng thái Nháp / Đã duyệt / Đang áp dụng.
- **RFQ Kỹ thuật** đủ 7 trạng thái: Mới, Đang xử lý, Trả lại bổ sung, Đã bổ sung,
  Chờ tạo báo giá, Đã tạo báo giá, Đã hủy.
- **BOM** Nháp / Đã xác nhận / cha–con (BTP) + **bản vẽ** + BOM tham số D×R×C (seed sẵn).
- **Báo giá** đủ vòng đời: Nháp, Đã duyệt nội bộ (qua), Đã gửi khách, Yêu cầu
  điều chỉnh, Khách đồng ý, Đã lên đơn, Từ chối, Hết hiệu lực, Đã thay bản mới.
- **Phiếu phê duyệt** đang chờ: 1 cần Trưởng KD (>20tr), 1 cần CEO (>100tr).
- **Đơn bán hàng** sinh từ báo giá đã lên đơn.

## Ghi chú kỹ thuật

- `dl_demo` là module **chỉ dành cho dev/demo**. KHÔNG cài trên môi trường thật —
  không cài = DB sạch kiểu production.
- Master data tĩnh nạp bằng XML (`dl_demo/data/`); dữ liệu giao dịch (có state
  machine + engine giá) dựng bằng `dl_demo/hooks.py::post_init_hook` để đi qua
  đúng logic nghiệp vụ, liên kết chuẩn giữa các màn.
- Màn **Kho** (`dl_inventory`) hiện là placeholder (chưa có model/list) nên
  không seed phiếu kho.
- `_recreate_db.py` chỉ drop/create DB (psycopg2); mọi seed nằm trong `dl_demo`.
