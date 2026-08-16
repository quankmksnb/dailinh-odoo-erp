# -*- coding: utf-8 -*-
"""§3.3 Enum/Lookup · §3.4 Indexing · §3.5 Migration · §3.6 Seed Data.

Mọi giá trị Selection dưới đây trích từ AST source (.tmp_tds/cons_src.json),
không chép tay từ giao diện.
"""

G = lambda t: ("GROUP", t)          # noqa: E731 — hàng gộp nhóm trong bảng

# ══════════════════════════ §3.3 Enum / Lookup Values ════════════════════════

ENUM_LEAD = (
    "Every value below comes from a Selection field in the source, not from the screens. A "
    "Selection is stored as VARCHAR in PostgreSQL — Odoo does not create a native ENUM type and "
    "does not add a CHECK constraint, so the allowed list is enforced by the ORM on write, not "
    "by the database. Columns marked [Native] belong to Odoo core and are listed only because a "
    "business rule in this document branches on them."
)

ENUM_HEADERS = ["Table / Mixin", "Column", "Allowed Values", "Notes"]
ENUM_WIDTHS = [24, 20, 30, 26]

ENUM_ROWS = [
    G("Group A — Partners · Users · Access Control"),
    ["res_partner", "partner_role", "customer / supplier / both",
     "Phân biệt Khách hàng và Nhà cung cấp TRÊN CÙNG một bảng. Là cột mà mọi ir.rule tách hai "
     "nhóm màn hình dựa vào."],
    ["res_partner", "partner_type", "individual / company / dealer",
     "Mặc định individual. 'company' bắt buộc có Mã số thuế."],
    ["res_partner", "dlm_customer_group", "new / existing / loyal",
     "Bậc gắn bó, tự suy từ doanh số so với ngưỡng trong ir.config_parameter (mặc định 150 "
     "triệu ₫). Dùng cho chiết khấu tự động."],
    ["dl_rbac_feature", "category", "master / sales / approval / system",
     "Mặc định system. Nhóm chức năng trên ma trận phân quyền."],

    G("Group B — Product & Material Catalogue"),
    ["product_product", "product_kind",
     "manufactured / trading / material / material_processed",
     "Bốn loại mặt hàng nghiệp vụ trên MỘT bảng — thay cho thiết kế tách bảng cũ. Mặc định "
     "manufactured."],
    ["product_product", "dlm_lifecycle_state", "draft / active / obsolete",
     "Mặc định active. draft = sản phẩm tạm sinh trong lúc xử lý RFQ; obsolete thì không lập "
     "BOM mới được."],
    ["product_product", "dl_categ_branch", "finished / material",
     "Nhánh của nhóm sản phẩm, dùng để chặn gán chéo nhánh."],
    ["product_product", "dlm_supplier_price_state",
     "none / pending / applied",
     "Chưa có giá NCC / có giá chưa áp dụng / đã áp dụng. Compute — không nhập tay."],
    ["product_product", "dlm_calc_kind",
     "cut_length / sheet / count / bulk",
     "Cách tính định mức: cắt đoạn · tấm · đếm · định lượng. Mặc định count."],
    ["product_product", "dlm_finish", "powder / galv / raw",
     "Hoàn thiện bề mặt: sơn tĩnh điện · mạ kẽm · để nguyên."],
    ["product_category", "dl_branch", "finished / material / other",
     "finished gồm SP gia công và SP thương mại; material gồm vật tư và bán thành phẩm."],
    ["product_supplierinfo", "approval_state", "draft / approved",
     "Mặc định draft. Mua hàng/Kế toán duyệt giá NCC."],
    ["product_supplierinfo", "display_state", "draft / approved / applied",
     "Trạng thái hiển thị gộp — compute, không store."],
    ["product_supplierinfo", "validity_state",
     "upcoming / active / expiring / expired",
     "Suy từ date_start/date_end so với hôm nay."],
    ["product_supplierinfo", "dl_product_kind",
     "manufactured / trading / material / material_processed",
     "Bản sao related của product_kind — để lọc bảng giá theo loại mặt hàng."],

    G("Group C — Engineering: Drawing · BOM · RFQ"),
    ["dl.bom.header.mixin", "status", "draft / confirmed / locked / archived",
     "Vòng đời dùng CHUNG cho dl_bom và dl_bom_template. Mặc định draft."],
    ["dl_bom", "bom_type", "template / quotation",
     "BOM mẫu hay BOM sinh cho một báo giá. Tham gia khoá duy nhất "
     "(product_id, version, bom_type)."],
    ["dl_bom_operation_line", "material_scope", "all / selected",
     "Công đoạn tính trên toàn bộ vật tư hay chỉ vật tư đã chọn. Mặc định all."],
    ["dl_bom_operation_line", "method",
     "percent_material / per_kg / per_meter / per_sqm / per_unit / per_batch",
     "Compute KHÔNG store — đọc từ quy tắc công đoạn đang hiệu lực."],
    ["dl_bom_template_param", "dim_role",
     "length / width / height / thickness / side / none",
     "Vai trò kích thước của tham số. Mặc định none (không tự đọc)."],
    ["dl_bom_template_line_param_map", "target_field",
     "dim_length / dim_width / piece_count / quantity",
     "Ô số liệu nhận kết quả ánh xạ. Danh sách đóng — cố ý không cho công thức tự do."],
    ["dl_drawing", "status", "draft / confirmed / archived", "Mặc định draft."],
    ["dl_quotation_request", "status",
     "new / processing / returned / supplemented / confirmed / quoted / cancelled",
     "Vòng đời RFQ. Mặc định new."],
    ["dl_quotation_request", "tech_stage",
     "pending / processing / waiting_sales / done / closed",
     "Tiến độ phía Kỹ thuật, tách khỏi status của Sales."],
    ["dl_quotation_request", "deadline_state", "ok / soon / overdue",
     "Suy từ deadline so với hôm nay — compute, không store."],
    ["dl_quotation_request_line", "product_type", "manufactured / trading",
     "Mặc định manufactured. Quyết định field nào là bắt buộc trên dòng."],
    ["dl_quotation_request_line", "technical_status",
     "pending / waiting / supplemented / processing / review / done / infeasible",
     "Trạng thái xử lý kỹ thuật của TỪNG dòng."],
    ["dl_quotation_request_line", "suggestion_state", "none / suggest / auto",
     "Hệ thống có gợi ý sản phẩm sẵn có hay không."],

    G("Group D — Sales: Quotation & Sales Order"),
    ["dl_quotation", "state",
     "draft / approved / sent / revision_requested / accepted / ordered / rejected / expired / "
     "cancelled",
     "Vòng đời báo giá. Mặc định draft. Mọi chuyển trạng thái đều có guard — xem §3.1."],
    ["dl_quotation", "approval_state",
     "not_required / pending / approved / rejected",
     "Mặc định not_required. Do ma trận phê duyệt đặt theo giá trị đơn / chiết khấu / giá sàn."],
    ["dl_quotation", "reject_reason",
     "price_high / lead_time / tech_not_met / chose_competitor / other",
     "Lý do khách từ chối — dữ liệu đầu vào cho phân tích tỷ lệ thắng."],
    ["dl_quotation", "revision_request_type", "commercial / technical / terms",
     "Khách yêu cầu điều chỉnh về giá, về kỹ thuật, hay về điều khoản giao hàng."],
    ["dl_quotation", "validity_state", "ok / soon / overdue",
     "Compute từ validity_date — không store."],
    ["dl_quotation", "status_banner_level",
     "info / success / warning / danger / secondary",
     "Chỉ phục vụ hiển thị dải thông báo trên form. KHÔNG store."],
    ["dl_quotation", "discount_hint_level", "info / secondary / warning",
     "Trong khoảng / trên mặc định / vượt trần. Chỉ để hiển thị."],
    ["dl_quotation_line", "line_type", "trading / manufactured",
     "Mặc định trading."],
    ["dl_quotation_price_component", "component_type",
     "trading_base / material / processed_material / recovery / operation / overhead / "
     "margin / discount",
     "Loại thành phần giá trong ảnh chụp giá. Bắt buộc."],
    ["dl_sale_order", "state", "draft / confirmed / done / cancelled",
     "Mặc định draft."],
    ["dl_sale_order_line", "line_type", "trading / manufactured", "Mặc định trading."],

    G("Group E — Pricing Configuration & Approval"),
    ["dl.pricing.rule.mixin", "state", "draft / active / expired",
     "Quy tắc KỸ THUẬT — áp dụng ngay, không cần duyệt."],
    ["dl.pricing.commercial.mixin", "state",
     "draft / pending / active / rejected / expired",
     "Quy tắc THƯƠNG MẠI — bắt buộc qua phê duyệt trước khi có hiệu lực."],
    ["dl_pricing_waste_rule", "target_type", "category / product",
     "Áp theo nhóm vật tư hay theo đúng một vật tư. Mặc định category."],
    ["dl_pricing_operation_rule", "method",
     "percent_material / per_kg / per_meter / per_sqm / per_unit / per_batch",
     "Cách tính đơn giá công đoạn. Mặc định percent_material."],
    ["dl_pricing_cost_adjustment_rule", "rule_type",
     "workshop_overhead / packing / shipping / small_order / urgent / complexity / "
     "contingency / other",
     "Mặc định workshop_overhead. small_order và urgent bắt buộc khai điều kiện kèm theo."],
    ["dl_pricing_cost_adjustment_rule", "method",
     "percent_direct / percent_cost / per_unit / per_batch / fixed / factor",
     "Mặc định percent_direct."],
    ["dl_pricing_discount_rule", "customer_group", "new / existing / loyal",
     "Ba bậc gắn bó. Chiết khấu phải không giảm theo bậc."],
    ["dl_pricing_approval_matrix", "approval_level", "none / sales_manager / ceo",
     "Mặc định sales_manager. Cấp duyệt phải tăng theo ngưỡng giá trị."],
    ["dl_pricing_approval_setting", "request_type",
     "profit_config / discount_config / quote_discount / quote_below_floor / "
     "quote_over_threshold / matrix_config",
     "Sáu loại việc cần duyệt."],
    ["dl_pricing_approval_setting", "approver_role", "sales_manager / ceo",
     "Mặc định ceo. Ánh xạ sang group trong dl_base."],
    ["dl_pricing_approval_request", "state",
     "pending / approved / rejected / cancelled",
     "Mặc định pending. cancelled đặt tự động khi báo giá nguồn đổi khiến yêu cầu hết ý nghĩa."],
    ["dl_pricing_approval_request", "approval_level", "sales_manager / ceo",
     "Suy từ ma trận phê duyệt."],

    G("Group F — Inventory"),
    ["stock_picking", "dlm_qc_state", "none / pending / passed / has_reject",
     "Kết quả kiểm hàng. Compute và CÓ store để danh sách lọc/nhóm được."],
    ["stock_picking", "dlm_picking_kind",
     "receipt / qc / transfer / delivery / vendor_return / scrap_sale",
     "Loại chứng từ, suy từ picking_type_id.sequence_code. KHÔNG store."],
    ["stock_picking", "dlm_banner_level", "info / success / warning / danger",
     "Mức độ của dải thông báo trên form. KHÔNG store."],
    ["stock_move", "dlm_reject_reason",
     "defect / wrong_spec / wrong_item / other",
     "Lý do bị loại khi kiểm: hàng lỗi · sai quy cách · giao sai mặt hàng · khác."],
    ["dl_sale_order", "dlm_delivery_state", "nothing / partial / done",
     "Tình trạng giao của đơn. Compute và CÓ store, mặc định nothing."],
    ["dl_scrap_recovery_report", "diff_level", "short / match / over",
     "short = thu hồi ít hơn dự toán, tức giá vốn thật cao hơn giá đã báo."],
    ["stock_location", "usage [Native]",
     "view / internal / supplier / customer / production / inventory",
     "Odoo core. SQL view phế liệu dùng usage = 'customer' để nhận ra phần đã bán ra ngoài."],
    ["stock_picking_type", "code [Native]", "incoming / outgoing / internal",
     "Odoo core. Kết hợp với sequence_code (NH / KC / CK / GH / TR / BPL) để định danh loại "
     "chứng từ."],
    ["stock_picking", "state [Native]",
     "draft / waiting / confirmed / assigned / done / cancel",
     "Odoo core. Chỉ 'done' mới làm đổi tồn kho."],
]

