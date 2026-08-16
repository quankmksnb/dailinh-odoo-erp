# -*- coding: utf-8 -*-
"""§3.1 Entity Definitions — modules E (dl_technical), F (dl_sale), G (dl_inventory)."""

HDR_MIXIN_NOTE = (
    "+ 3 cột vật chất hoá từ mixin E5: version (INTEGER, NOT NULL, DEFAULT 1), "
    "product_qty (NUMERIC, NOT NULL, DEFAULT 1.0), status (VARCHAR, DEFAULT 'draft', "
    "Enum §3.3, copy=False)."
)

LINE_MIXIN_NOTE = (
    "+ 20 cột vật chất hoá từ mixin E6 (xem E6): material_id, measurement_type_id, "
    "measurement_shape_id, measurement_coefficient, dim_length, dim_width, dim_thickness, "
    "dim_side, dim_diameter, dim_height, quantity, complexity_id, waste_rate, effective_qty, "
    "is_override, override_reason, uom_id."
)

MODULE_E = {
    "title": "E. Module dl_technical — RFQ, bản vẽ, BOM",
    "lead": "Module kỹ thuật: tiếp nhận yêu cầu báo giá, quản lý bản vẽ và dựng BOM. "
            "Điểm khác biệt lớn nhất so với thiết kế trước: dl.bom và dl.bom.line là MODEL TỰ "
            "ĐỊNH NGHĨA (bảng dl_bom / dl_bom_line), KHÔNG kế thừa mrp.bom / mrp.bom.line — "
            "dự án không cài module mrp. Hai mixin trừu tượng (E5, E6) cho phép BOM thật và BOM "
            "mẫu dùng chung khai báo trường mà vẫn nằm ở 2 bảng riêng.",
    "entities": [
        {
            "head": "E1. dl.quotation.request [Model mới + mail.thread]",
            "desc": "YÊU CẦU BÁO GIÁ (RFQ) — bước tiếp nhận đầu tiên trước khi có BOM. requested_date "
                    "là mốc đo cycle time. Tách khỏi dl.quotation để RFQ không thành báo giá vẫn "
                    "không làm sai win-rate.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin']   ·   _order = 'id desc'   ·   "
                    "_sql_constraints: name_uniq = unique(name)\n"
                    "Mã sinh từ ir.sequence 'dl.quotation.request', prefix RFQ-%(year)s-.",
            "cols": [
                ["name", "VARCHAR", "NOT NULL, UNIQUE", "Mã yêu cầu; readonly, copy=False"],
                ["customer_id", "INTEGER", "NOT NULL", "FK → res_partner, domain partner_role ∈ (customer, both)"],
                ["description", "TEXT", "nullable", "Mô tả yêu cầu"],
                ["requested_date", "TIMESTAMP", "NOT NULL", "Ngày nhận yêu cầu — mốc đo cycle time"],
                ["deadline", "DATE", "nullable", "Hạn khách yêu cầu"],
                ["status", "VARCHAR", "DEFAULT 'new'", "Enum §3.3 — 7 trạng thái; readonly, copy=False"],
                ["return_reason", "TEXT", "nullable", "Lý do trả lại cho Sales bổ sung; copy=False"],
                ["created_by", "INTEGER", "nullable", "FK → res_users — người tạo (field nghiệp vụ, khác create_uid)"],
                ["note", "TEXT", "nullable", "Ghi chú"],
                ["line_ids", "—", "—", "One2many → dl_quotation_request_line, không sinh cột"],
                ["manufactured_line_ids, trading_line_ids", "—", "—", "One2many cùng bảng, khác domain — không sinh cột"],
                ["resolved_product_ids, resolved_bom_ids", "—", "—", "Many2many compute, store=False → KHÔNG sinh bảng nối"],
                ["is_technician", "—", "—", "compute, store=False → KHÔNG sinh cột"],
                ["quotation_id", "—", "—", "Khai ở dl_sale; compute, store=False → KHÔNG sinh cột"],
            ],
            "extra": "Ràng buộc: _check_deadline (deadline không sớm hơn requested_date).",
        },
        {
            "head": "E2. dl.quotation.request.line [Model mới]",
            "desc": "1 dòng RFQ = 1 sản phẩm khách yêu cầu. Kỹ thuật viên xử lý từng dòng: chọn/tạo "
                    "sản phẩm thật (resolved_product_id) HOẶC đánh dấu không khả thi "
                    "(is_infeasible) — hai việc loại trừ nhau.",
            "meta": "_order = 'id'",
            "cols": [
                ["quotation_request_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_quotation_request (E1)"],
                ["product_type", "VARCHAR", "NOT NULL, DEFAULT 'manufactured'", "Enum §3.3 — manufactured / trading"],
                ["product_name", "VARCHAR", "nullable", "Tên sản phẩm khách mô tả"],
                ["product_category_id", "INTEGER", "nullable", "FK → product_category, domain dl_branch = 'finished' và có nhóm cha"],
                ["reference_product_id", "INTEGER", "nullable", "FK → product_product — SP tham khảo Sales gợi ý"],
                ["quantity", "NUMERIC", "NOT NULL, DEFAULT 1.0", "Số lượng khách yêu cầu"],
                ["dimension_note", "TEXT", "nullable", "Kích thước / yêu cầu riêng của dòng"],
                ["resolved_product_id", "INTEGER", "nullable", "FK → product_product — SP thật do KTV xác định/tạo"],
                ["resolved_bom_id", "INTEGER", "nullable", "FK → dl_bom (E7) — BOM tham chiếu"],
                ["is_infeasible", "BOOLEAN", "DEFAULT FALSE", "KTV đánh dấu không sản xuất được"],
                ["infeasible_reason", "TEXT", "nullable", "Bắt buộc nhập khi is_infeasible (ràng buộc Python)"],
                ["attachment_ids", "— (bảng nối)", "—", "Many2many → ir_attachment; Odoo sinh bảng nối riêng"],
                ["image_ids", "—", "—", "One2many → dl_quotation_request_line_image (E3), không sinh cột"],
                ["currency_id, product_price", "—", "—", "related qua resolved_product_id, store=False → KHÔNG sinh cột"],
                ["image_count, preview_image, price_subtotal, resolvable_product_ids, "
                 "selectable_category_ids, reference_product_ids, is_technician",
                 "—", "—", "compute, store=False → KHÔNG sinh cột / bảng nối"],
            ],
            "extra": "Ràng buộc: _check_quantity; _check_resolved_bom; _check_product_type_required; "
                     "_check_resolution (resolved_product_id và is_infeasible loại trừ nhau); "
                     "_check_infeasible_reason; _check_product_has_bom (SP xác định phải có BOM hợp lệ).",
        },
        {
            "head": "E3. dl.quotation.request.line.image [Model mới]",
            "desc": "Ảnh minh hoạ Sales đính kèm cho từng dòng RFQ.",
            "meta": "_order = 'sequence, id'",
            "cols": [
                ["line_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_quotation_request_line (E2)"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự ảnh"],
                ["name", "VARCHAR", "nullable", "Mô tả ảnh"],
                ["image", "— (ir_attachment)", "NOT NULL", "fields.Image, attachment=True → nội dung nằm ở ir_attachment + filestore, KHÔNG sinh cột"],
            ],
        },
        {
            "head": "E4. dl.drawing [Model mới + mail.thread]",
            "desc": "Bản vẽ kỹ thuật của sản phẩm, có versioning. File thật nằm ở ir.attachment.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin']   ·   _order = 'drawing_code'   ·   "
                    "_sql_constraints: drawing_code_uniq = unique(drawing_code); "
                    "product_version_uniq = unique(product_id, version)\n"
                    "Mã sinh từ ir.sequence 'dl.drawing', prefix DW-.",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên bản vẽ"],
                ["product_id", "INTEGER", "NOT NULL", "FK → product_product"],
                ["drawing_code", "VARCHAR", "NOT NULL, UNIQUE", "Mã bản vẽ; copy=False"],
                ["version", "INTEGER", "NOT NULL, DEFAULT 1", "Phiên bản — UNIQUE cùng product_id"],
                ["status", "VARCHAR", "DEFAULT 'draft'", "Enum §3.3 — draft / confirmed / archived; copy=False"],
                ["attachment_id", "INTEGER", "nullable", "FK → ir_attachment — file bản vẽ"],
                ["confirmed_date", "DATE", "nullable", "Ngày xác nhận; readonly"],
                ["created_by", "INTEGER", "NOT NULL", "FK → res_users; readonly"],
            ],
        },
        {
            "head": "E5. dl.bom.header.mixin [AbstractModel — không có bảng]",
            "desc": "Trường & workflow phần ĐẦU BOM dùng chung cho BOM thật (E7) và BOM mẫu (E9). "
                    "3 field bên dưới được vật chất hoá thành cột trong CẢ HAI bảng dl_bom và "
                    "dl_bom_template.",
            "cols": [
                ["version", "INTEGER", "NOT NULL, DEFAULT 1", "Phiên bản BOM"],
                ["product_qty", "NUMERIC", "NOT NULL, DEFAULT 1.0", "Số lượng đầu ra"],
                ["status", "VARCHAR", "DEFAULT 'draft'", "Enum §3.3 — draft / confirmed / locked / archived; copy=False"],
            ],
        },
        {
            "head": "E6. dl.bom.line.mixin [AbstractModel — không có bảng]",
            "desc": "Trường & logic tính ĐỊNH MỨC dùng chung cho dòng BOM thật (E8) và dòng BOM mẫu "
                    "(E10). Đây là nơi hệ đo lường (C4–C6) gặp vật tư: chọn Rule + Shape rồi nhập "
                    "kích thước, hệ thống tính ra định mức.",
            "cols": [
                ["material_id", "INTEGER", "NOT NULL", "FK → product_product, domain product_kind ∈ (material, material_processed)"],
                ["measurement_type_id", "INTEGER", "nullable", "FK → dl_measurement_type (C4) — Rule"],
                ["measurement_shape_id", "INTEGER", "nullable", "FK → dl_measurement_shape (C5) — Shape, lọc theo Rule"],
                ["measurement_coefficient", "NUMERIC(16,4)", "nullable", "Hệ số áp cho dòng này (mặc định lấy từ Shape)"],
                ["dim_length, dim_width, dim_thickness, dim_side, dim_diameter, dim_height",
                 "NUMERIC(16,3)", "nullable", "Kích thước (mm) — công thức đọc theo code tham số của Shape"],
                ["quantity", "NUMERIC", "NOT NULL, DEFAULT 1.0", "Số lượng"],
                ["complexity_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → dl_pricing_complexity_level (D9)"],
                ["waste_rate", "NUMERIC(5,2)", "DEFAULT 0.0", "Tỷ lệ hao hụt (%) = dlm_waste_rate của vật tư × hệ số phức tạp"],
                ["effective_qty", "NUMERIC", "nullable", "compute, store=True → CÓ cột. Số lượng thực tế sau hao hụt"],
                ["is_override", "BOOLEAN", "DEFAULT FALSE", "Ghi đè số lượng hệ thống tính"],
                ["override_reason", "TEXT", "nullable", "Bắt buộc khi is_override"],
                ["uom_id", "INTEGER", "nullable", "FK → uom_uom. compute, store=True → CÓ cột"],
                ["computed_quantity, rule_applicable, shape_code, material_uom_category_id, "
                 "shape_coefficient_label", "—", "—", "compute / related, store=False → KHÔNG sinh cột"],
            ],
            "extra": "Ràng buộc: _check_quantity; _check_waste_rate; _check_override_reason.",
        },
        {
            "head": "E7. dl.bom [Model mới + mail.thread]",
            "desc": "BOM — danh sách vật tư để làm ra 1 sản phẩm. Dùng chung cho SP gia công và bán "
                    "thành phẩm (cả hai đều nằm trong product_product nên product_id trỏ về đúng 1 bảng).",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin', 'dl.bom.header.mixin']   ·   "
                    "_order = 'id desc'   ·   _sql_constraints: product_version_type_uniq = "
                    "unique(product_id, version, bom_type)\n"
                    "Mã sinh từ ir.sequence 'dl.bom', prefix BOM-.",
            "note": ("Khác biệt so với thiết kế trước",
                     "Tài liệu bản cũ ghi B2 kế thừa mrp.bom. Trong mã nguồn hiện tại dl.bom là "
                     "model ĐỘC LẬP (_name = 'dl.bom'), không kế thừa mrp.bom — dự án không khai "
                     "depends 'mrp' ở bất kỳ module nào."),
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Mã BOM; copy=False"],
                ["product_id", "INTEGER", "NOT NULL, ON DELETE RESTRICT", "FK → product_product, domain product_kind ∈ (manufactured, material_processed)"],
                ["category_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → product_category — chỉ dùng để LỌC sản phẩm khi chọn"],
                ["bom_type", "VARCHAR", "NOT NULL, DEFAULT 'template'", "Enum §3.3 — template / quotation"],
                ["total_material_cost", "NUMERIC", "nullable", "compute, store=True → CÓ cột. Tổng chi phí vật tư"],
                ["note", "TEXT", "nullable", "Ghi chú"],
                ["line_ids", "—", "—", "One2many → dl_bom_line (E8), copy=True; không sinh cột"],
                ["drawing_id, drawing_attachment_id, drawing_mimetype, drawing_filename, "
                 "show_back_to_rfq", "—", "—", "compute, store=False → KHÔNG sinh cột"],
                [HDR_MIXIN_NOTE, "", "", ""],
            ],
            "extra": "Ràng buộc: _check_product_qty.",
        },
        {
            "head": "E8. dl.bom.line [Model mới]",
            "desc": "Dòng vật tư trong BOM. price_snapshot CHỐT đơn giá tại thời điểm tính — lấy từ "
                    "bảng giá NCC (C3) có is_applied = TRUE, hoặc tính đệ quy nếu vật tư là bán "
                    "thành phẩm có BOM riêng.",
            "meta": "_inherit = ['dl.bom.line.mixin']   ·   _order = 'id'",
            "cols": [
                ["bom_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_bom (E7)"],
                ["price_snapshot", "NUMERIC", "nullable", "compute, store=True → CÓ cột. Đơn giá đã chốt; readonly"],
                ["recovery_value", "NUMERIC", "nullable", "compute, store=True → CÓ cột. Giá trị thu hồi phế liệu"],
                ["subtotal", "NUMERIC", "nullable", "compute, store=True → CÓ cột. Thành tiền"],
                ["drawing_attachment_id, drawing_mimetype, drawing_filename", "—", "—",
                 "related qua bom_id, store=False → KHÔNG sinh cột"],
                [LINE_MIXIN_NOTE, "", "", ""],
            ],
        },
        {
            "head": "E9. dl.bom.template [Model mới + mail.thread]",
            "desc": "BOM MẪU tái sử dụng theo nhóm sản phẩm. Độc lập với BOM thật — KTV áp mẫu lên 1 "
                    "BOM mới để pre-fill danh sách vật tư rồi chỉnh lại.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin', 'dl.bom.header.mixin']   ·   "
                    "_order = 'name'   ·   _sql_constraints: category_version_uniq = "
                    "unique(product_category_id, version)",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên BOM mẫu"],
                ["product_category_id", "INTEGER", "NOT NULL, ON DELETE RESTRICT", "FK → product_category, domain dl_branch ∈ (finished, material)"],
                ["line_ids", "—", "—", "One2many → dl_bom_template_line (E10), copy=True; không sinh cột"],
                [HDR_MIXIN_NOTE, "", "", ""],
            ],
        },
        {
            "head": "E10. dl.bom.template.line [Model mới]",
            "desc": "Dòng gợi ý trong BOM mẫu. Dùng chung mixin dòng BOM (E6) nên cấu trúc kích thước / "
                    "định mức giống hệt dòng BOM thật, nhưng KHÔNG có các cột giá.",
            "meta": "_inherit = ['dl.bom.line.mixin']   ·   _order = 'id'",
            "cols": [
                ["bom_template_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_bom_template (E9)"],
                ["note", "VARCHAR", "nullable", "Ghi chú dòng mẫu"],
                [LINE_MIXIN_NOTE, "", "", ""],
            ],
        },
        {
            "head": "E11–E13. Các lượt mở rộng model của module khác",
            "desc": "dl_technical bổ sung field/ràng buộc vào 3 model đã tồn tại, theo đúng chiều "
                    "phụ thuộc (module trên bổ sung cho module dưới, không ngược lại).",
            "cols": [
                ["product.category . bom_template_id", "INTEGER", "nullable, ON DELETE SET NULL",
                 "E11 — FK → dl_bom_template (E9). Khai ở đây vì dl_product KHÔNG được depends dl_technical"],
                ["product.product . bom_ids", "—", "—",
                 "E12 — One2many computed → KHÔNG sinh cột. Cũng bổ sung onchange tự điền dlm_waste_rate "
                 "từ dl.pricing.waste.rule (D8) khi chọn nhóm cho vật tư"],
                ["dl.measurement.shape . (ràng buộc)", "—", "—",
                 "E13 — thêm _check_code_known: code phải nằm trong tập công thức hard-code đã cài đặt"],
            ],
        },
        {
            "head": "E14–E17. Wizard [TransientModel]",
            "desc": "4 model tạm phục vụ thao tác trên UI. Có bảng vật lý nhưng bản ghi bị "
                    "ir.autovacuum dọn định kỳ — không tính là dữ liệu nghiệp vụ.",
            "cols": [
                ["dl.bom.from.template.wizard", "dl_bom_from_template_wizard", "—",
                 "E14 — bom_id (FK dl_bom), template_id (FK dl_bom_template)"],
                ["dl.rfq.resolve.wizard", "dl_rfq_resolve_wizard", "—",
                 "E15 — rfq_line_id (FK), mode (Enum existing/new), product_id, new_product_name, "
                 "new_product_category_id, selected_bom_id, is_infeasible, infeasible_reason"],
                ["dl.rfq.return.wizard", "dl_rfq_return_wizard", "—",
                 "E16 — request_id (FK dl_quotation_request), reason (TEXT, NOT NULL)"],
                ["dl.rfq.history.wizard", "dl_rfq_history_wizard", "—",
                 "E17 — request_id (FK), history_html (compute, không lưu)"],
            ],
        },
    ],
}

