# -*- coding: utf-8 -*-
"""§3.1 Entity Definitions — modules A (dl_base), B (dl_partner), C (dl_product), D (dl_config)."""

CH = ["Cột", "Kiểu PostgreSQL", "Ràng buộc", "Ghi chú"]
CW = [24, 20, 21, 35]

MODULE_A = {
    "title": "A. Module dl_base — nền tảng & phân quyền",
    "lead": "Module gốc của hệ thống. Định nghĩa 6 nhóm quyền (res.groups) bằng data XML — "
            "dl_group_ceo, dl_group_admin, dl_group_ba, dl_group_tech, dl_group_accountant, "
            "dl_group_sales_manager — và 2 model phục vụ màn hình khai báo phân quyền. "
            "Các nhóm quyền là BẢN GHI trong bảng res_groups của Odoo, không phải model mới.",
    "entities": [
        {
            "head": "A1. dl.rbac.feature [Model mới]",
            "desc": "Danh mục CHỨC NĂNG dùng để dựng ma trận phân quyền trên UI. Mỗi bản ghi "
                    "gắn với một model dữ liệu và một nhóm chức năng.",
            "meta": "_order = 'sequence, category, name'   ·   "
                    "_sql_constraints: code_uniq = unique(code)",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên chức năng hiển thị"],
                ["code", "VARCHAR", "NOT NULL, UNIQUE", "Mã chức năng — khoá tra cứu"],
                ["model_id", "INTEGER", "nullable, ON DELETE CASCADE", "FK → ir_model"],
                ["model_name", "VARCHAR", "nullable", "related model_id.model, store=True → có cột"],
                ["category", "VARCHAR", "NOT NULL, DEFAULT 'system'", "Enum — xem §3.3"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự hiển thị"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Cờ lưu trữ chuẩn Odoo"],
                ["operation_ids", "—", "—", "One2many → dl_rbac_operation, không sinh cột"],
            ],
        },
        {
            "head": "A2. dl.rbac.operation [Model mới]",
            "desc": "THAO TÁC ĐẶC BIỆT của một chức năng (ngoài 4 quyền CRUD chuẩn), mỗi thao tác "
                    "ánh xạ sang đúng 1 nhóm quyền kỹ thuật.",
            "meta": "_order = 'feature_id, sequence, name'",
            "cols": [
                ["feature_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_rbac_feature (A1)"],
                ["name", "VARCHAR", "NOT NULL", "Tên thao tác"],
                ["code", "VARCHAR", "NOT NULL", "Mã thao tác"],
                ["sequence", "INTEGER", "DEFAULT 10", "Thứ tự"],
                ["group_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → res_groups (native Odoo)"],
            ],
        },
    ],
}