ENUM_NOTE = (
    "Selection không sinh ENUM của PostgreSQL",
    "Odoo lưu Selection thành VARCHAR và KHÔNG tạo CHECK constraint. Hệ quả cần biết khi đọc "
    "schema: một câu UPDATE chạy thẳng trên PostgreSQL có thể ghi giá trị ngoài danh sách mà "
    "không bị chặn. Toàn bộ danh sách hợp lệ ở trên do ORM kiểm lúc ghi. Đây cũng là lý do các "
    "cột phân loại quan trọng (state, product_kind, partner_role) luôn đi kèm ràng buộc Python "
    "ở §3.1 chứ không dựa vào kiểu dữ liệu.")

# ══════════════════════════ §3.4 Indexing Strategy ═══════════════════════════

IDX_LEAD = (
    "Odoo creates a BTREE index automatically for every primary key and for EVERY stored "
    "Many2one column, so foreign-key lookups are already covered and are NOT repeated below. "
    "The table lists only what the project declares explicitly in code: UNIQUE constraints "
    "(_sql_constraints, which become real PostgreSQL constraints) and index=True columns."
)

IDX_HEADERS = ["Table", "Index Column(s)", "Type", "Declared as", "Reason"]
IDX_WIDTHS = [26, 22, 11, 15, 26]