MODULE_F = {
    "title": "F. Module dl_sale — báo giá & đơn bán hàng",
    "lead": "Module đỉnh của chuỗi phụ thuộc. Chứa báo giá, đơn bán hàng và cơ chế SNAPSHOT cấu "
            "phần giá — điểm thay thế cho entity dl.quotation.history của thiết kế cũ: thay vì "
            "chụp cả báo giá thành JSON, dự án lưu từng cấu phần giá thành bản ghi có cấu trúc "
            "kèm source_model / source_id / source_revision để truy ngược đúng tham số đã dùng.",
    "entities": [
        {
            "head": "F1. dl.quotation [Model mới + mail.thread]",
            "desc": "BÁO GIÁ — entity trung tâm. Gom giá trị từ các dòng, áp chiết khấu và VAT, "
                    "đối chiếu với chính sách lợi nhuận (D3) và ma trận phê duyệt (D10) để quyết "
                    "định có phải xin duyệt hay không.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin']   ·   "
                    "_order = 'date_order desc, id desc'\n"
                    "Số báo giá sinh từ ir.sequence 'dl.quotation', prefix BG/%(year)s/.",
            "cols": [
                ["name", "VARCHAR", "NOT NULL, DEFAULT 'New'", "Số báo giá; readonly, copy=False"],
                ["partner_id", "INTEGER", "NOT NULL", "FK → res_partner, domain partner_role ∈ (customer, both)"],
                ["date_order", "DATE", "NOT NULL", "Ngày báo giá"],
                ["state", "VARCHAR", "DEFAULT 'draft'", "Enum §3.3 — 7 trạng thái"],
                ["note", "TEXT", "nullable", "Ghi chú"],
                ["currency_id", "INTEGER", "nullable", "FK → res_currency"],
                ["company_id", "INTEGER", "nullable", "FK → res_company; readonly"],
                ["quotation_request_id", "INTEGER", "nullable, ON DELETE RESTRICT, INDEX (index=True)", "FK → dl_quotation_request (E1); copy=False"],
                ["pricing_date", "DATE", "nullable", "Ngày tính giá — mốc tra tham số cấu hình; readonly"],
                ["discount_pct, vat_pct", "NUMERIC(5,2)", "nullable", "Chiết khấu và VAT (%)"],
                ["amount_untaxed, discount_amount, amount_before_vat, vat_amount, amount_total, "
                 "total_cost, floor_amount", "NUMERIC", "nullable", "compute, store=True → CÓ cột"],
                ["effective_markup", "NUMERIC(16,2)", "nullable", "compute, store=True → CÓ cột. Markup thực (%)"],
                ["target_markup, discount_default_rate, discount_max_rate", "NUMERIC(6,2)", "nullable",
                 "Ảnh chụp tham số cấu hình tại thời điểm tính giá; readonly"],
                ["approval_required", "BOOLEAN", "nullable", "Cần phê duyệt; readonly"],
                ["approval_state", "VARCHAR", "DEFAULT 'not_required'", "Enum §3.3 — not_required / pending / approved / rejected"],
                ["approval_level", "VARCHAR", "nullable", "Cấp duyệt yêu cầu; readonly"],
                ["approval_reasons", "TEXT", "nullable", "Lý do phải duyệt; readonly"],
                ["approval_request_id", "INTEGER", "nullable", "FK → dl_pricing_approval_request (D12)"],
                ["below_floor, discount_above_default, discount_above_max", "BOOLEAN", "nullable",
                 "Cờ vi phạm ngưỡng; readonly"],
                ["line_ids, component_ids", "—", "—", "One2many → F2, F3; không sinh cột"],
                ["approval_can_resolve, sale_order_id", "—", "—", "related / compute, store=False → KHÔNG sinh cột"],
            ],
        },
        {
            "head": "F2. dl.quotation.line [Model mới]",
            "desc": "Dòng hạng mục trong báo giá. Nối ngược về dòng RFQ, sản phẩm và BOM đã dùng.",
            "cols": [
                ["quotation_id", "INTEGER", "nullable, ON DELETE CASCADE", "FK → dl_quotation (F1)"],
                ["name", "VARCHAR", "NOT NULL", "Mô tả hạng mục"],
                ["qty", "NUMERIC", "DEFAULT 1.0", "Số lượng"],
                ["price_unit", "NUMERIC", "nullable", "Đơn giá bán"],
                ["price_subtotal", "NUMERIC", "nullable", "compute, store=True → CÓ cột"],
                ["rfq_line_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → dl_quotation_request_line (E2); readonly"],
                ["product_id", "INTEGER", "nullable", "FK → product_product; readonly"],
                ["bom_id", "INTEGER", "nullable", "FK → dl_bom (E7); readonly"],
                ["line_type", "VARCHAR", "DEFAULT 'trading'", "Enum §3.3 — trading / manufactured; readonly"],
                ["base_price, material_cost, total_cost, floor_price", "NUMERIC", "nullable",
                 "Giá nền / chi phí vật tư / giá thành / giá sàn trên 1 đơn vị; readonly"],
                ["component_ids", "—", "—", "One2many → dl_quotation_price_component (F3), không sinh cột"],
            ],
        },
        {
            "head": "F3. dl.quotation.price.component [Model mới]",
            "desc": "CẤU PHẦN GIÁ dạng SNAPSHOT. Mỗi bản ghi = 1 thành phần đã cấu thành nên giá "
                    "(vật tư, thu hồi, markup, chiết khấu, VAT…). Bộ ba source_model / source_id / "
                    "source_revision cho biết bản ghi cấu hình nào, revision nào đã được dùng — "
                    "đây là cơ chế truy vết giá của hệ thống.",
            "meta": "_order = 'quotation_line_id, id'",
            "cols": [
                ["quotation_id", "INTEGER", "NOT NULL, ON DELETE CASCADE, INDEX (index=True)", "FK → dl_quotation (F1)"],
                ["quotation_line_id", "INTEGER", "nullable, ON DELETE CASCADE, INDEX (index=True)", "FK → dl_quotation_line (F2)"],
                ["component_type", "VARCHAR", "NOT NULL", "Enum §3.3 — 7 loại cấu phần"],
                ["source_model", "VARCHAR", "nullable", "Tên model nguồn — tham chiếu MỀM, KHÔNG có FK"],
                ["source_id", "INTEGER", "nullable", "ID bản ghi nguồn — KHÔNG có FK"],
                ["source_revision", "INTEGER", "nullable", "Revision của bản ghi nguồn tại thời điểm chốt"],
                ["material_id", "INTEGER", "nullable, ON DELETE SET NULL", "FK → product_product"],
                ["qty, unit_price, amount", "NUMERIC", "nullable", "Số lượng / đơn giá / thành tiền"],
                ["rate", "NUMERIC(5,2)", "nullable", "Tỷ lệ (%) nếu cấu phần tính theo %"],
                ["no_discount", "BOOLEAN", "DEFAULT FALSE", "Cấu phần không chịu chiết khấu"],
            ],
        },
        {
            "head": "F4. dl.sale.order [Model mới + mail.thread]",
            "desc": "ĐƠN BÁN HÀNG, sinh từ báo giá khách đã chấp nhận. Khi đơn được xác nhận, hệ "
                    "thống tự nâng SP gia công còn nháp lên trạng thái đã duyệt.",
            "meta": "_inherit = ['mail.thread', 'mail.activity.mixin']   ·   "
                    "_order = 'date_order desc, id desc'\n"
                    "Số đơn sinh từ ir.sequence 'dl.sale.order', prefix DH/%(year)s/.",
            "cols": [
                ["name", "VARCHAR", "NOT NULL, DEFAULT 'New'", "Số đơn; readonly, copy=False"],
                ["partner_id", "INTEGER", "NOT NULL", "FK → res_partner, domain partner_role ∈ (customer, both)"],
                ["quotation_id", "INTEGER", "nullable, ON DELETE RESTRICT, INDEX (index=True)", "FK → dl_quotation (F1); readonly, copy=False"],
                ["date_order", "DATE", "NOT NULL", "Ngày lên đơn"],
                ["state", "VARCHAR", "DEFAULT 'draft'", "Enum §3.3 — draft / confirmed / done / cancelled; copy=False"],
                ["note", "TEXT", "nullable", "Ghi chú"],
                ["currency_id", "INTEGER", "nullable", "FK → res_currency"],
                ["company_id", "INTEGER", "nullable", "FK → res_company; readonly"],
                ["discount_pct, vat_pct", "NUMERIC(5,2)", "nullable", "Chiết khấu và VAT (%)"],
                ["amount_untaxed, discount_amount, amount_before_vat, vat_amount, amount_total",
                 "NUMERIC", "nullable", "compute, store=True → CÓ cột"],
                ["line_ids", "—", "—", "One2many → dl_sale_order_line (F5), không sinh cột"],
            ],
        },
        {
            "head": "F5. dl.sale.order.line [Model mới]",
            "desc": "Dòng chi tiết đơn bán hàng.",
            "cols": [
                ["order_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_sale_order (F4)"],
                ["name", "VARCHAR", "NOT NULL", "Mô tả hạng mục"],
                ["qty", "NUMERIC", "DEFAULT 1.0", "Số lượng"],
                ["price_unit", "NUMERIC", "nullable", "Đơn giá"],
                ["price_subtotal", "NUMERIC", "nullable", "compute, store=True → CÓ cột"],
                ["product_id", "INTEGER", "nullable", "FK → product_product; readonly"],
                ["bom_id", "INTEGER", "nullable", "FK → dl_bom (E7); readonly"],
                ["line_type", "VARCHAR", "DEFAULT 'trading'", "Enum §3.3 — trading / manufactured; readonly"],
            ],
        },
        {
            "head": "F6–F9. Mixin dịch vụ và các lượt mở rộng",
            "desc": "Phần còn lại của dl_sale không tạo bảng mới.",
            "cols": [
                ["dl.quotation.pricing.service", "— (AbstractModel)", "—",
                 "F6 — dịch vụ tính giá, KHÔNG khai field nào; chỉ chứa thuật toán ghép cấu phần giá"],
                ["dl.pricing.approval.request (ext)", "dl_pricing_approval_request", "—",
                 "F7 — thêm quotation_id (compute, store=True → CÓ cột) và ~20 field related q_* "
                 "(store=False → KHÔNG sinh cột)"],
                ["dl.quotation.request (ext)", "dl_quotation_request", "—",
                 "F8 — thêm quotation_id (compute, store=False → KHÔNG sinh cột)"],
                ["res.partner (ext)", "res_partner", "—",
                 "F9 — thêm dlm_customer_group (store=True → CÓ cột) và 8 chỉ số thống kê báo giá "
                 "(store=False → KHÔNG sinh cột)"],
            ],
        },
    ],
}

MODULE_G = {
    "title": "G. Module dl_inventory — kho (placeholder)",
    "lead": "Module đã được khai báo trong __manifest__.py (depends: dl_base, dl_product, "
            "dl_partner, stock) và cài đặt được, NHƯNG hiện chưa đóng góp entity nào: "
            "models/__init__.py rỗng, views/picking_views.xml và views/menus.xml chỉ có thẻ "
            "<odoo> rỗng, ir.model.access.csv chỉ có dòng tiêu đề. Khi triển khai giai đoạn Kho, "
            "module này sẽ dùng lại các model native của Odoo (stock.picking, stock.move, "
            "stock.quant…) chứ không dự kiến tạo bảng mới — mục này giữ chỗ để cập nhật sau.",
    "entities": [],
}
