# -*- coding: utf-8 -*-
"""§3.2 Entity Relationships, §3.3 Enum / Lookup Values, §3.4 Indexing Strategy."""

# ─────────────────────────── §3.2 ───────────────────────────
REL_LEAD = (
    "Bảng dưới liệt kê MỌI quan hệ có lưu trữ giữa các model của dự án — đây là dữ liệu để vẽ "
    "ERD. Quy ước: M2O = Many2one (sinh cột FK ở bảng NGUỒN); O2M = One2many (không sinh cột, "
    "chỉ là chiều đọc ngược của một M2O); M2M = Many2many (sinh bảng nối). "
    "Các quan hệ compute/related không lưu trữ đã được lược bỏ vì không tồn tại ở tầng DB."
)

REL_HEADERS = ["Từ (model.field)", "Loại", "Tới", "ON DELETE", "Ý nghĩa"]
REL_WIDTHS = [27, 7, 24, 12, 30]

REL_ROWS = [
    ("GROUP", "A · dl_base"),
    ["dl.rbac.feature.model_id", "M2O", "ir.model", "CASCADE", "Chức năng gắn với model dữ liệu nào"],
    ["dl.rbac.feature.operation_ids", "O2M", "dl.rbac.operation", "—", "Chiều ngược của operation.feature_id"],
    ["dl.rbac.operation.feature_id", "M2O", "dl.rbac.feature", "CASCADE", "Thao tác thuộc chức năng"],
    ["dl.rbac.operation.group_id", "M2O", "res.groups", "CASCADE", "Thao tác ánh xạ sang nhóm quyền"],

    ("GROUP", "B · dl_partner"),
    ["res.partner.pending_link_partner_id", "M2O", "res.partner", "(mặc định)", "Tự tham chiếu — chờ gộp KH & NCC"],

    ("GROUP", "C · dl_product"),
    ["product.product.dlm_scrap_product_id", "M2O", "product.product", "(mặc định)", "Tự tham chiếu — sản phẩm phế liệu"],
    ["product.product.categ_id", "M2O", "product.category", "(native)", "Nhóm sản phẩm — native, bị siết bằng ràng buộc nhánh"],
    ["product.product.seller_ids", "O2M", "product.supplierinfo", "—", "Native — các bảng giá NCC của sản phẩm"],
    ["product.supplierinfo.product_tmpl_id", "M2O", "product.template", "(native)", "Native — sản phẩm được áp giá"],
    ["product.supplierinfo.partner_id", "M2O", "res.partner", "(native)", "Native — nhà cung cấp"],
    ["dl.measurement.type.formula_uom_id", "M2O", "uom.uom", "(mặc định)", "Đơn vị vật lý công thức trả về"],
    ["dl.measurement.type.shape_ids", "O2M", "dl.measurement.shape", "—", "Chiều ngược của shape.measurement_type_id"],
    ["dl.measurement.shape.measurement_type_id", "M2O", "dl.measurement.type", "CASCADE", "Hình dạng thuộc đại lượng"],
    ["dl.measurement.shape.param_ids", "O2M", "dl.measurement.shape.param", "—", "Chiều ngược của param.shape_id"],
    ["dl.measurement.shape.param.shape_id", "M2O", "dl.measurement.shape", "CASCADE", "Tham số thuộc hình dạng"],

    ("GROUP", "D · dl_config"),
    ["(mọi model kế thừa D1).company_id", "M2O", "res.company", "(mặc định)", "Quy tắc thuộc công ty nào"],
    ["dl.pricing.discount.rule / profit.rule", "—", "—", "—", "Không có FK nghiệp vụ ngoài company_id"],
    ["dl.pricing.operation.rule.operation_id", "M2O", "dl.pricing.operation", "RESTRICT", "Đơn giá thuộc công đoạn"],
    ["dl.pricing.waste.rule.category_id", "M2O", "product.category", "RESTRICT", "Quy tắc hao hụt áp theo nhóm"],
    ["dl.pricing.waste.rule.product_id", "M2O", "product.product", "RESTRICT", "Quy tắc hao hụt áp theo đúng 1 vật tư"],
    ["dl.pricing.waste.rule.scrap_product_id", "M2O", "product.product", "RESTRICT", "Sản phẩm phế mặc định"],
    ["dl.pricing.approval.matrix.currency_id", "M2O", "res.currency", "(related, store)", "Tiền tệ của mốc giá trị"],
    ["dl.pricing.approval.matrix.approver_user_id", "M2O", "res.users", "(mặc định)", "Người duyệt chỉ định"],
    ["dl.pricing.approval.matrix.revised_from_id", "M2O", "dl.pricing.approval.matrix", "SET NULL", "Tự tham chiếu — bản ghi gốc bị sửa"],
    ["dl.pricing.approval.setting.approver_user_id", "M2O", "res.users", "(mặc định)", "Người duyệt mặc định"],
    ["dl.pricing.approval.request.requester_id", "M2O", "res.users", "(mặc định)", "Người gửi yêu cầu"],
    ["dl.pricing.approval.request.resolved_by_id", "M2O", "res.users", "(mặc định)", "Người xử lý"],
    ["dl.pricing.approval.request.matrix_row_id", "M2O", "dl.pricing.approval.matrix", "RESTRICT", "Dòng ma trận đã dùng để xét"],
    ["dl.pricing.approval.request.(res_model, res_id)", "—", "(bất kỳ model)", "KHÔNG có FK",
     "Tham chiếu MỀM — chủ ý, để 1 bảng yêu cầu duyệt phục vụ nhiều loại đối tượng"],
    ["dl.pricing.config.waste_ids", "O2M", "dl.pricing.waste", "—", "Chiều ngược của waste.config_id"],
    ["dl.pricing.config.level_ids", "O2M", "dl.approval.level", "—", "Chiều ngược của level.config_id"],
    ["dl.pricing.waste.config_id", "M2O", "dl.pricing.config", "CASCADE", "Dòng hao hụt thuộc bản cấu hình"],
    ["dl.approval.level.config_id", "M2O", "dl.pricing.config", "CASCADE", "Cấp duyệt thuộc bản cấu hình"],
    ["dl.approval.level.approver_user_id / backup_user_id", "M2O", "res.users", "(mặc định)", "Người duyệt chính / dự phòng"],
    ["dl.config.audit.log.user_id", "M2O", "res.users", "(mặc định)", "Người thực hiện thay đổi"],
    ["res.users.dl_backup_approver_id", "M2O", "res.users", "(mặc định)", "Tự tham chiếu — người duyệt dự phòng"],

    ("GROUP", "E · dl_technical"),
    ["dl.quotation.request.customer_id", "M2O", "res.partner", "(mặc định)", "RFQ của khách hàng nào"],
    ["dl.quotation.request.created_by", "M2O", "res.users", "(mặc định)", "Người tiếp nhận RFQ"],
    ["dl.quotation.request.line_ids", "O2M", "dl.quotation.request.line", "—", "Chiều ngược của line.quotation_request_id"],
    ["dl.quotation.request.line.quotation_request_id", "M2O", "dl.quotation.request", "CASCADE", "Dòng thuộc RFQ"],
    ["dl.quotation.request.line.product_category_id", "M2O", "product.category", "(mặc định)", "Nhóm SP khách yêu cầu"],
    ["dl.quotation.request.line.reference_product_id", "M2O", "product.product", "(mặc định)", "SP tham khảo Sales gợi ý"],
    ["dl.quotation.request.line.resolved_product_id", "M2O", "product.product", "(mặc định)", "SP thật KTV xác định"],
    ["dl.quotation.request.line.resolved_bom_id", "M2O", "dl.bom", "(mặc định)", "BOM tham chiếu"],
    ["dl.quotation.request.line.attachment_ids", "M2M", "ir.attachment", "(bảng nối)", "File Sales đính kèm"],
    ["dl.quotation.request.line.image_ids", "O2M", "dl.quotation.request.line.image", "—", "Chiều ngược của image.line_id"],
    ["dl.quotation.request.line.image.line_id", "M2O", "dl.quotation.request.line", "CASCADE", "Ảnh thuộc dòng RFQ"],
    ["dl.drawing.product_id", "M2O", "product.product", "(mặc định)", "Bản vẽ của sản phẩm"],
    ["dl.drawing.attachment_id", "M2O", "ir.attachment", "(mặc định)", "File bản vẽ"],
    ["dl.drawing.created_by", "M2O", "res.users", "(mặc định)", "Người tạo bản vẽ"],
    ["dl.bom.product_id", "M2O", "product.product", "RESTRICT", "BOM của sản phẩm nào"],
    ["dl.bom.category_id", "M2O", "product.category", "SET NULL", "Chỉ dùng để lọc khi chọn sản phẩm"],
    ["dl.bom.line_ids", "O2M", "dl.bom.line", "—", "Chiều ngược của line.bom_id"],
    ["dl.bom.line.bom_id", "M2O", "dl.bom", "CASCADE", "Dòng thuộc BOM"],
    ["dl.bom.line.material_id", "M2O", "product.product", "(mặc định)", "Vật tư / bán thành phẩm dùng trong dòng (từ mixin E6)"],
    ["dl.bom.line.measurement_type_id", "M2O", "dl.measurement.type", "(mặc định)", "Rule đo lường (từ mixin E6)"],
    ["dl.bom.line.measurement_shape_id", "M2O", "dl.measurement.shape", "(mặc định)", "Shape đo lường (từ mixin E6)"],
    ["dl.bom.line.complexity_id", "M2O", "dl.pricing.complexity.level", "SET NULL", "Mức phức tạp (từ mixin E6)"],
    ["dl.bom.line.uom_id", "M2O", "uom.uom", "(compute, store)", "Đơn vị tính (từ mixin E6)"],
    ["dl.bom.template.product_category_id", "M2O", "product.category", "RESTRICT", "BOM mẫu áp cho nhóm sản phẩm"],
    ["dl.bom.template.line_ids", "O2M", "dl.bom.template.line", "—", "Chiều ngược của line.bom_template_id"],
    ["dl.bom.template.line.bom_template_id", "M2O", "dl.bom.template", "CASCADE", "Dòng thuộc BOM mẫu"],
    ["dl.bom.template.line.(material_id, measurement_*, complexity_id, uom_id)", "M2O", "(như dl.bom.line)", "—",
     "Cùng bộ FK vì dùng chung mixin E6"],
    ["product.category.bom_template_id", "M2O", "dl.bom.template", "SET NULL", "BOM mẫu mặc định của nhóm — khai ở dl_technical"],

    ("GROUP", "F · dl_sale"),
    ["dl.quotation.partner_id", "M2O", "res.partner", "(mặc định)", "Báo giá cho khách hàng nào"],
    ["dl.quotation.quotation_request_id", "M2O", "dl.quotation.request", "RESTRICT", "Báo giá sinh từ RFQ nào"],
    ["dl.quotation.approval_request_id", "M2O", "dl.pricing.approval.request", "(mặc định)", "Yêu cầu duyệt tương ứng"],
    ["dl.quotation.currency_id / company_id", "M2O", "res.currency / res.company", "(mặc định)", "Tiền tệ, công ty"],
    ["dl.quotation.line_ids", "O2M", "dl.quotation.line", "—", "Chiều ngược của line.quotation_id"],
    ["dl.quotation.component_ids", "O2M", "dl.quotation.price.component", "—", "Cấu phần giá cấp báo giá"],
    ["dl.quotation.line.quotation_id", "M2O", "dl.quotation", "CASCADE", "Dòng thuộc báo giá"],
    ["dl.quotation.line.rfq_line_id", "M2O", "dl.quotation.request.line", "SET NULL", "Dòng báo giá sinh từ dòng RFQ"],
    ["dl.quotation.line.product_id", "M2O", "product.product", "(mặc định)", "Sản phẩm của hạng mục"],
    ["dl.quotation.line.bom_id", "M2O", "dl.bom", "(mặc định)", "BOM đã dùng để tính giá thành"],
    ["dl.quotation.line.component_ids", "O2M", "dl.quotation.price.component", "—", "Cấu phần giá cấp dòng"],
    ["dl.quotation.price.component.quotation_id", "M2O", "dl.quotation", "CASCADE", "Cấu phần thuộc báo giá"],
    ["dl.quotation.price.component.quotation_line_id", "M2O", "dl.quotation.line", "CASCADE", "Cấu phần thuộc dòng báo giá"],
    ["dl.quotation.price.component.material_id", "M2O", "product.product", "SET NULL", "Vật tư của cấu phần"],
    ["dl.quotation.price.component.(source_model, source_id, source_revision)", "—", "(bản ghi cấu hình)", "KHÔNG có FK",
     "Tham chiếu MỀM — chủ ý, để snapshot không bị xoá theo bản ghi cấu hình gốc"],
    ["dl.sale.order.partner_id", "M2O", "res.partner", "(mặc định)", "Đơn của khách hàng nào"],
    ["dl.sale.order.quotation_id", "M2O", "dl.quotation", "RESTRICT", "Đơn sinh từ báo giá nào"],
    ["dl.sale.order.line_ids", "O2M", "dl.sale.order.line", "—", "Chiều ngược của line.order_id"],
    ["dl.sale.order.line.order_id", "M2O", "dl.sale.order", "CASCADE", "Dòng thuộc đơn"],
    ["dl.sale.order.line.product_id", "M2O", "product.product", "(mặc định)", "Sản phẩm của dòng"],
    ["dl.sale.order.line.bom_id", "M2O", "dl.bom", "(mặc định)", "BOM tương ứng"],
    ["dl.pricing.approval.request.quotation_id", "M2O", "dl.quotation", "SET NULL", "compute, store=True — khai ở dl_sale"],
    ["res.partner.dlm_quotation_ids", "O2M", "dl.quotation", "—", "Chiều ngược của quotation.partner_id"],
]