IDX_ROWS = [
    G("UNIQUE — ràng buộc thật ở tầng PostgreSQL (_sql_constraints)"),
    ["dl_rbac_feature", "code", "UNIQUE", "code_uniq", "Mã chức năng là khoá tra cứu"],
    ["dl_pricing_operation", "code", "UNIQUE", "code_uniq", "Mã công đoạn phải duy nhất"],
    ["dl_pricing_approval_setting", "(request_type, company_id)", "UNIQUE",
     "type_company_uniq", "Mỗi loại việc chỉ có 1 cấu hình duyệt trên mỗi công ty"],
    ["dl_quotation_request", "name", "UNIQUE", "name_uniq", "Mã RFQ là khoá nghiệp vụ"],
    ["dl_drawing", "drawing_code", "UNIQUE", "drawing_code_uniq", "Mã bản vẽ là khoá nghiệp vụ"],
    ["dl_drawing", "(product_id, version)", "UNIQUE", "product_version_uniq",
     "Mỗi sản phẩm chỉ 1 bản vẽ cho mỗi phiên bản"],
    ["dl_bom", "(product_id, version, bom_type)", "UNIQUE", "product_version_type_uniq",
     "Chặn trùng phiên bản BOM của cùng sản phẩm"],
    ["dl_bom_template", "(product_category_id, version)", "UNIQUE", "category_version_uniq",
     "Chặn trùng phiên bản BOM mẫu của cùng nhóm"],
    ["dl_bom_template_param", "(bom_template_id, code)", "UNIQUE", "code_uniq",
     "Mã tham số duy nhất trong một BOM mẫu"],

    G("BTREE — khai tường minh bằng index=True"),
    ["res_partner", "dlm_code", "BTREE", "index=True", "Tra cứu và lọc khách hàng theo mã"],
    ["product_supplierinfo", "dl_product_kind", "BTREE", "index=True",
     "Lọc bảng giá NCC theo loại mặt hàng"],
    ["dl_pricing_approval_request", "state", "BTREE", "index=True",
     "Hàng đợi phê duyệt luôn lọc state = 'pending'"],
    ["dl_pricing_approval_request", "company_id", "BTREE", "index=True", "Tách dữ liệu theo công ty"],
    ["dl_pricing_approval_setting", "company_id", "BTREE", "index=True", "Tách dữ liệu theo công ty"],
    ["dl_pricing_profit_rule · dl_pricing_discount_rule · dl_pricing_cost_adjustment_rule · "
     "dl_pricing_operation_rule · dl_pricing_waste_rule · dl_pricing_approval_matrix",
     "state", "BTREE", "index=True",
     "MỌI truy vấn tra tham số của engine đều lọc state = 'active' — xem dl.pricing.rule.mixin"],
    ["dl_pricing_rule (mixin)", "company_id", "BTREE", "index=True",
     "Ràng buộc phạm vi công ty trên mọi bảng quy tắc"],
    ["dl_quotation", "quotation_request_id", "BTREE", "index=True", "Lần từ RFQ sang báo giá"],
    ["dl_quotation", "origin_quotation_id", "BTREE", "index=True",
     "Lần chuỗi phiên bản báo giá (bản mới ← bản trước)"],
    ["dl_sale_order", "quotation_id", "BTREE", "index=True", "Lần từ báo giá sang đơn hàng"],
    ["dl_quotation_price_component", "quotation_id", "BTREE", "index=True",
     "Đọc toàn bộ thành phần giá của một báo giá"],
    ["dl_quotation_price_component", "quotation_line_id", "BTREE", "index=True",
     "Đọc thành phần giá theo từng dòng"],
    ["dl_bom", "product_id", "BTREE", "index=True", "Tìm BOM theo sản phẩm"],
    ["dl_bom", "param_signature", "BTREE", "index=True",
     "Tìm lại BOM đã sinh cho cùng bộ tham số, tránh dựng trùng"],
    ["dl_bom_operation_line", "bom_id", "BTREE", "index=True", "Đọc công đoạn theo BOM"],
    ["dl_bom_template_param", "bom_template_id", "BTREE", "index=True", "Đọc tham số theo mẫu"],
    ["dl_bom_template_line_param_map", "template_line_id · bom_template_id", "BTREE",
     "index=True", "Đọc ánh xạ theo dòng và theo mẫu"],

    G("BTREE — module Kho (index=True)"),
    ["stock_picking", "dlm_sale_order_id", "BTREE", "index=True",
     "Mở đơn hàng và liệt kê phiếu giao của nó"],
    ["stock_picking", "dlm_origin_picking_id", "BTREE", "index=True",
     "Lần ngược phiếu trả NCC về phiếu kiểm đã sinh ra nó"],
    ["stock_lot", "dlm_supplier_id", "BTREE", "index=True",
     "Truy ngược hàng lỗi về nhà cung cấp đã giao"],
    ["stock_lot", "dlm_receipt_date", "BTREE", "index=True",
     "Báo cáo tuổi tồn lọc theo ngày nhập"],
]

