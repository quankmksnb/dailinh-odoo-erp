# -*- coding: utf-8 -*-
"""§3 intro + entity summary table. All facts derived from source under dlm-erp/."""

INTRO_LEAD = (
    "Toàn bộ dữ liệu nằm trên PostgreSQL 16 và được khai báo qua ORM của Odoo 17 — "
    "không có DDL viết tay. Mục này liệt kê 7 module addon của DLM-ERP theo đúng thứ tự "
    "phụ thuộc (depends), và với mỗi module là các model được định nghĩa, cột vật lý sinh ra, "
    "quan hệ, enum và index."
)

MECH_HEADERS = ["Cơ chế", "Khai báo trong code", "Hệ quả ở tầng DB", "Dùng ở đâu trong dự án"]
MECH_WIDTHS = [20, 24, 28, 28]
MECH_ROWS = [
    ["Mở rộng (extension)",
     "_inherit = 'res.partner'",
     "KHÔNG tạo bảng mới. Field bổ sung được ALTER TABLE thêm cột vào chính bảng gốc.",
     "res.partner, product.category, product.supplierinfo, res.users"],
    ["Mở rộng + trộn mixin",
     "_name = 'product.product'\n_inherit = ['product.product', 'mail.thread', 'mail.activity.mixin']",
     "KHÔNG tạo bảng mới. Bắt buộc khai CẢ _name lẫn _inherit dạng list — thiếu _name khi "
     "_inherit là list sẽ báo lỗi \"The _name attribute … is not valid\".",
     "product.product (dl_product)"],
    ["Model mới",
     "_name = 'dl.bom'\nclass … (models.Model)",
     "Tạo bảng mới, tên bảng = _name thay '.' bằng '_' (dl.bom → dl_bom).",
     "32 bảng mới (xem bảng tổng hợp bên dưới)"],
    ["Mixin trừu tượng",
     "_name = 'dl.bom.line.mixin'\nclass … (models.AbstractModel)",
     "KHÔNG có bảng. Các field khai trong mixin được vật chất hoá thành cột trong bảng của "
     "MỌI model kế thừa nó.",
     "dl.pricing.rule.mixin, dl.pricing.commercial.mixin, dl.bom.header.mixin, "
     "dl.bom.line.mixin, dl.quotation.pricing.service"],
    ["Model tạm (wizard)",
     "class … (models.TransientModel)",
     "Có bảng vật lý nhưng bản ghi bị cron ir.autovacuum dọn định kỳ — không phải dữ liệu "
     "nghiệp vụ lâu dài.",
     "5 wizard: 4 ở dl_technical, 1 ở dl_config"],
    ["Uỷ quyền (_inherits)",
     "_inherits = {...}",
     "Tạo bảng con + cột FK tới bảng cha.",
     "KHÔNG DÙNG. Thiết kế cũ (dl.product / dl.semi.product / dl.material là 3 bảng "
     "delegation) đã bị loại bỏ ở bản refactor dl_product 17.0.2.x."],
]

COMMON_NOTE_LABEL = "Quy ước chung cho mọi bảng bên dưới"
COMMON_NOTE = (
    "(1) Mọi model đều được Odoo tự thêm 5 cột hạ tầng: id (BIGSERIAL PK), create_uid, "
    "create_date, write_uid, write_date — các bảng chi tiết bên dưới KHÔNG lặp lại chúng, "
    "trừ khi cột đó mang ý nghĩa nghiệp vụ.\n"
    "(2) Mọi Many2one có lưu trữ đều sinh 1 cột INTEGER kèm FOREIGN KEY và được Odoo tự tạo "
    "BTREE index — §3.4 chỉ liệt kê các index ĐẶC BIỆT (unique, index=True khai tường minh).\n"
    "(3) One2many KHÔNG sinh cột — nó chỉ là chiều đọc ngược của một Many2one ở bảng kia.\n"
    "(4) Field compute/related KHÔNG có store=True thì KHÔNG sinh cột — tính lúc đọc.\n"
    "(5) fields.Binary và fields.Image mặc định attachment=True → nội dung nằm ở bảng "
    "ir_attachment + filestore, KHÔNG sinh cột trong bảng của model.\n"
    "(6) Model trộn mail.thread / mail.activity.mixin không sinh cột — lịch sử nằm ở "
    "mail_message / mail_activity với res_model + res_id."
)