REL_NOTE = (
    "Ba tham chiếu MỀM (không có FOREIGN KEY) là quyết định thiết kế có chủ ý, không phải thiếu sót: "
    "(1) dl.pricing.approval.request.res_model + res_id — cho phép một bảng yêu cầu duyệt phục vụ "
    "nhiều loại đối tượng khác nhau; (2) dl.quotation.price.component.source_model + source_id + "
    "source_revision — snapshot phải sống sót kể cả khi bản ghi cấu hình gốc bị đổi hoặc hết hiệu lực; "
    "(3) dl.rbac.feature.model_name — chỉ là bản sao tên kỹ thuật để tra cứu nhanh."
)

# ─────────────────────────── §3.3 ───────────────────────────
ENUM_LEAD = (
    "Mọi enum bên dưới là fields.Selection của Odoo — lưu xuống PostgreSQL dưới dạng VARCHAR, "
    "KHÔNG dùng kiểu ENUM của PostgreSQL và KHÔNG có CHECK constraint. Giá trị hợp lệ được ORM "
    "kiểm tra ở tầng ứng dụng khi ghi."
)

ENUM_HEADERS = ["Model", "Cột", "Giá trị hợp lệ", "Ghi chú"]
ENUM_WIDTHS = [24, 16, 30, 30]