IDX_NOTE = (
    "Những index cố ý KHÔNG tạo",
    "stock_move.dlm_qty_rejected và stock_move.dlm_reject_reason không đánh index: chúng chỉ "
    "được đọc trong ngữ cảnh MỘT phiếu đã biết, nên index sẽ tốn chi phí ghi mà không đổi kế "
    "hoạch truy vấn. stock_picking.dlm_qc_state tuy có store nhưng cũng không đánh index vì độ "
    "chọn lọc thấp (4 giá trị trên toàn bảng) — PostgreSQL sẽ bỏ qua index và quét tuần tự. "
    "dl_scrap_recovery_report là VIEW nên không thể có index riêng; hiệu năng của nó phụ thuộc "
    "index của stock_move và stock_location.parent_path.")

# ══════════════════════════ §3.5 Migration Strategy ══════════════════════════

MIG_LEAD = (
    "Template này viết cho stack Spring Boot + Flyway. Odoo KHÔNG dùng Flyway: schema được suy "
    "ra từ khai báo field trong Python và được ORM đồng bộ mỗi lần nâng cấp module. Phần dưới "
    "mô tả đúng cơ chế đang dùng, không phải cơ chế của template."
)

MIG_HEADERS = ["Setting", "Value"]
MIG_WIDTHS = [24, 76]

