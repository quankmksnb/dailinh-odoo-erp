# -*- coding: utf-8 -*-
"""§3.1 Entity Definitions — module D (dl_config)."""

MIXIN_COLS_NOTE = (
    "+ 6 cột vật chất hoá từ mixin D1: company_id (INTEGER, NOT NULL, INDEX), "
    "revision (INTEGER, DEFAULT 1), valid_from (DATE, NOT NULL), valid_to (DATE, nullable), "
    "change_reason (VARCHAR, nullable), used_in_snapshot (BOOLEAN, DEFAULT FALSE)."
)

MODULE_D = {
    "title": "D. Module dl_config — cấu hình giá & phê duyệt",
    "lead": "Toàn bộ tham số dùng để tính giá và toàn bộ luồng phê duyệt nằm ở đây. Đặc điểm "
            "chung: các quy tắc đều có HIỆU LỰC THEO THỜI GIAN (valid_from / valid_to) và số "
            "REVISION, thay vì sửa đè — nhờ vậy báo giá cũ vẫn tra lại đúng tham số đã dùng. "
            "Nhóm này thay thế hoàn toàn các entity C2 dl.cost.parameter, D6 dl.discount.policy, "
            "E1 dl.approval.rule, E3 dl.approval.threshold.config của thiết kế trước.",
    "entities": [
        {
            "head": "D1. dl.pricing.rule.mixin [AbstractModel — không có bảng]",
            "desc": "Thuộc tính chung của MỌI quy tắc cấu hình báo giá. Là AbstractModel nên không "
                    "có bảng riêng: 6 field bên dưới được vật chất hoá thành cột trong bảng của "
                    "từng model kế thừa (D3, D4, D5, D7, D8, D10).",
            "meta": "_inherit = ['mail.thread']   ·   _order = 'valid_from desc, id desc'",
            "cols": [
                ["company_id", "INTEGER", "NOT NULL, INDEX (index=True)", "FK → res_company, mặc định self.env.company"],
                ["revision", "INTEGER", "DEFAULT 1", "Số lần sửa đổi; readonly, copy=False"],
                ["valid_from", "DATE", "NOT NULL", "Ngày bắt đầu hiệu lực, mặc định hôm nay"],
                ["valid_to", "DATE", "nullable", "Ngày hết hiệu lực; readonly, copy=False"],
                ["change_reason", "VARCHAR", "nullable", "Lý do thay đổi (ghi vào tracking)"],
                ["used_in_snapshot", "BOOLEAN", "DEFAULT FALSE", "Đã bị 1 báo giá chốt tham chiếu ⇒ không được sửa/xoá"],
            ],
            "extra": "Ràng buộc: _check_valid_range (valid_from ≤ valid_to).",
        },
        {
            "head": "D2. dl.pricing.commercial.mixin [AbstractModel — không có bảng]",
            "desc": "Kế thừa D1 và bổ sung LUỒNG BẮT BUỘC PHÊ DUYỆT cho các cấu hình mang tính "
                    "thương mại (lợi nhuận, chiết khấu): bản ghi phải qua Chờ duyệt trước khi được "
                    "áp dụng. Không khai thêm field nào — chỉ bổ sung hành vi.",
            "meta": "_inherit = ['dl.pricing.rule.mixin']",
            "cols": [],
        },
        {
            "head": "D3. dl.pricing.profit.rule [Model mới]",
            "desc": "Chính sách lợi nhuận và giá sàn. Báo giá có markup thực thấp hơn min_markup "
                    "sẽ bị đánh dấu below_floor và phải xin duyệt.",
            "meta": "_inherit = ['dl.pricing.commercial.mixin']   ·   _rec_name = 'name'",
            "cols": [
                ["name", "VARCHAR", "nullable", "compute, store=True → CÓ cột"],
                ["target_markup", "NUMERIC(6,2)", "NOT NULL", "Lợi nhuận mục tiêu (%)"],
                ["min_markup", "NUMERIC(6,2)", "NOT NULL", "Lợi nhuận tối thiểu / giá sàn (%)"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái THƯƠNG MẠI); copy=False"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_markup (min_markup ≤ target_markup).",
        },
        {
            "head": "D4. dl.pricing.discount.rule [Model mới]",
            "desc": "Chính sách chiết khấu theo NHÓM KHÁCH HÀNG. Có kiểm tra thang bậc: khách gắn bó "
                    "lâu hơn phải được chiết khấu KHÔNG THẤP hơn khách mới hơn (mới ≤ cũ ≤ thân thiết).",
            "meta": "_inherit = ['dl.pricing.commercial.mixin']   ·   "
                    "_order = 'group_rank asc, state, valid_from desc, id desc'",
            "cols": [
                ["name", "VARCHAR", "nullable", "compute, store=True → CÓ cột"],
                ["customer_group", "VARCHAR", "NOT NULL, DEFAULT 'new'", "Enum §3.3"],
                ["group_rank", "INTEGER", "nullable", "compute, store=True → CÓ cột. Bậc gắn bó: new=0, existing=1, loyal=2"],
                ["default_rate", "NUMERIC(6,2)", "NOT NULL", "Chiết khấu mặc định (%)"],
                ["max_rate", "NUMERIC(6,2)", "NOT NULL", "Chiết khấu tối đa (%)"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái THƯƠNG MẠI); copy=False"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_rates (default_rate ≤ max_rate); _check_group_ladder "
                     "(giữ thang bậc giữa các nhóm khách trong cùng công ty).",
        },
        {
            "head": "D5. dl.pricing.cost.adjustment.rule [Model mới]",
            "desc": "Chi phí chung và hệ số điều chỉnh — chi phí xưởng, đóng gói, vận chuyển, đơn "
                    "hàng nhỏ, giao gấp, độ phức tạp, dự phòng. Thay thế entity dl.cost.parameter "
                    "của thiết kế cũ.",
            "meta": "_inherit = ['dl.pricing.rule.mixin']",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên quy tắc"],
                ["rule_type", "VARCHAR", "NOT NULL, DEFAULT 'workshop_overhead'", "Enum §3.3 — 8 loại chi phí"],
                ["method", "VARCHAR", "NOT NULL, DEFAULT 'percent_direct'", "Enum §3.3 — 6 cách tính"],
                ["value", "NUMERIC(16,2)", "NOT NULL", "Giá trị áp dụng theo method"],
                ["condition_days", "INTEGER", "nullable", "Điều kiện kích hoạt theo số ngày (giao gấp)"],
                ["condition_amount", "NUMERIC(16,2)", "nullable", "Điều kiện kích hoạt theo giá trị (đơn hàng nhỏ)"],
                ["no_discount", "BOOLEAN", "nullable", "Cấu phần này không chịu chiết khấu"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái KỸ THUẬT); copy=False"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_value (giá trị hợp lệ theo method — vd method dạng % phải trong khoảng cho phép).",
        },
        {
            "head": "D6. dl.pricing.operation [Model mới]",
            "desc": "Danh mục CÔNG ĐOẠN gia công dùng chung (cắt, hàn, sơn…). Tách khỏi bảng đơn giá "
                    "để 1 công đoạn có thể có nhiều bản đơn giá theo thời gian.",
            "meta": "_order = 'sequence, name'   ·   _sql_constraints: code_uniq = unique(code)",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên công đoạn"],
                ["code", "VARCHAR", "NOT NULL, UNIQUE", "Mã công đoạn"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Đang sử dụng"],
            ],
        },
        {
            "head": "D7. dl.pricing.operation.rule [Model mới]",
            "desc": "Đơn giá / tỷ lệ cho từng công đoạn, có hiệu lực theo thời gian.",
            "meta": "_inherit = ['dl.pricing.rule.mixin']   ·   _rec_name = 'operation_id'",
            "cols": [
                ["operation_id", "INTEGER", "NOT NULL, ON DELETE RESTRICT", "FK → dl_pricing_operation (D6)"],
                ["method", "VARCHAR", "NOT NULL, DEFAULT 'percent_material'", "Enum §3.3 — 6 phương pháp tính"],
                ["price_rate", "NUMERIC(16,2)", "NOT NULL", "Đơn giá hoặc tỷ lệ theo method"],
                ["setup_fee", "NUMERIC(16,2)", "nullable", "Phí chuẩn bị (cố định theo lô)"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái KỸ THUẬT); copy=False"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_values (price_rate / setup_fee hợp lệ theo method).",
        },
        {
            "head": "D8. dl.pricing.waste.rule [Model mới]",
            "desc": "Quy tắc hao hụt & thu hồi MẶC ĐỊNH, áp theo nhóm sản phẩm hoặc theo đúng 1 vật tư. "
                    "Đây chỉ là NGUỒN GỢI Ý: khi tạo vật tư, dl_technical đọc quy tắc này để tự điền "
                    "dlm_waste_rate lên chính bản ghi vật tư (C1) — lúc tính giá, BOM đọc thẳng field "
                    "trên vật tư chứ không tra lại bảng này.",
            "meta": "_inherit = ['dl.pricing.rule.mixin']   ·   _rec_name = 'target_label'",
            "cols": [
                ["target_type", "VARCHAR", "NOT NULL, DEFAULT 'category'", "Enum §3.3 — category / product"],
                ["category_id", "INTEGER", "nullable, ON DELETE RESTRICT", "FK → product_category"],
                ["product_id", "INTEGER", "nullable, ON DELETE RESTRICT", "FK → product_product (vật tư)"],
                ["target_label", "VARCHAR", "nullable", "compute, store=True → CÓ cột"],
                ["waste_rate", "NUMERIC(6,2)", "NOT NULL", "Tỷ lệ hao hụt (%)"],
                ["has_recovery", "BOOLEAN", "nullable", "Có thu hồi phế liệu"],
                ["recovery_rate", "NUMERIC(6,2)", "nullable", "Tỷ lệ thu hồi (%) trên lượng hao hụt"],
                ["scrap_product_id", "INTEGER", "nullable, ON DELETE RESTRICT", "FK → product_product (sản phẩm phế)"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái KỸ THUẬT); copy=False"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_target (đúng 1 trong category_id / product_id theo target_type); _check_rates.",
        },
        {
            "head": "D9. dl.pricing.complexity.level [Model mới]",
            "desc": "Hệ số phức tạp dùng chung. Chọn trên từng dòng BOM và NHÂN vào tỷ lệ hao hụt "
                    "cơ sở của vật tư khi tính giá.",
            "meta": "_order = 'sequence, factor'",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên mức phức tạp"],
                ["factor", "NUMERIC(6,2)", "NOT NULL, DEFAULT 1.0", "Hệ số nhân"],
                ["note", "VARCHAR", "nullable", "Ghi chú"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Đang sử dụng"],
            ],
            "extra": "Ràng buộc: _check_factor.",
        },
        {
            "head": "D10. dl.pricing.approval.matrix [Model mới]",
            "desc": "MA TRẬN PHÊ DUYỆT báo giá theo ngưỡng giá trị: từ mốc value_from trở lên thì cần "
                    "cấp duyệt nào. Thay thế entity dl.approval.rule + dl.approval.threshold.config "
                    "của thiết kế cũ. Sửa ma trận cũng phải qua phê duyệt (D12).",
            "meta": "_inherit = ['dl.pricing.rule.mixin']   ·   "
                    "_order = 'value_from asc, revision desc, id desc'",
            "cols": [
                ["value_from", "NUMERIC", "NOT NULL", "Mốc giá trị bắt đầu áp dụng (Monetary)"],
                ["currency_id", "INTEGER", "nullable", "related company_id.currency_id, store=True → CÓ cột"],
                ["approval_level", "VARCHAR", "NOT NULL, DEFAULT 'sales_manager'", "Enum §3.3 — none / sales_manager / ceo"],
                ["level_rank", "INTEGER", "nullable", "compute, store=True → CÓ cột. none=0, sales_manager=1, ceo=2"],
                ["approver_user_id", "INTEGER", "nullable", "FK → res_users — chỉ định người duyệt cụ thể"],
                ["note", "VARCHAR", "nullable", "Ghi chú"],
                ["revised_from_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → dl_pricing_approval_matrix (tự tham chiếu) — bản ghi gốc bị sửa đổi"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'draft', INDEX", "Enum §3.3 (trạng thái KỸ THUẬT); copy=False"],
                ["pending_request_id, has_pending_request", "—", "—", "compute, store=False → KHÔNG sinh cột"],
                [MIXIN_COLS_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_value_from; _check_approver_in_role (người duyệt phải thuộc "
                     "đúng nhóm quyền của cấp duyệt); _check_unique_threshold (không trùng mốc giá trị "
                     "trong cùng công ty ở trạng thái đang áp dụng); _check_level_monotonic "
                     "(giá trị càng cao thì cấp duyệt không được thấp đi).",
        },
        {
            "head": "D11. dl.pricing.approval.setting [Model mới]",
            "desc": "Người duyệt mặc định theo TỪNG LOẠI yêu cầu.",
            "meta": "_order = 'request_type'   ·   _sql_constraints: type_company_uniq = "
                    "unique(request_type, company_id)",
            "cols": [
                ["request_type", "VARCHAR", "NOT NULL", "Enum §3.3 — 6 loại yêu cầu"],
                ["approver_role", "VARCHAR", "NOT NULL, DEFAULT 'ceo'", "Enum §3.3 — sales_manager / ceo"],
                ["approver_user_id", "INTEGER", "nullable", "FK → res_users"],
                ["company_id", "INTEGER", "NOT NULL, INDEX (index=True)", "FK → res_company"],
            ],
        },
        {
            "head": "D12. dl.pricing.approval.request [Model mới + mail.thread]",
            "desc": "YÊU CẦU PHÊ DUYỆT — mỗi lần xin duyệt (đổi cấu hình thương mại, hoặc báo giá vượt "
                    "ngưỡng/chiết khấu/dưới giá sàn) sinh 1 bản ghi. Thay thế entity "
                    "dl.quotation.approval của thiết kế cũ; lịch sử thao tác nằm ở mail_message "
                    "qua mail.thread chứ không tự dựng bảng lịch sử.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin']   ·   "
                    "_order = 'create_date desc, id desc'   ·   _rec_name = 'title'\n"
                    "Trỏ tới đối tượng cần duyệt bằng cặp res_model + res_id (tham chiếu MỀM, "
                    "KHÔNG có FK).",
            "cols": [
                ["title", "VARCHAR", "nullable", "compute, store=True → CÓ cột"],
                ["request_type", "VARCHAR", "NOT NULL", "Enum §3.3"],
                ["res_model", "VARCHAR", "nullable", "Tên model của đối tượng cần duyệt — KHÔNG có FK"],
                ["res_id", "INTEGER", "nullable", "ID bản ghi cần duyệt — KHÔNG có FK"],
                ["object_label, old_value, new_value, impact", "VARCHAR", "nullable", "Ảnh chụp mô tả thay đổi để hiển thị cho người duyệt"],
                ["requester_id", "INTEGER", "nullable", "FK → res_users, mặc định người đang đăng nhập"],
                ["requester_role", "VARCHAR", "nullable", "Vai trò người yêu cầu tại thời điểm gửi"],
                ["reason", "TEXT", "NOT NULL", "Lý do xin duyệt"],
                ["resolved_by_id", "INTEGER", "nullable", "FK → res_users — người đã xử lý"],
                ["resolved_at", "TIMESTAMP", "nullable", "Thời điểm xử lý"],
                ["reject_comment", "TEXT", "nullable", "Lý do từ chối"],
                ["is_self_approval", "BOOLEAN", "nullable", "Người duyệt trùng người yêu cầu"],
                ["approval_level", "VARCHAR", "nullable", "Enum §3.3 — cấp duyệt đã xác định"],
                ["matrix_row_id", "INTEGER", "nullable, ON DELETE RESTRICT", "FK → dl_pricing_approval_matrix (D10) — dòng ma trận đã dùng"],
                ["matrix_revision", "INTEGER", "nullable", "Revision của dòng ma trận tại thời điểm xét"],
                ["trigger_reasons", "TEXT", "nullable", "Các lý do khiến phải duyệt"],
                ["state", "VARCHAR", "NOT NULL, DEFAULT 'pending', INDEX", "Enum §3.3 — pending / approved / rejected / cancelled"],
                ["company_id", "INTEGER", "NOT NULL, INDEX (index=True)", "FK → res_company"],
                ["quotation_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → dl_quotation (F1). compute, store=True → CÓ cột. Khai ở dl_sale"],
                ["can_resolve", "—", "—", "compute, store=False → KHÔNG sinh cột"],
                ["q_* (khoảng 20 field)", "—", "—", "Khai ở dl_sale; related qua quotation_id, store=False → KHÔNG sinh cột"],
            ],
        },
        {
            "head": "D13. dl.pricing.config [Model mới]",
            "desc": "Tham số báo giá tổng thể (cơ cấu giá thành, VAT, làm tròn, hiệu lực báo giá) và "
                    "cấu hình SLA phê duyệt. Là bản ghi cấu hình đơn — không phải "
                    "res.config.settings.",
            "cols": [
                ["name", "VARCHAR", "NOT NULL, DEFAULT 'Cấu hình báo giá'", "Tên bản cấu hình"],
                ["material_pct, labor_pct, overhead_pct, risk_pct, margin_pct", "DOUBLE PRECISION",
                 "DEFAULT 55 / 25 / 5 / 3 / 12", "Cơ cấu giá thành mục tiêu (%)"],
                ["max_discount_pct", "DOUBLE PRECISION", "DEFAULT 15.0", "Trần chiết khấu (%)"],
                ["vat_pct", "DOUBLE PRECISION", "DEFAULT 0.0", "VAT mặc định (%)"],
                ["price_validity_days", "INTEGER", "DEFAULT 30", "Số ngày hiệu lực báo giá"],
                ["rounding_to", "INTEGER", "DEFAULT 1000", "Làm tròn tới (VND)"],
                ["matrix_seeded", "BOOLEAN", "DEFAULT FALSE", "Đã nạp ma trận phê duyệt mẫu"],
                ["sla_sales_manager_hours, sla_ceo_hours, sla_reminder_every_hours", "INTEGER",
                 "DEFAULT 4 / 8 / 2", "Ngưỡng SLA duyệt (giờ)"],
                ["sla_require_late_reason, sla_overdue_remind, sla_overdue_escalate, "
                 "sla_overdue_log, sla_overdue_kpi", "BOOLEAN", "DEFAULT TRUE", "Hành vi khi quá hạn SLA"],
                ["structure_total", "—", "—", "compute, store=False → KHÔNG sinh cột"],
                ["waste_ids, level_ids", "—", "—", "One2many → D14, D15; không sinh cột"],
            ],
        },
        {
            "head": "D14. dl.pricing.waste [Model mới]",
            "desc": "Dòng hao hụt mặc định theo TÊN nhóm vật tư, thuộc D13. Khác D8 ở chỗ đây chỉ là "
                    "bảng nhập liệu dạng text trên màn cấu hình, không trỏ FK tới product.category.",
            "meta": "_order = 'id'",
            "cols": [
                ["config_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_pricing_config (D13)"],
                ["group_name", "VARCHAR", "NOT NULL", "Tên nhóm vật tư (text tự do)"],
                ["waste_pct", "DOUBLE PRECISION", "nullable", "Tỷ lệ hao hụt (%)"],
            ],
        },
        {
            "head": "D15. dl.approval.level [Model mới]",
            "desc": "Cấp duyệt trong ma trận phê duyệt trên màn Cấu hình, thuộc D13.",
            "meta": "_order = 'sequence, id'",
            "cols": [
                ["config_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_pricing_config (D13)"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự cấp"],
                ["name", "VARCHAR", "NOT NULL", "Tên cấp duyệt"],
                ["value_min, value_max", "DOUBLE PRECISION", "DEFAULT 0.0", "Khoảng giá trị áp dụng"],
                ["discount_min, discount_max", "DOUBLE PRECISION", "DEFAULT 0.0 / 100.0", "Khoảng chiết khấu áp dụng"],
                ["margin_min", "DOUBLE PRECISION", "DEFAULT 0.0", "Ngưỡng lợi nhuận tối thiểu"],
                ["approver_role", "VARCHAR", "NOT NULL, DEFAULT 'sales_manager'", "Enum §3.3 — none / sales_manager / ceo / custom"],
                ["approver_user_id, backup_user_id", "INTEGER", "nullable", "FK → res_users"],
                ["mode", "VARCHAR", "NOT NULL, DEFAULT 'sequential'", "Enum §3.3 — sequential / parallel / direct / none"],
                ["sla_hours", "INTEGER", "DEFAULT 4", "SLA của cấp này (giờ)"],
                ["note", "VARCHAR", "nullable", "Ghi chú"],
                ["is_active", "BOOLEAN", "DEFAULT TRUE", "Cấp đang bật"],
                ["is_priority", "BOOLEAN", "DEFAULT FALSE", "Ưu tiên"],
                ["pending_count", "INTEGER", "DEFAULT 0", "Số yêu cầu đang chờ; readonly"],
            ],
        },
        {
            "head": "D16. dl.config.audit.log [Model mới]",
            "desc": "Nhật ký thay đổi cấu hình hệ thống. Thay thế entity dl.audit.log của thiết kế cũ. "
                    "Ghi ở dạng mô tả text, KHÔNG có FK tới bản ghi bị đổi.",
            "meta": "_order = 'id desc'",
            "cols": [
                ["config_tab", "VARCHAR", "nullable", "Tab cấu hình bị đổi"],
                ["param_label", "VARCHAR", "nullable", "Tham số bị đổi"],
                ["detail", "VARCHAR", "nullable", "Chi tiết thay đổi"],
                ["user_id", "INTEGER", "nullable", "FK → res_users, mặc định người đang đăng nhập"],
            ],
        },
        {
            "head": "D17. dl.pricing.ui [TransientModel]",
            "desc": "Model bootstrap dữ liệu cho màn Cấu hình Báo giá (OWL). KHÔNG khai field nào — "
                    "chỉ có phương thức trả dữ liệu về client.",
            "cols": [],
        },
        {
            "head": "D18. res.users [Mở rộng — _inherit]",
            "desc": "Mở rộng người dùng Odoo. Lưu ý: 6 nhóm quyền của dự án là BẢN GHI res.groups "
                    "khai bằng XML ở dl_base, không phải cột trên bảng này.",
            "cols": [
                ["dl_backup_approver_id", "INTEGER", "nullable", "FK → res_users (tự tham chiếu) — người duyệt dự phòng"],
            ],
        },
    ],
}
