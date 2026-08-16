/** @odoo-module **/
/**
 * Lỗi nghiệp vụ hiện bằng TOAST thay vì hộp thoại "Ôi!".
 *
 * Mặc định Odoo đẩy mọi lỗi từ server qua registry "error_dialogs" ⇒ ra một
 * modal chặn màn hình (WarningDialog). Với lỗi nghiệp vụ thường gặp — thiếu ô
 * bắt buộc, sai định dạng, sai trạng thái — modal là quá nặng tay: nó che form,
 * bắt bấm thêm một nút mới quay lại sửa được, và không cho nhìn ô đang sai.
 *
 * Odoo có sẵn đường thoát: registry "error_notifications" được rpcErrorHandler
 * kiểm TRƯỚC "error_dialogs" (xem web/static/src/core/errors/error_handlers.js).
 * Khai một exceptionName ở đây là mọi lỗi loại đó trong TOÀN hệ thống tự chuyển
 * sang toast — không màn nào phải sửa riêng, không patch, không ghi đè.
 *
 * ⚠️ KHÔNG thêm "odoo.exceptions.RedirectWarning" vào đây: loại đó mang theo
 * một nút hành động (mở màn khác để xử lý), phải giữ hộp thoại mới bấm được.
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const errorNotificationRegistry = registry.category("error_notifications");

// Lỗi do người dùng nhập/thao tác sai: người dùng sửa ngay tại chỗ, toast tự
// tắt sau vài giây (rê chuột vào thì dừng đếm giờ — notification_service).
const BUSINESS_ERROR = {
    type: "warning",
    sticky: false,
};

// Lỗi hệ thống/quyền: hiếm, và người dùng thường phải chép lại nội dung gửi
// Admin ⇒ giữ toast tới khi tự bấm đóng.
const SYSTEM_ERROR = {
    type: "danger",
    sticky: true,
};

errorNotificationRegistry
    .add("odoo.exceptions.ValidationError", {
        ...BUSINESS_ERROR,
        title: _t("Chưa lưu được"),
    })
    .add("odoo.exceptions.UserError", {
        ...BUSINESS_ERROR,
        title: _t("Không thực hiện được"),
    })
    .add("odoo.exceptions.Warning", {
        ...BUSINESS_ERROR,
        title: _t("Cảnh báo"),
    })
    .add("odoo.exceptions.AccessError", {
        ...SYSTEM_ERROR,
        title: _t("Không đủ quyền"),
    })
    .add("odoo.exceptions.AccessDenied", {
        ...SYSTEM_ERROR,
        title: _t("Từ chối truy cập"),
    })
    .add("odoo.exceptions.MissingError", {
        ...SYSTEM_ERROR,
        title: _t("Bản ghi không còn tồn tại"),
    });