MIG_ROWS = [
    ["Tool", "Odoo module versioning + migration script (chuẩn OCA: pre- / post- / end-migration). "
     "Không dùng Flyway hay Liquibase."],
    ["Schema source of truth",
     "Khai báo fields.* trong Python. ORM tự CREATE TABLE / ADD COLUMN khi module được nâng cấp; "
     "không có file DDL viết tay."],
    ["Version declaration",
     "Khoá 'version' trong dl_<module>/__manifest__.py. Hiện tại: dl_base 17.0.1.9.0 · dl_config "
     "17.0.2.9.0 · dl_partner 17.0.1.0.2 · dl_product 17.0.3.5.0 · dl_technical 17.0.2.2.0 · "
     "dl_sale 17.0.1.30.0 · dl_inventory 17.0.2.8.0 · dl_demo 17.0.1.0.0."],
    ["Script location",
     "dl_<module>/migrations/<version>/post-migration.py — tên thư mục phải TRÙNG version khai "
     "trong manifest, nếu không script sẽ không chạy. Hiện có 17 script trên 5 module."],
    ["Trigger",
     "Script chỉ chạy khi version trong manifest LỚN HƠN version đang lưu ở bảng ir_module_module. "
     "Quên tăng version = script nằm im, đây là lỗi hay gặp nhất."],
    ["Policy",
     "Forward-only. Không sửa script đã chạy trên môi trường khác; muốn sửa thì tăng version và "
     "viết script mới. Không có đường rollback tự động — rollback = phục hồi từ bản sao lưu."],
    ["Dev profile",
     "odoo-bin -u dl_sale --dev=all — nạp lại model và view theo code thay đổi, không cần khởi "
     "động lại."],
    ["Prod profile",
     "odoo-bin -u dl_<module> (hoặc qua menu Apps). Migration script chạy trong CÙNG transaction "
     "với việc đồng bộ schema: script lỗi thì toàn bộ lần nâng cấp bị rollback."],
    ["Dependency order",
     "Odoo tự nâng cấp theo thứ tự depends. Nâng dl_base kéo theo mọi module phụ thuộc, nên khi "
     "đổi model dùng chung phải nâng version của cả chuỗi."],
    ["Data files",
     "File trong 'data' được nạp lại ở mỗi lần -u, TRỪ bản ghi mang noupdate=\"True\". Đây là lý "
     "do res_company._dlm_enforce_vnd() phải làm bằng hook Python chứ không bằng <record> — xem "
     "§3.1 nhóm A."],
]