SUMMARY_INTRO = (
    "Bảng tổng hợp 53 entity trên 7 module (32 bảng nghiệp vụ mới + 5 bảng wizard tạm + "
    "5 mixin không bảng + 11 lượt mở rộng bảng có sẵn của Odoo):"
)

SUM_HEADERS = ["ID", "Model", "Cơ chế", "Bảng vật lý", "Mô tả"]
SUM_WIDTHS = [6, 25, 15, 21, 33]

SUM_ROWS = [
    ("GROUP", "MODULE A — dl_base 17.0.1.0.0   ·   depends: base, web, mail"),
    ["A1", "dl.rbac.feature", "Model mới", "dl_rbac_feature",
     "Danh mục chức năng dùng để dựng màn hình phân quyền"],
    ["A2", "dl.rbac.operation", "Model mới", "dl_rbac_operation",
     "Thao tác đặc biệt của 1 chức năng, ánh xạ sang 1 res.groups"],

    ("GROUP", "MODULE B — dl_partner 17.0.1.0.0   ·   depends: dl_base, mail"),
    ["B1", "res.partner", "Mở rộng", "res_partner (native)",
     "Đối tác — Khách hàng và/hoặc Nhà cung cấp, phân biệt bằng partner_role"],

    ("GROUP", "MODULE C — dl_product 17.0.2.4.0   ·   depends: dl_base, product, stock, uom, dl_partner"),
    ["C1", "product.product", "Mở rộng + mail.thread", "product_product (native)",
     "SẢN PHẨM — bảng hợp nhất cho cả 4 loại nghiệp vụ, phân biệt bằng product_kind"],
    ["C2", "product.category", "Mở rộng", "product_category (native)",
     "Nhóm sản phẩm; dl_branch suy ra từ vị trí trong cây (Thành phẩm / Vật tư)"],
    ["C3", "product.supplierinfo", "Mở rộng", "product_supplierinfo (native)",
     "Bảng giá vật tư / SP thương mại theo NCC + thời điểm, có bước duyệt giá"],
    ["C4", "dl.measurement.type", "Model mới", "dl_measurement_type",
     "Đại lượng đo lường (Diện tích / Chiều dài / Khối lượng / Thể tích)"],
    ["C5", "dl.measurement.shape", "Model mới", "dl_measurement_shape",
     "Hình dạng đo lường thuộc 1 đại lượng; code là khoá dispatch công thức"],
    ["C6", "dl.measurement.shape.param", "Model mới", "dl_measurement_shape_param",
     "Tên các tham số kích thước theo từng hình dạng"],

    ("GROUP", "MODULE D — dl_config 17.0.2.2.0   ·   depends: dl_base, uom, auth_signup, mail, product"),
    ["D1", "dl.pricing.rule.mixin", "AbstractModel", "— (không bảng)",
     "Thuộc tính chung mọi quy tắc cấu hình giá: hiệu lực, revision, công ty"],
    ["D2", "dl.pricing.commercial.mixin", "AbstractModel", "— (không bảng)",
     "Thêm luồng bắt buộc phê duyệt cho cấu hình THƯƠNG MẠI"],
    ["D3", "dl.pricing.profit.rule", "Model mới", "dl_pricing_profit_rule",
     "Chính sách lợi nhuận và giá sàn (markup mục tiêu / tối thiểu)"],
    ["D4", "dl.pricing.discount.rule", "Model mới", "dl_pricing_discount_rule",
     "Chính sách chiết khấu theo nhóm khách hàng, có kiểm tra thang bậc"],
    ["D5", "dl.pricing.cost.adjustment.rule", "Model mới", "dl_pricing_cost_adjustment_rule",
     "Chi phí chung và hệ số điều chỉnh (overhead, đóng gói, giao gấp…)"],
    ["D6", "dl.pricing.operation", "Model mới", "dl_pricing_operation",
     "Danh mục công đoạn gia công dùng chung"],
    ["D7", "dl.pricing.operation.rule", "Model mới", "dl_pricing_operation_rule",
     "Đơn giá / tỷ lệ cho từng công đoạn"],
    ["D8", "dl.pricing.waste.rule", "Model mới", "dl_pricing_waste_rule",
     "Quy tắc hao hụt & thu hồi mặc định theo nhóm hoặc theo đúng 1 vật tư"],
    ["D9", "dl.pricing.complexity.level", "Model mới", "dl_pricing_complexity_level",
     "Hệ số phức tạp dùng chung, chọn trên từng dòng BOM"],
    ["D10", "dl.pricing.approval.matrix", "Model mới", "dl_pricing_approval_matrix",
     "Ma trận phê duyệt báo giá theo ngưỡng giá trị"],
    ["D11", "dl.pricing.approval.setting", "Model mới", "dl_pricing_approval_setting",
     "Người duyệt mặc định theo từng loại yêu cầu"],
    ["D12", "dl.pricing.approval.request", "Model mới + mail.thread", "dl_pricing_approval_request",
     "Yêu cầu phê duyệt (cấu hình thương mại hoặc báo giá) — 1 bản ghi / 1 lần xin duyệt"],
    ["D13", "dl.pricing.config", "Model mới", "dl_pricing_config",
     "Tham số báo giá tổng thể + cấu hình SLA duyệt"],
    ["D14", "dl.pricing.waste", "Model mới", "dl_pricing_waste",
     "Dòng hao hụt mặc định theo tên nhóm vật tư, thuộc D13"],
    ["D15", "dl.approval.level", "Model mới", "dl_approval_level",
     "Cấp duyệt trong ma trận phê duyệt, thuộc D13"],
    ["D16", "dl.config.audit.log", "Model mới", "dl_config_audit_log",
     "Nhật ký thay đổi cấu hình hệ thống"],
    ["D17", "dl.pricing.ui", "TransientModel", "dl_pricing_ui (tạm)",
     "Bootstrap dữ liệu cho màn Cấu hình Báo giá — không lưu field nào"],
    ["D18", "res.users", "Mở rộng", "res_users (native)",
     "Thêm người duyệt dự phòng"],

    ("GROUP", "MODULE E — dl_technical 17.0.1.2.0   ·   depends: dl_base, dl_product, dl_partner, uom, dl_config"),
    ["E1", "dl.quotation.request", "Model mới + mail.thread", "dl_quotation_request",
     "Yêu cầu báo giá (RFQ) — bước tiếp nhận đầu tiên, mốc đo cycle time"],
    ["E2", "dl.quotation.request.line", "Model mới", "dl_quotation_request_line",
     "1 dòng RFQ = 1 sản phẩm khách yêu cầu; KTV xác định SP thật hoặc đánh dấu bất khả thi"],
    ["E3", "dl.quotation.request.line.image", "Model mới", "dl_quotation_request_line_image",
     "Ảnh minh hoạ do Sales đính kèm cho từng dòng RFQ"],
    ["E4", "dl.drawing", "Model mới + mail.thread", "dl_drawing",
     "Bản vẽ kỹ thuật của sản phẩm, có versioning"],
    ["E5", "dl.bom.header.mixin", "AbstractModel", "— (không bảng)",
     "Trường & workflow phần đầu BOM dùng chung cho BOM thật và BOM mẫu"],
    ["E6", "dl.bom.line.mixin", "AbstractModel", "— (không bảng)",
     "Trường & logic tính định mức dùng chung cho dòng BOM thật và dòng BOM mẫu"],
    ["E7", "dl.bom", "Model mới + mail.thread", "dl_bom",
     "BOM — model TỰ ĐỊNH NGHĨA, không kế thừa mrp.bom"],
    ["E8", "dl.bom.line", "Model mới", "dl_bom_line",
     "Dòng vật tư trong BOM, có snapshot đơn giá và giá trị thu hồi"],
    ["E9", "dl.bom.template", "Model mới + mail.thread", "dl_bom_template",
     "BOM mẫu tái sử dụng theo nhóm sản phẩm"],
    ["E10", "dl.bom.template.line", "Model mới", "dl_bom_template_line",
     "Dòng gợi ý trong BOM mẫu"],
    ["E11", "product.category", "Mở rộng", "product_category (native)",
     "Thêm bom_template_id — khai ở đây để giữ đúng chiều phụ thuộc module"],
    ["E12", "product.product", "Mở rộng", "product_product (native)",
     "Thêm bom_ids (computed, không lưu)"],
    ["E13", "dl.measurement.shape", "Mở rộng", "dl_measurement_shape",
     "Thêm ràng buộc: code phải nằm trong tập công thức đã cài đặt"],
    ["E14", "dl.bom.from.template.wizard", "TransientModel", "dl_bom_from_template_wizard",
     "Wizard tạo BOM từ BOM mẫu"],
    ["E15", "dl.rfq.resolve.wizard", "TransientModel", "dl_rfq_resolve_wizard",
     "Wizard xử lý 1 dòng RFQ — chọn/tạo Product và BOM"],
    ["E16", "dl.rfq.return.wizard", "TransientModel", "dl_rfq_return_wizard",
     "Wizard trả RFQ về Sales để bổ sung thông tin"],
    ["E17", "dl.rfq.history.wizard", "TransientModel", "dl_rfq_history_wizard",
     "Wizard xem lịch sử xử lý RFQ"],

    ("GROUP", "MODULE F — dl_sale 17.0.1.6.0   ·   depends: dl_partner, dl_product, dl_technical, dl_base, mail"),
    ["F1", "dl.quotation", "Model mới + mail.thread", "dl_quotation",
     "BÁO GIÁ — entity trung tâm, tổng hợp giá trị và trạng thái phê duyệt"],
    ["F2", "dl.quotation.line", "Model mới", "dl_quotation_line",
     "Dòng hạng mục trong báo giá"],
    ["F3", "dl.quotation.price.component", "Model mới", "dl_quotation_price_component",
     "Cấu phần giá dạng SNAPSHOT — ghi lại từng thành phần đã dùng để ra giá"],
    ["F4", "dl.sale.order", "Model mới + mail.thread", "dl_sale_order",
     "Đơn bán hàng, sinh từ báo giá đã được khách chấp nhận"],
    ["F5", "dl.sale.order.line", "Model mới", "dl_sale_order_line",
     "Dòng chi tiết đơn bán hàng"],
    ["F6", "dl.quotation.pricing.service", "AbstractModel", "— (không bảng)",
     "Dịch vụ tính giá — chỉ chứa logic, không khai field nào"],
    ["F7", "dl.pricing.approval.request", "Mở rộng", "dl_pricing_approval_request",
     "Nối yêu cầu duyệt với báo giá + ~20 field related để hiển thị"],
    ["F8", "dl.quotation.request", "Mở rộng", "dl_quotation_request",
     "Thêm quotation_id (computed, không lưu)"],
    ["F9", "res.partner", "Mở rộng", "res_partner (native)",
     "Thêm thống kê báo giá của khách + nhóm khách hàng"],

    ("GROUP", "MODULE G — dl_inventory 17.0.1.0.0   ·   depends: dl_base, dl_product, dl_partner, stock"),
    ["G0", "— (chưa có model)", "—", "—",
     "Module đã khai báo và cài được nhưng models/__init__.py rỗng, "
     "views/menus/ACL đều rỗng — placeholder cho giai đoạn Kho, chưa đóng góp entity nào"],
]