ENUM_ROWS = [
    ["dl.rbac.feature", "category", "master / sales / approval / system", "Nhóm chức năng; mặc định system"],
    ["res.partner", "partner_role", "customer / supplier / both", "Phân biệt KH và NCC trên cùng bảng res_partner"],
    ["res.partner", "partner_type", "individual / company / dealer", "Mặc định individual; company bắt buộc có MST"],
    ["res.partner", "dlm_customer_group", "new / existing / loyal", "compute, store=True. Bậc gắn bó: 0 / 1 / 2 — dùng cho chính sách chiết khấu"],
    ["product.product", "product_kind", "manufactured / trading / material / material_processed",
     "4 loại nghiệp vụ trên 1 bảng. Selection CALLABLE — từng màn giới hạn danh sách qua context dl_kind_scope"],
    ["product.product", "dlm_lifecycle_state", "draft / active / obsolete", "Mặc định active; draft = SP mới tạo lúc xử lý RFQ, chưa tái sử dụng được"],
    ["product.product", "dl_categ_branch", "finished / material", "compute, KHÔNG lưu — nhánh nhóm kỳ vọng theo product_kind"],
    ["product.category", "dl_branch", "finished / material / other", "compute từ parent_path, store=True. other = nhóm hệ thống Odoo hoặc chưa gắn vào 2 gốc chuẩn"],
    ["product.supplierinfo", "approval_state", "draft / approved", "Kế toán duyệt giá NCC"],
    ["product.supplierinfo", "display_state", "draft / approved / applied", "compute, store=True. Pipeline hiển thị: Nháp → Đã duyệt → Đang áp dụng"],
    ["dl.pricing.cost.adjustment.rule, dl.pricing.operation.rule, dl.pricing.waste.rule, dl.pricing.approval.matrix",
     "state", "draft / active / expired", "Trạng thái KỸ THUẬT — không cần phê duyệt"],
    ["dl.pricing.profit.rule, dl.pricing.discount.rule", "state",
     "draft / pending / active / rejected / expired", "Trạng thái THƯƠNG MẠI — bắt buộc qua phê duyệt trước khi hiệu lực"],
    ["dl.pricing.discount.rule", "customer_group", "new / existing / loyal", "Thang bậc bắt buộc: mới ≤ cũ ≤ thân thiết"],
    ["dl.pricing.cost.adjustment.rule", "rule_type",
     "workshop_overhead / packing / shipping / small_order / urgent / complexity / contingency / other",
     "8 loại chi phí chung; mặc định workshop_overhead"],
    ["dl.pricing.cost.adjustment.rule", "method",
     "percent_direct / percent_cost / per_unit / per_batch / fixed / factor", "Cách tính giá trị"],
    ["dl.pricing.operation.rule", "method",
     "percent_material / per_kg / per_meter / per_sqm / per_unit / per_batch", "Phương pháp tính đơn giá công đoạn"],
    ["dl.pricing.waste.rule", "target_type", "category / product", "Áp theo nhóm hay theo đúng 1 vật tư"],
    ["dl.pricing.approval.matrix", "approval_level", "none / sales_manager / ceo",
     "Bậc: 0 / 1 / 2 — giá trị càng cao thì cấp duyệt không được thấp đi"],
    ["dl.pricing.approval.setting, dl.pricing.approval.request", "request_type",
     "profit_config / discount_config / quote_discount / quote_below_floor / quote_over_threshold / matrix_config",
     "6 loại yêu cầu phê duyệt"],
    ["dl.pricing.approval.setting", "approver_role", "sales_manager / ceo", "Vai trò duyệt; ánh xạ sang group dl_base"],
    ["dl.pricing.approval.request", "approval_level", "sales_manager / ceo", "Cấp duyệt đã xác định; readonly"],
    ["dl.pricing.approval.request", "state", "pending / approved / rejected / cancelled", "Mặc định pending; readonly, có index"],
    ["dl.approval.level", "approver_role", "none / sales_manager / ceo / custom", "Vai trò duyệt của cấp (màn Cấu hình)"],
    ["dl.approval.level", "mode", "sequential / parallel / direct / none", "Cách chạy của cấp duyệt"],
    ["dl.quotation.request", "status",
     "new / processing / returned / supplemented / confirmed / quoted / cancelled",
     "7 trạng thái. returned / supplemented là 2 trạng thái BỔ SUNG so với thiết kế cũ (trả về cho Sales bổ sung thông tin)"],
    ["dl.quotation.request.line", "product_type", "manufactured / trading", "Quyết định dòng đi qua BOM hay bán thẳng"],
    ["dl.drawing", "status", "draft / confirmed / archived", "Chỉ bản vẽ confirmed mới tham chiếu được trong BOM"],
    ["dl.bom, dl.bom.template", "status", "draft / confirmed / locked / archived",
     "Từ mixin dl.bom.header.mixin. locked = sửa phải tạo version mới"],
    ["dl.bom", "bom_type", "template / quotation", "template = mẫu tái sử dụng; quotation = bản riêng cho 1 báo giá"],
    ["dl.quotation", "state", "draft / approved / sent / accepted / ordered / rejected / cancelled",
     "7 trạng thái. ordered = đã lên đơn bán hàng"],
    ["dl.quotation", "approval_state", "not_required / pending / approved / rejected",
     "Tách RIÊNG khỏi state — báo giá có thể ở draft mà vẫn đang chờ duyệt"],
    ["dl.quotation.line, dl.sale.order.line", "line_type", "trading / manufactured", "Quyết định cách tính giá của dòng"],
    ["dl.quotation.price.component", "component_type",
     "trading_base / material / processed_material / recovery / markup / discount / vat",
     "7 loại cấu phần cấu thành nên giá"],
    ["dl.sale.order", "state", "draft / confirmed / done / cancelled", "Vòng đời đơn bán hàng"],
    ["dl.rfq.resolve.wizard", "mode", "existing / new", "Chọn SP có sẵn hay tạo SP mới khi xử lý dòng RFQ"],
]