MIG_NOTE = (
    "Odoo KHÔNG BAO GIỜ DROP COLUMN — hệ quả phải biết khi chấm điểm schema",
    "Khi một field bị xoá khỏi source, ORM chỉ thôi quản lý cột đó; cột vẫn nằm nguyên trong "
    "PostgreSQL với dữ liệu cũ. Đo được trên DB phát triển: dl_pricing_config theo source hiện "
    "tại có 3 field ⇒ 8 cột, nhưng bảng thật đang có 24 cột — 16 cột mồ côi từ các phiên bản "
    "trước (sla_sales_manager_hours, material_pct, margin_pct, max_discount_pct...). Hai bảng "
    "dl_pricing_waste và dl_approval_level còn tồn tại nguyên vẹn vì lý do tương tự.\n"
    "Vì vậy: ERD vật lý và §3.1 mô tả schema của một LẦN CÀI SẠCH TỪ SOURCE HIỆN TẠI, không phải "
    "ảnh chụp DB phát triển. Muốn đối chiếu 1–1 với tài liệu thì phải dropdb && createdb rồi cài "
    "lại. Dọn cột mồ côi là việc phải viết DDL tay trong post-migration.py và cố ý chưa làm ở "
    "phiên bản này — xoá cột là thao tác không lùi được.")