MODULE_B = {
    "title": "B. Module dl_partner — đối tác",
    "lead": "Chỉ mở rộng res.partner. KHÔNG tạo bảng mới — Khách hàng và Nhà cung cấp dùng "
            "CHUNG một bảng res_partner, phân biệt bằng partner_role. Hệ quả: quyền CRUD không "
            "tách được ở tầng ir.model.access (chung model), phải phân biệt bằng ir.rule.",
    "entities": [
        {
            "head": "B1. res.partner [Mở rộng — _inherit]",
            "desc": "ĐỐI TÁC của Công ty Đại Linh. Tận dụng toàn bộ hạ tầng địa chỉ, liên lạc, "
                    "ngôn ngữ, ảnh đại diện của Odoo. Các cột bên dưới là phần MỞ RỘNG, được "
                    "ALTER TABLE thêm vào bảng res_partner có sẵn.",
            "meta": "Native dùng lại: name, vat, phone, mobile, email, street/city/country_id, "
                    "image_1920, category_id (tags), customer_rank / supplier_rank, active, "
                    "company_id, lang.",
            "note": ("Lưu ý",
                     "partner_role KHÔNG thay thế customer_rank / supplier_rank native — 2 field "
                     "đó chỉ tự tăng sau giao dịch đã xác nhận nên vô dụng với đối tác mới. "
                     "partner_role là field nghiệp vụ, gán ngay khi tạo."),
            "cols": [
                ["partner_role", "VARCHAR", "nullable", "Enum §3.3 — customer / supplier / both"],
                ["partner_type", "VARCHAR", "DEFAULT 'individual'", "Enum §3.3 — individual / company / dealer"],
                ["dlm_code", "VARCHAR", "nullable, INDEX (index=True)", "Mã KH, sinh từ ir.sequence 'dlm.customer' (prefix KH-); readonly, copy=False"],
                ["pending_link_partner_id", "INTEGER", "nullable", "FK → res_partner (tự tham chiếu) — chờ gộp thành đối tác vừa là KH vừa là NCC"],
                ["dlm_allow_dup_tax", "BOOLEAN", "DEFAULT FALSE", "Cho phép trùng mã số thuế (trường hợp chi nhánh)"],
                ["dlm_has_photo", "BOOLEAN", "nullable", "compute, store=True → có cột"],
                ["dlm_customer_group", "VARCHAR", "nullable", "compute, store=True → có cột. Khai ở dl_sale. Enum §3.3"],
                ["partner_type_label, dlm_status_label, dlm_initial, dlm_avatar_bg, dlm_avatar_fg",
                 "—", "—", "compute, store=False → KHÔNG sinh cột"],
                ["dlm_quotation_count, dlm_win_rate, dlm_open_quote_count, dlm_recent_quote_count, "
                 "dlm_recent_quote_total, dlm_split_warning, dlm_split_threshold, dlm_currency_id",
                 "—", "—", "Khai ở dl_sale; compute, store=False → KHÔNG sinh cột"],
                ["dlm_quotation_ids", "—", "—", "One2many → dl_quotation, không sinh cột"],
            ],
            "extra": "Ràng buộc mức ứng dụng (@api.constrains, KHÔNG phải CHECK trong DB): "
                     "_check_partner_type, _check_company_tax_code (KH doanh nghiệp bắt buộc có MST), "
                     "_check_phone_format, _check_email_format, "
                     "_check_unique_tax_code (MST duy nhất trừ khi dlm_allow_dup_tax).",
        },
    ],
}

