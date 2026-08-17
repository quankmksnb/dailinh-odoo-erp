# Ảnh thương hiệu Đại Linh

Hai file trong thư mục này là **nguồn duy nhất** của logo trong toàn hệ thống —
đừng chép logo sang module khác.

| File | Dùng ở đâu |
| ---- | ---------- |
| `dai_linh_logo.png` | lockup ngang đầy đủ. Nạp vào `res.company.logo` (⇒ trang đăng nhập, PDF/Word báo giá, đơn mua, biên bản hàng không đạt) và hero màn Trang chủ. |
| `dai_linh_mark.png` | riêng biểu tượng DL, khung vuông. Icon rail, brand navbar Trang chủ, favicon tab trình duyệt, icon module. |

## Sinh lại từ file gốc

Không sửa tay hai file trên. Đưa ảnh logo gốc (lockup ngang, nền trắng) vào rồi chạy:

```
python scripts/make_logo_assets.py <đường-dẫn-file-logo-gốc>
```

Script cắt lề trắng, tách biểu tượng khỏi phần chữ, và cập nhật luôn
`static/description/icon.png` của `dl_base` + `dl_sale`.

Sau khi sinh xong phải `-u dl_base` để `_dlm_setup_identity` đẩy logo mới lên
`res.company` (xem `dl_base/models/res_company.py`).