# ═════════════════════════════ §3.6 Seed Data ════════════════════════════════

SEED_LEAD = (
    "Seed data chia làm hai tầng. MASTER DATA tĩnh nạp bằng XML trong 'data' của từng module và "
    "đi theo mọi lần cài — đây là dữ liệu hệ thống không chạy được nếu thiếu. DỮ LIỆU GIAO DỊCH "
    "demo nằm riêng ở module dl_demo và dựng bằng post_init_hook (Python) chứ không bằng XML, "
    "để mỗi bản ghi đi qua đúng state machine và đúng engine tính giá — dữ liệu nhồi thẳng bằng "
    "XML sẽ có trạng thái hợp lệ nhưng số tiền sai."
)

SEED_ACC_HEADERS = ["Account", "Permission group", "Test objective"]
SEED_ACC_WIDTHS = [22, 26, 52]
SEED_ACC_ROWS = [
    ["Sales", "dl_group_sale",
     "Tạo RFQ, lập báo giá, chỉ xem báo giá của mình"],
    ["Trưởng phòng KD", "dl_group_sales_manager",
     "Duyệt cấp 1 (require_sales_manager), xem báo giá toàn đội"],
    ["CEO", "dl_group_ceo",
     "Duyệt cấp 2 (require_ceo), cấu hình lợi nhuận / chiết khấu / ma trận duyệt"],
    ["Kỹ thuật viên", "dl_group_technician",
     "Lập và xác nhận BOM — mọi cột giá vốn / giá sàn phải bị ẩn"],
    ["Kế toán", "dl_group_accountant",
     "Cập nhật và duyệt giá NCC; KHÔNG thấy màn Sản phẩm/Vật tư"],
    ["Thủ kho", "dl_group_warehouse",
     "Nhận hàng, kiểm, cất, giao, trả NCC, bán phế liệu"],
    ["Admin", "dl_group_admin",
     "Quản trị ma trận phân quyền (dl_rbac_feature / dl_rbac_operation)"],
]