# ─────────────────────────── §3.4 ───────────────────────────
IDX_LEAD = (
    "Odoo tự tạo BTREE index cho khoá chính và cho MỌI cột Many2one có lưu trữ — bảng dưới chỉ "
    "liệt kê các index/ràng buộc được khai TƯỜNG MINH trong mã nguồn."
)

IDX_HEADERS = ["Bảng", "Cột", "Loại", "Khai báo trong code", "Lý do"]
IDX_WIDTHS = [23, 24, 13, 16, 24]

IDX_ROWS = [
    ("GROUP", "UNIQUE — ràng buộc thật ở tầng PostgreSQL (_sql_constraints)"),
    ["dl_rbac_feature", "code", "UNIQUE", "code_uniq", "Mã chức năng là khoá tra cứu"],
    ["dl_pricing_operation", "code", "UNIQUE", "code_uniq", "Mã công đoạn không được trùng"],
    ["dl_pricing_approval_setting", "(request_type, company_id)", "UNIQUE", "type_company_uniq",
     "Mỗi loại yêu cầu chỉ có 1 cấu hình người duyệt / công ty"],
    ["dl_quotation_request", "name", "UNIQUE", "name_uniq", "Mã RFQ là định danh nghiệp vụ"],
    ["dl_drawing", "drawing_code", "UNIQUE", "drawing_code_uniq", "Mã bản vẽ là định danh nghiệp vụ"],
    ["dl_drawing", "(product_id, version)", "UNIQUE", "product_version_uniq", "Mỗi sản phẩm chỉ có 1 bản vẽ cho mỗi phiên bản"],
    ["dl_bom", "(product_id, version, bom_type)", "UNIQUE", "product_version_type_uniq", "Chặn trùng phiên bản BOM của cùng sản phẩm"],
    ["dl_bom_template", "(product_category_id, version)", "UNIQUE", "category_version_uniq", "Chặn trùng phiên bản BOM mẫu của cùng nhóm"],

    ("GROUP", "BTREE — khai tường minh bằng index=True"),
    ["res_partner", "dlm_code", "BTREE", "index=True", "Tra cứu và lọc khách hàng theo mã KH"],
    ["dl_pricing_approval_request", "state", "BTREE", "index=True", "Lọc hàng đợi yêu cầu đang chờ duyệt"],
    ["dl_pricing_approval_request", "company_id", "BTREE", "index=True", "Tách dữ liệu theo công ty"],
    ["dl_pricing_approval_setting", "company_id", "BTREE", "index=True", "Tách dữ liệu theo công ty"],
    ["dl_pricing_profit_rule, dl_pricing_discount_rule, dl_pricing_cost_adjustment_rule, "
     "dl_pricing_operation_rule, dl_pricing_waste_rule, dl_pricing_approval_matrix",
     "state", "BTREE", "index=True", "Mọi truy vấn tra tham số đều lọc state = 'active'"],
    ["(mọi bảng kế thừa dl.pricing.rule.mixin)", "company_id", "BTREE", "index=True (khai ở mixin D1)",
     "Vật chất hoá vào cả 6 bảng quy tắc"],
    ["dl_quotation", "quotation_request_id", "BTREE", "index=True", "Truy ngược từ RFQ sang báo giá"],
    ["dl_sale_order", "quotation_id", "BTREE", "index=True", "Truy ngược từ báo giá sang đơn"],
    ["dl_quotation_price_component", "quotation_id", "BTREE", "index=True", "Đọc toàn bộ cấu phần giá của 1 báo giá"],
    ["dl_quotation_price_component", "quotation_line_id", "BTREE", "index=True", "Đọc cấu phần giá theo từng dòng"],
]

IDX_NOTE_LABEL = "Cảnh báo: các quy tắc duy nhất KHÔNG được DB bảo đảm"
IDX_NOTE = (
    "Một số ràng buộc duy nhất chỉ được kiểm ở tầng Python bằng @api.constrains + search(), "
    "KHÔNG có UNIQUE INDEX tương ứng trong PostgreSQL — nghĩa là ghi thẳng vào DB hoặc ghi đồng "
    "thời từ 2 tiến trình vẫn có thể tạo ra dữ liệu vi phạm:\n"
    "• product.product.default_code — duy nhất + khớp ^[A-Z0-9\\-]+$ (_check_default_code)\n"
    "• product.supplierinfo.is_applied — tối đa 1 dòng đang áp dụng cho mỗi product_tmpl_id "
    "(_check_is_applied)\n"
    "• product.supplierinfo.price > 0 (_check_price_positive)\n"
    "• dl.pricing.approval.matrix.value_from — không trùng mốc trong cùng công ty "
    "(_check_unique_threshold)\n"
    "• res.partner.vat — duy nhất trừ khi dlm_allow_dup_tax (_check_unique_tax_code)"
)