MODULE_C = {
    "title": "C. Module dl_product — sản phẩm, vật tư, bảng giá NCC",
    "lead": "Mở rộng 3 bảng native của Odoo và tạo 3 bảng mới cho hệ đo lường. Điểm cốt lõi: "
            "SẢN PHẨM là bảng HỢP NHẤT — cả 4 loại nghiệp vụ (SP gia công, SP thương mại, vật tư, "
            "bán thành phẩm) đều nằm trong product_product, phân biệt bằng product_kind. "
            "Đổi loại sản phẩm chỉ là đổi giá trị 1 cột, không phải chuyển bản ghi giữa các bảng.",
    "entities": [
        {
            "head": "C1. product.product [Mở rộng + mail.thread]",
            "desc": "SẢN PHẨM — bảng hợp nhất cho cả 4 loại nghiệp vụ. Kế thừa MỞ RỘNG THUẦN nên "
                    "mọi bản ghi nằm trực tiếp trong product_product, giữ nguyên vẹn "
                    "search / report / tồn kho của Odoo.",
            "meta": "_name = 'product.product'   ·   "
                    "_inherit = ['product.product', 'mail.thread', 'mail.activity.mixin']\n"
                    "Native dùng lại: name, default_code, list_price, standard_price, categ_id, "
                    "uom_id, type, active, seller_ids, image_1920, product_tmpl_id.",
            "note": ("Quyết định kiến trúc",
                     "Thiết kế cũ tách dl.product / dl.semi.product / dl.material thành 3 bảng "
                     "delegation qua _inherits đã bị BỎ (refactor dl_product 17.0.2.x): semi → "
                     "material_processed, material giữ nguyên. Lý do: tránh phân mảnh "
                     "product.product và bỏ hẳn việc migrate dữ liệu khi đổi loại sản phẩm."),
            "cols": [
                ["product_kind", "VARCHAR", "NOT NULL, DEFAULT 'manufactured'",
                 "Enum §3.3. Selection là CALLABLE — bị lọc theo context dl_kind_scope của từng màn, "
                 "ghi giá trị ngoài scope sẽ bị ORM chặn"],
                ["dlm_lifecycle_state", "VARCHAR", "NOT NULL, DEFAULT 'active'",
                 "Enum §3.3 — vòng đời draft / active / obsolete; tracking, copy=False"],
                ["dlm_waste_rate", "NUMERIC(6,2)", "nullable", "Hao hụt cơ sở (%) — NGUỒN DUY NHẤT của hao hụt, đặt trên vật tư"],
                ["dlm_has_recovery", "BOOLEAN", "nullable", "Có thu hồi phế liệu"],
                ["dlm_recovery_rate", "NUMERIC(6,2)", "nullable", "Tỷ lệ thu hồi (%) — tính trên LƯỢNG hao hụt"],
                ["dlm_scrap_product_id", "INTEGER", "nullable", "FK → product_product (tự tham chiếu) — sản phẩm phế liệu, đơn giá thu hồi lấy từ list_price của nó"],
                ["dl_categ_branch", "—", "—", "compute, store=False → KHÔNG sinh cột. Nhánh nhóm kỳ vọng, suy từ product_kind"],
                ["dlm_is_price_editor, dlm_has_draft_seller", "—", "—", "compute, store=False → KHÔNG sinh cột (dùng cho readonly/banner trên form)"],
                ["bom_ids", "—", "—", "Khai ở dl_technical; One2many computed → KHÔNG sinh cột"],
            ],
            "extra": "Ràng buộc mức ứng dụng: _check_default_code (default_code khớp ^[A-Z0-9\\-]+$ "
                     "và duy nhất — kiểm bằng search, KHÔNG phải UNIQUE trong DB); "
                     "_check_categ_branch (nhóm phải cùng nhánh với loại SP). "
                     "Cron _cron_obsolete_orphan_drafts chuyển SP nháp mồ côi quá hạn sang 'obsolete'; "
                     "ngưỡng ngày đọc từ ir.config_parameter khoá dl_product.orphan_draft_days (mặc định 30).",
        },
        {
            "head": "C2. product.category [Mở rộng — _inherit]",
            "desc": "Nhóm sản phẩm cơ khí. dl_branch KHÔNG do người dùng nhập — nó được SUY RA từ "
                    "vị trí của nhóm trong cây (nằm dưới gốc 'Thành phẩm' hay gốc 'Vật tư'), "
                    "dùng để tách danh mục đầu vào / đầu ra và chặn cứng nhóm theo loại sản phẩm.",
            "meta": "Native dùng lại: name, complete_name, parent_id, parent_path, product_count.",
            "cols": [
                ["active", "BOOLEAN", "DEFAULT TRUE", "Cờ lưu trữ — Odoo core không có trên product.category"],
                ["dl_branch", "VARCHAR", "nullable", "compute từ parent_path, store=True → CÓ cột. Enum §3.3"],
                ["bom_template_id", "INTEGER", "nullable, ON DELETE SET NULL",
                 "FK → dl_bom_template (E9). Khai ở dl_technical chứ KHÔNG ở dl_product, để giữ "
                 "đúng chiều phụ thuộc (dl_product không được depends dl_technical)"],
            ],
            "extra": "Ràng buộc: _check_branch_products — chặn kéo nhóm sang nhánh khác khi trong "
                     "nhóm đã có sản phẩm sai loại; bỏ qua khi context install_mode.",
        },
        {
            "head": "C3. product.supplierinfo [Mở rộng — _inherit]",
            "desc": "Bảng giá vật tư / SP thương mại theo NHÀ CUNG CẤP + THỜI ĐIỂM. Dùng bảng native "
                    "thay vì tự chế — thay thế hoàn toàn model cũ dl.material.price. "
                    "BOM đọc bảng này qua dòng có is_applied = TRUE để lấy price_snapshot.",
            "meta": "Native dùng lại: product_tmpl_id, partner_id, price, min_qty, date_end, "
                    "currency_id, company_id, delay.",
            "cols": [
                ["date_start", "DATE", "NOT NULL", "Native nhưng được SIẾT thành required trong dự án"],
                ["approval_state", "VARCHAR", "NOT NULL, DEFAULT 'draft'", "Enum §3.3 — Kế toán duyệt giá NCC; copy=False"],
                ["is_applied", "BOOLEAN", "DEFAULT FALSE", "Đánh dấu RÕ 1 bảng giá đang dùng để tính giá; copy=False"],
                ["display_state", "VARCHAR", "nullable", "compute từ approval_state + is_applied, store=True → CÓ cột. Enum §3.3"],
                ["product_image_128", "—", "—", "related product_tmpl_id.image_128, store=False → KHÔNG sinh cột"],
            ],
            "extra": "Ràng buộc mức ứng dụng: _check_price_positive (price > 0 — kiểm ở Python, "
                     "KHÔNG có CHECK constraint trong DB); _check_date_range (date_end ≥ date_start); "
                     "_check_is_applied (chỉ bảng giá đã duyệt mới được áp dụng, và mỗi "
                     "product_tmpl_id chỉ có TỐI ĐA 1 dòng is_applied — kiểm bằng search, "
                     "KHÔNG phải unique index).",
        },
        {
            "head": "C4. dl.measurement.type [Model mới]",
            "desc": "ĐẠI LƯỢNG đo lường (Diện tích / Chiều dài / Khối lượng / Thể tích). Thay cho cơ "
                    "chế công thức lưu-trong-DB cũ (dl.parametric.formula đã bỏ) — việc tính vật tư "
                    "từ kích thước nay dựa trên bộ Type → Shape → Param.",
            "meta": "_order = 'name'",
            "cols": [
                ["name", "VARCHAR", "NOT NULL", "Tên đại lượng"],
                ["description", "TEXT", "nullable", "Mô tả"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Đang sử dụng"],
                ["formula_uom_id", "INTEGER", "nullable", "FK → uom_uom. Đơn vị VẬT LÝ mà công thức trả về (kg, m², m³) — dùng để lọc Rule theo nhóm ĐVT của vật tư và tự quy đổi kết quả. Để trống ⇒ Rule không hiện ở dòng BOM nào"],
                ["shape_ids", "—", "—", "One2many → dl_measurement_shape, không sinh cột"],
            ],
        },
        {
            "head": "C5. dl.measurement.shape [Model mới]",
            "desc": "HÌNH DẠNG đo lường (tấm phẳng, ống vuông rỗng, tròn…) thuộc một đại lượng.",
            "meta": "_order = 'measurement_type_id, name'",
            "note": ("Nơi lưu công thức",
                     "Công thức tính KHÔNG lưu trong DB. Cột code là khoá để dispatch công thức "
                     "HARD-CODE trong Python (ví dụ flat_plate, hollow_square_tube). "
                     "dl_technical bổ sung ràng buộc _check_code_known để chặn code không nằm "
                     "trong tập công thức đã cài đặt."),
            "cols": [
                ["measurement_type_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_measurement_type (C4)"],
                ["name", "VARCHAR", "NOT NULL", "Tên hình dạng"],
                ["code", "VARCHAR", "nullable", "Khoá dispatch công thức hard-code"],
                ["default_coefficient", "NUMERIC(16,4)", "nullable", "Hệ số gợi ý khi dựng BOM (vd khối lượng riêng thép 7850 kg/m³)"],
                ["coefficient_label", "VARCHAR", "DEFAULT 'Hệ số'", "Nhãn hiển thị cho hệ số"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Đang sử dụng"],
                ["param_ids", "—", "—", "One2many → dl_measurement_shape_param, không sinh cột"],
            ],
        },
        {
            "head": "C6. dl.measurement.shape.param [Model mới]",
            "desc": "Định nghĩa TÊN các tham số kích thước theo từng hình dạng (chiều dài, chiều rộng, "
                    "độ dày, cạnh ngoài…). Model này CHỈ định nghĩa tên tham số — giá trị cụ thể được "
                    "nhập trên từng dòng BOM (các cột dim_* của E6), không lưu ở đây.",
            "meta": "_order = 'shape_id, name'",
            "cols": [
                ["shape_id", "INTEGER", "NOT NULL, ON DELETE CASCADE", "FK → dl_measurement_shape (C5)"],
                ["name", "VARCHAR", "NOT NULL", "Tên tham số"],
                ["code", "VARCHAR", "nullable", "Khoá để công thức đọc giá trị (length, width, thickness, side…)"],
                ["active", "BOOLEAN", "DEFAULT TRUE", "Đang sử dụng"],
            ],
        },
    ],
}