SEED_DOM_HEADERS = ["Entity", "Count", "States needed"]
SEED_DOM_WIDTHS = [30, 10, 60]
SEED_DOM_ROWS = [
    G("Master data tĩnh — nạp bằng XML, bắt buộc có"),
    ["res_currency (VNĐ)", "1", "active — bị ép làm tiền tệ công ty ở mỗi lần -u dl_base"],
    ["uom_uom", "≥ 6", "kg · m · m² · cây · tấm · cái — phủ đủ 4 giá trị dlm_calc_kind"],
    ["dl_measurement_type", "5", "Khối lượng · Diện tích · Chu vi · Thể tích · Chiều dài"],
    ["dl_measurement_shape (+ param)", "≥ 8", "Hình dạng cố định kèm tham số, nạp cùng nhau"],
    ["product_category", "≥ 4", "Ít nhất 1 nhánh 'finished' và 1 nhánh 'material'"],
    ["ir_sequence", "≥ 8", "Mã KH · 4 mã sản phẩm theo product_kind · mã RFQ · báo giá · đơn · lô"],
    ["dl_rbac_feature", "toàn bộ", "Nạp từ rbac_features.xml của 6 module — thiếu thì màn phân quyền trắng"],
    ["dl_pricing_config", "1", "1 dòng cấu hình VAT + làm tròn"],

    G("Cấu hình giá — cần cho engine chạy được"),
    ["dl_pricing_operation", "≥ 4", "Cắt · hàn · sơn · mạ"],
    ["dl_pricing_operation_rule", "≥ 4", "Mỗi công đoạn 1 quy tắc state = 'active'"],
    ["dl_pricing_waste_rule", "≥ 2", "1 theo category, 1 theo product; 1 bật has_recovery"],
    ["dl_pricing_profit_rule", "1", "state = 'active' — thiếu thì không có giá mục tiêu và giá sàn"],
    ["dl_pricing_discount_rule", "3", "new ≤ existing ≤ loyal, cả 3 ở state = 'active'"],
    ["dl_pricing_approval_matrix", "≥ 3", "none → sales_manager → ceo, ngưỡng tăng dần"],
    ["dl_pricing_approval_setting", "≥ 2", "1 cấu hình cho mỗi request_type sẽ được test"],

    G("Dữ liệu giao dịch demo — dl_demo, dựng bằng post_init_hook"),
    ["res_partner", "≥ 4", "Phủ 3 bậc dlm_customer_group (new/existing/loyal) + 1 nhà cung cấp; "
     "1 'company' có MST, 1 'individual'"],
    ["product_product", "≥ 8", "Phủ đủ 4 product_kind; ít nhất 1 sản phẩm ở lifecycle 'obsolete'"],
    ["product_supplierinfo", "≥ 4", "Phủ draft · approved · applied; 1 bảng giá đã hết hiệu lực"],
    ["dl_drawing", "≥ 2", "1 draft, 1 confirmed — cần cho luật chặn xác nhận BOM"],
    ["dl_bom (+ line, operation line)", "≥ 3", "draft · confirmed · locked; 1 BOM có bán thành phẩm lồng nhau"],
    ["dl_bom_template (+ param, map)", "≥ 1", "1 mẫu D×R×C đã confirmed, có ánh xạ tham số"],
    ["dl_quotation_request (+ line)", "≥ 7", "Phủ đủ 7 giá trị status; có dòng infeasible và dòng chờ bổ sung"],
    ["dl_quotation (+ line, component)", "≥ 6", "draft · approved · sent · accepted · rejected · expired; "
     "mỗi báo giá đã tính phải có đủ dòng price_component"],
    ["dl_pricing_approval_request", "≥ 2", "1 dưới ngưỡng tự duyệt, 1 vượt ngưỡng đang pending"],
    ["dl_sale_order (+ line)", "≥ 2", "1 sinh từ báo giá đã accepted, 1 đơn bán trực tiếp"],

    G("Kho — dl_inventory"),
    ["stock_warehouse", "1", "Kho DL duy nhất, reception_steps = 'two_steps'"],
    ["stock_location", "7", "DL/NHAN (+QC, +KHO, +TRA) · DL/XUONG (+BTP, +PL) · DL/TP; "
     "dlm_no_inventory bật trên QC và TRA"],
    ["stock_picking_type", "8", "NH · KC · CK · GH · TR · BPL dùng ngay; XSX · NTP dành sẵn cho pha Sản xuất"],
    ["ir_sequence (lô)", "1", "Prefix LO/%(year)s/, padding 5"],
    ["stock_picking — nhận", "2", "1 × done (sinh lô có dlm_supplier_id); 1 × assigned đang chờ"],
    ["stock_picking — kiểm", "1", "dlm_qc_state = 'has_reject', có dòng mang dlm_qty_rejected > 0"],
    ["stock_picking — giao", "1", "Gắn dl_sale_order đã confirmed để dlm_delivery_state đổi được"],
    ["stock_move (phế liệu)", "2", "1 vào DL/XUONG/PL, 1 ra địa điểm khách — đủ cho SQL view đối chiếu"],
]

SEED_NOTE = (
    "Seed data phải nạp trên DB sạch",
    "Bố cục kho, các ir.sequence và ma trận phân quyền đều được tạo bằng XML mang id ngoại "
    "(external id). Nạp lại trên một DB đã có dữ liệu sẽ CẬP NHẬT bản ghi cũ chứ không tạo bản "
    "mới — nên một kho đã bị người dùng đổi tên tay sẽ bị ghi đè về giá trị seed. Ngược lại, bản "
    "ghi mang noupdate=\"True\" sẽ KHÔNG bị đụng tới, kể cả khi giá trị trong XML đã đổi.\n"
    "dl_demo KHÔNG được cài trên môi trường thật: không cài = database sạch kiểu production. "
    "Module này phụ thuộc cả 7 module còn lại nên nó luôn được cài sau cùng.")
