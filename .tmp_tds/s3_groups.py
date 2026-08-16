# -*- coding: utf-8 -*-
"""§3.1 — cấu trúc nhóm A–F + các bảng CHƯA có trong tài liệu.

Nhóm và số lượng bám đúng docs/erd/DLM-ERP_Physical_Table_Inventory.md §3,
để §3.1 (văn bản) và ERD vật lý (7 trang) dùng chung một thứ tự mục lục.
"""

CH = ["Column", "Type", "PostgreSQL", "Constraints", "Notes"]
CW = [26, 17, 15, 20, 42]

DCC_HEADERS = ["Field / Action", "Type", "Validation / Rule"]
DCC_WIDTHS = [26, 16, 58]

# ─────────────────────────────── dẫn nhập §3.1 ───────────────────────────────

INTRO = (
    "The physical model is presented in six subject groups, A to F. The grouping, the order "
    "and the table counts are identical to the pages of the physical ERD, so an entity in the "
    "diagram and its definition below can be read side by side."
)

# Bảng chú giải này THAY bảng "Frefix | Meaning | Description" ở đầu §3 — cùng chỗ,
# cùng 3 cột, nhưng phủ đủ các cờ thật sự đang dùng trong tiêu đề của §3.1.
LEGEND_HEADERS = ["Marker", "Meaning", "Description"]
LEGEND_WIDTHS = [16, 26, 58]
LEGEND_ROWS = [
    ["[Native]", "Bảng lõi Odoo, dùng nguyên trạng",
     "Dự án KHÔNG thêm cột nào — chỉ đọc hoặc tham chiếu. §3.1 chỉ liệt kê các cột mang khoá "
     "ngoại hoặc chi phối một luật nghiệp vụ được mô tả trong tài liệu này, không liệt kê hết."],
    ["[Inherit]", "Bảng lõi Odoo được thêm cột (_inherit)",
     "Mọi cột do dự án thêm đều mang tiền tố dlm_ (hoặc dl_), nên nhìn tên cột là biết ranh "
     "giới giữa phần Odoo và phần nhóm làm ra."],
    ["[New]", "Bảng do dự án tạo mới (models.Model)",
     "Odoo tự sinh id và 4 cột kiểm toán create_uid / create_date / write_uid / write_date cho "
     "mọi bảng loại này; §3.1 không lặp lại chúng ở từng bảng."],
    ["[Mixin]", "models.AbstractModel — KHÔNG sinh bảng",
     "Cột của mixin được nhân bản vật lý xuống từng bảng kế thừa. Mô tả một lần để không phải "
     "lặp lại ở mọi bảng con."],
    ["[SQL VIEW]", "_auto = False",
     "CREATE OR REPLACE VIEW của PostgreSQL, không phải bảng: không sequence khoá chính, không "
     "cột kiểm toán, không có đường INSERT/UPDATE."],
    ["[Transient]", "models.TransientModel — bảng tạm của wizard",
     "Có sinh bảng thật nhưng dữ liệu bị ORM vacuum xoá sau transient_max_hours. Cố ý không đưa "
     "vào §3.1 và §3.2 — xem ghi chú cuối §3.1."],
    ["[Deprecated]", "Bảng chết còn sót trong schema",
     "Không còn nghiệp vụ nào dùng. Odoo không bao giờ DROP TABLE khi field bị gỡ khỏi source — "
     "xem §3.5."],
    ["PK", "Primary Key", "Khoá chính"],
    ["FK", "Foreign Key", "Khoá ngoại trỏ sang bảng khác"],
]

# ──────────────────────────────── nhóm A–F ───────────────────────────────────
# key: khớp key trong .tmp_erd/phys_cols.json (hoặc NEW_ENTITIES bên dưới)

GROUPS = [
    dict(
        letter="A", title="Group A — Partners · Users · Access Control",
        count="6 tables",
        lead=("Đối tác và người dùng là hai bảng “hub” của toàn hệ: 29 trong số 64 khoá ngoại "
              "liên nhóm trỏ về đây. Khách hàng và Nhà cung cấp dùng CHUNG bảng res_partner, "
              "phân biệt bằng cột partner_role chứ không tách bảng — quyết định này kéo theo "
              "việc phân quyền phải làm bằng ir.rule thay vì ACL, xem §4."),
        keys=["res_partner", "res_users", "res_company", "res_country",
              "dl_rbac_feature", "dl_rbac_operation"],
    ),
    dict(
        letter="B", title="Group B — Product & Material Catalogue",
        count="8 tables",
        lead=("Bốn loại mặt hàng nghiệp vụ — sản phẩm gia công, sản phẩm thương mại, vật tư, "
              "bán thành phẩm — nằm CHUNG trên product_product và phân biệt bằng product_kind. "
              "Không có bảng dl_material hay dl_semi_product riêng; thiết kế tách bảng cũ đã bị "
              "loại bỏ trong đợt tái cấu trúc dl_product."),
        keys=["product_product", "product_template", "product_category",
              "product_supplierinfo", "uom_uom", "dl_measurement_type",
              "dl_measurement_shape", "dl_measurement_shape_param"],
    ),
    dict(
        letter="C", title="Group C — Engineering: Drawing · BOM · RFQ",
        count="11 tables + 2 link tables",
        lead=("Nhóm đông khoá ngoại nội bộ nhất (11 FK trong nhóm). BOM báo giá và BOM mẫu dùng "
              "chung hai mixin — dl.bom.header.mixin cho phần đầu và dl.bom.line.mixin cho phần "
              "dòng — nên hai cặp bảng có cấu trúc cột gần như trùng nhau mà không phải khai lại."),
        keys=["dl_drawing", "dl.bom.header.mixin", "dl_bom", "dl.bom.line.mixin",
              "dl_bom_line", "dl_bom_operation_line", "dl_bom_template",
              "dl_bom_template_line", "dl_bom_template_param",
              "dl_bom_template_line_param_map", "dl_quotation_request",
              "dl_quotation_request_line", "dl_quotation_request_line_image"],
    ),
    dict(
        letter="D", title="Group D — Sales: Quotation & Sales Order",
        count="5 tables",
        lead=("Báo giá là nơi giá được CHỐT LẠI thành ảnh chụp: dl_quotation_price_component lưu "
              "từng thành phần giá tại thời điểm tính, nên báo giá đã gửi không đổi giá khi bảng "
              "giá nhà cung cấp hay tham số cấu hình thay đổi về sau. Đơn hàng chép lại từ báo "
              "giá và cố ý BỎ mọi cột giá vốn."),
        keys=["dl_quotation", "dl_quotation_line", "dl_quotation_price_component",
              "dl_sale_order", "dl_sale_order_line"],
    ),
    dict(
        letter="E", title="Group E — Pricing Configuration & Approval",
        count="14 tables",
        lead=("Toàn bộ tham số của engine tính giá nằm ở nhóm này. Mọi bảng quy tắc đều kế thừa "
              "dl.pricing.rule.mixin (khoảng hiệu lực + trạng thái), các bảng mang tính THƯƠNG MẠI "
              "kế thừa thêm dl.pricing.commercial.mixin (bắt buộc qua phê duyệt trước khi áp dụng)."),
        keys=["dl.pricing.rule.mixin", "dl.pricing.commercial.mixin", "dl_pricing_config",
              "dl_pricing_complexity_level", "dl_pricing_waste_rule", "dl_pricing_operation",
              "dl_pricing_operation_rule", "dl_pricing_cost_adjustment_rule",
              "dl_pricing_profit_rule", "dl_pricing_discount_rule",
              "dl_pricing_approval_matrix", "dl_pricing_approval_setting",
              "dl_pricing_approval_request", "dl_config_audit_log"],
    ),
    dict(
        letter="F", title="Group F — Inventory: Receiving · QC · Transfer · Delivery · Scrap",
        count="9 tables + 1 SQL view",
        lead=("dl_inventory KHÔNG tạo bảng lưu trữ mới. Nó dùng lại schema stock của Odoo và thêm "
              "11 cột vật lý rải trên 4 bảng lõi, 2 cột trên dl_sale_order, cùng một SQL VIEW chỉ "
              "đọc. Cột có tiền tố dlm_ là phần dự án thêm vào."),
        keys=["stock_warehouse", "stock_location", "stock_picking_type", "stock_picking",
              "stock_move", "stock_move_line", "stock_quant", "stock_lot",
              "procurement_group", "dl_scrap_recovery_report"],
    ),
]

# ───────────────── các bảng CHƯA có trong §3.1 hiện tại ──────────────────────
# (9 bảng: 2 nhóm A, 2 nhóm B, 3 nhóm C, 2+2 nhóm E, 1 nhóm F)

NEW_ENTITIES = {

    # ── Nhóm A ───────────────────────────────────────────────────────────────
    "res_company": dict(
        head="Table: res_company [Native]",
        desc=("Pháp nhân sở hữu dữ liệu. Đại Linh chạy MỘT công ty duy nhất, nhưng gần như mọi "
              "bảng quy tắc giá đều mang company_id để ràng buộc phạm vi áp dụng và để hệ thống "
              "còn đường mở rộng đa công ty về sau."),
        meta="dl_base thêm 0 cột — chỉ override một method (xem bảng ràng buộc bên dưới).",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL", "Tên công ty"],
            ["currency_id [Native]", "Many2one", "INTEGER", "FK → res_currency, NOT NULL",
             "Bị ép về VNĐ mỗi lần -u dl_base — xem ràng buộc bên dưới"],
            ["partner_id [Native]", "Many2one", "INTEGER", "FK → res_partner, NOT NULL",
             "Công ty cũng là một partner"],
        ],
        extra=("Đây là bảng lõi được liệt kê rút gọn: PostgreSQL có 45 cột, ở đây chỉ nêu các cột "
               "mang khoá ngoại hoặc chi phối luật nghiệp vụ."),
    ),

    "res_country": dict(
        head="Table: res_country [Native]",
        desc=("Danh mục quốc gia của Odoo, dùng cho địa chỉ đối tác. Dự án không thêm cột nào; "
              "chỉ đổi điều hướng để nút mở form dùng giao diện DLM."),
        meta="dl_partner thêm 0 cột — chỉ override get_formview_action().",
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char translated", "JSONB", "NOT NULL",
             "Odoo 17 lưu bản dịch dạng JSONB"],
            ["code [Native]", "Char", "VARCHAR(2)", "UNIQUE", "Mã ISO 3166-1 alpha-2"],
        ],
    ),

    # ── Nhóm B ───────────────────────────────────────────────────────────────
    "product_template": dict(
        head="Table: product_template [Native]",
        desc=("Bảng “mẫu sản phẩm” của Odoo. Dự án KHÔNG kế thừa bảng này trực tiếp — mọi field "
              "bổ sung được khai trên product.product (xem bảng ngay trên). Bảng vẫn xuất hiện "
              "trong mô hình vì product_product trỏ tới nó bằng _inherits (delegation), nên mỗi "
              "dòng product_product luôn kèm đúng một dòng product_template."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char translated required", "JSONB", "NOT NULL", "Tên mặt hàng"],
            ["type [Native]", "Selection", "VARCHAR", "NOT NULL",
             "Đặt 'product' (storable) để Kho theo dõi tồn — giá trị này do module stock thêm vào"],
            ["categ_id [Native]", "Many2one required", "INTEGER",
             "FK → product_category, NOT NULL", "Nhóm sản phẩm"],
            ["uom_id [Native]", "Many2one required", "INTEGER", "FK → uom_uom, NOT NULL",
             "Đơn vị tính"],
            ["active [Native]", "Boolean", "BOOL", "DEFAULT TRUE", "Lưu trữ thay vì xoá"],
        ],
        extra=("Quan hệ _inherits là kế thừa theo KIỂU ỦY QUYỀN (delegation): khoá ngoại "
               "product_product.product_tmpl_id vừa là FK vừa đóng vai trò khoá chính logic của "
               "quan hệ kế thừa. Đây là một trong bốn phương án ánh xạ kế thừa ở bước 8 của quy "
               "trình thiết kế CSDL."),
    ),

    "uom_uom": dict(
        head="Table: uom_uom [Native]",
        desc=("Đơn vị tính. Được dùng nguyên bản; dự án chỉ seed thêm các đơn vị cơ khí hay dùng "
              "qua data/uom_data.xml (kg, m, m², cây, tấm...)."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char translated required", "JSONB", "NOT NULL", "Tên đơn vị"],
            ["category_id [Native]", "Many2one required", "INTEGER",
             "FK → uom_category, NOT NULL",
             "Chỉ quy đổi được giữa các đơn vị CÙNG category"],
            ["factor [Native]", "Float", "NUMERIC", "NOT NULL", "Hệ số quy đổi về đơn vị gốc"],
            ["uom_type [Native]", "Selection", "VARCHAR", "NOT NULL",
             "bigger / reference / smaller"],
        ],
    ),

    # ── Nhóm C ───────────────────────────────────────────────────────────────
    "dl_bom_operation_line": dict(
        head="Table: dl_bom_operation_line [New]",
        desc=("Công đoạn gia công của một BOM (cắt, hàn, sơn, mạ...). Mỗi dòng trỏ tới một "
              "dl_pricing_operation và lấy đơn giá từ quy tắc công đoạn đang hiệu lực. Cột "
              "method / has_active_rule / needs_base_qty là compute KHÔNG store — chúng đọc quy "
              "tắc hiện hành theo thời gian thực nên không được đóng băng thành cột."),
        cols=[
            ["id", "—", "SERIAL", "PK", "Auto-increment"],
            ["bom_id", "Many2one required", "INTEGER",
             "FK → dl_bom, NOT NULL, ON DELETE CASCADE, INDEX", "Xoá BOM thì xoá công đoạn"],
            ["sequence", "Integer", "INTEGER", "DEFAULT 10", "Thứ tự hiển thị"],
            ["operation_id", "Many2one required", "INTEGER",
             "FK → dl_pricing_operation, NOT NULL, ON DELETE RESTRICT",
             "RESTRICT: không cho xoá công đoạn đang được BOM dùng"],
            ["base_qty", "Float", "NUMERIC", "—",
             "Định mức cơ sở; chỉ nhập khi phương pháp tính cần (needs_base_qty)"],
            ["material_scope", "Selection required", "VARCHAR", "NOT NULL DEFAULT 'all'",
             "all = tính trên toàn bộ vật tư · selected = chỉ vật tư đã chọn"],
            ["material_line_ids", "Many2many", "—", "bảng liên kết",
             "→ dl_bom_line. Sinh bảng dl_bom_line_dl_bom_operation_line_rel"],
            ["is_outsourced", "Boolean", "BOOL", "—", "Công đoạn thuê ngoài"],
            ["partner_id", "Many2one", "INTEGER", "FK → res_partner",
             "Nhà cung cấp gia công, chỉ khi is_outsourced"],
            ["note", "Char", "VARCHAR", "—", "Ghi chú"],
        ],
        extra=("estimated_unit_cost là compute không store — nó phải phản ánh quy tắc giá HIỆN "
               "HÀNH; nếu store thì BOM cũ sẽ giữ đơn giá cũ và lệch với engine tính giá."),
    ),

    "dl_bom_template_param": dict(
        head="Table: dl_bom_template_param [New]",
        desc=("Tham số cấp sản phẩm của một BOM mẫu — ví dụ Dài × Rộng × Cao của khung thép. Khi "
              "kỹ thuật viên áp mẫu lên một sản phẩm mới, họ chỉ nhập các tham số này và hệ thống "
              "suy ra số lượng từng vật tư qua bảng ánh xạ ngay bên dưới."),
        cols=[
            ["id", "—", "SERIAL", "PK", "Auto-increment"],
            ["bom_template_id", "Many2one required", "INTEGER",
             "FK → dl_bom_template, NOT NULL, ON DELETE CASCADE, INDEX", "Mẫu chứa tham số"],
            ["sequence", "Integer", "INTEGER", "DEFAULT 10", "Thứ tự nhập liệu"],
            ["code", "Char required", "VARCHAR", "NOT NULL, UNIQUE(bom_template_id, code)",
             "Mã tham số dùng trong công thức, VD D, R, C"],
            ["name", "Char required", "VARCHAR", "NOT NULL", "Nhãn hiển thị cho người nhập"],
            ["dim_role", "Selection", "VARCHAR", "DEFAULT 'none'",
             "Vai trò kích thước: length / width / height / thickness / side / none"],
            ["default_value", "Float", "NUMERIC", "—", "Giá trị gợi ý sẵn"],
            ["value_min", "Float", "NUMERIC", "—", "Chặn dưới khi nhập"],
            ["value_max", "Float", "NUMERIC", "—", "Chặn trên khi nhập"],
            ["required", "Boolean", "BOOL", "DEFAULT TRUE", "Bắt buộc nhập khi áp mẫu"],
        ],
    ),

    "dl_bom_template_line_param_map": dict(
        head="Table: dl_bom_template_line_param_map [New]",
        desc=("Ánh xạ “tham số → ô số liệu của dòng vật tư mẫu”. Một dòng nói: lấy tham số D, "
              "nhân factor rồi cộng offset, ghi kết quả vào ô dim_length của dòng vật tư này. "
              "Đây là cơ chế thay cho công thức tự do — giữ được tính kiểm chứng được của số liệu."),
        cols=[
            ["id", "—", "SERIAL", "PK", "Auto-increment"],
            ["template_line_id", "Many2one required", "INTEGER",
             "FK → dl_bom_template_line, NOT NULL, ON DELETE CASCADE, INDEX",
             "Dòng vật tư mẫu nhận giá trị"],
            ["bom_template_id", "Many2one related stored", "INTEGER",
             "FK → dl_bom_template, INDEX",
             "Bản sao có store của template_line_id.bom_template_id — để lọc nhanh theo mẫu"],
            ["target_field", "Selection required", "VARCHAR", "NOT NULL",
             "Ô đích: dim_length / dim_width / piece_count / quantity"],
            ["param_id", "Many2one required", "INTEGER",
             "FK → dl_bom_template_param, NOT NULL, ON DELETE CASCADE", "Tham số nguồn"],
            ["factor", "Float", "NUMERIC", "DEFAULT 1.0", "Hệ số nhân"],
            ["offset", "Float", "NUMERIC", "DEFAULT 0.0", "Số cộng thêm"],
        ],
        extra="Giá trị ghi vào ô đích = param_value × factor + offset.",
    ),

    # ── Nhóm E ───────────────────────────────────────────────────────────────
    "dl.pricing.commercial.mixin": dict(
        head="Mixin: dl.pricing.commercial.mixin [Mixin]",
        desc=("Lớp phê duyệt dùng chung cho hai bảng quy tắc THƯƠNG MẠI — lợi nhuận "
              "(dl_pricing_profit_rule) và chiết khấu (dl_pricing_discount_rule). Mixin kế thừa "
              "dl.pricing.rule.mixin và KHÔNG khai thêm field nào: nó chỉ thay hành vi — chặn nút "
              "Áp dụng trực tiếp và buộc mọi thay đổi đi qua một yêu cầu phê duyệt."),
        cols=None,
        extra=("Vì không có cột riêng, mixin này không để lại dấu vết nào trong schema; phần cột "
               "của hai bảng kế thừa đã mô tả ở dl.pricing.rule.mixin ngay trên. Ranh giới đáng "
               "nhớ: quy tắc KỸ THUẬT (công đoạn, hao hụt, chi phí điều chỉnh) tự áp dụng được, "
               "quy tắc THƯƠNG MẠI thì không — khác biệt đó nằm ở mixin này chứ không nằm ở cấu "
               "trúc bảng."),
    ),

    "dl_pricing_config": dict(
        head="Table: dl_pricing_config [New]",
        desc=("Tham số báo giá dùng chung: thuế suất VAT mặc định và mức làm tròn giá bán. Bảng "
              "chỉ giữ MỘT dòng cấu hình đang dùng."),
        cols=[
            ["id", "—", "SERIAL", "PK", "Auto-increment"],
            ["name", "Char required", "VARCHAR", "NOT NULL DEFAULT 'Cấu hình báo giá'",
             "Tên cấu hình"],
            ["vat_pct", "Float", "NUMERIC", "DEFAULT 0.0", "VAT mặc định (%), khoảng hợp lệ 0–100"],
            ["rounding_to", "Integer", "INTEGER", "DEFAULT 1000",
             "Làm tròn giá bán đến bội số này (đồng)"],
        ],
        note=("Bảng này là bằng chứng rõ nhất cho §3.5",
              "Source hiện tại khai 3 field ⇒ 8 cột vật lý. Nhưng trên một DB đã nâng cấp nhiều "
              "lần, bảng này đang có 24 cột — 16 cột mồ côi còn lại từ các phiên bản trước "
              "(sla_*, material_pct, margin_pct...). Odoo KHÔNG BAO GIỜ tự DROP COLUMN. Xem §3.5."),
    ),

    "dl_config_audit_log": dict(
        head="Table: dl_config_audit_log [New]",
        desc=("Nhật ký thay đổi cấu hình hệ thống (màn S02). Ghi lại ai đổi tham số nào, từ giá "
              "trị cũ sang giá trị mới — phục vụ truy vết khi một báo giá cũ ra số khác với hôm nay."),
        cols=[
            ["id", "—", "SERIAL", "PK", "Auto-increment"],
            ["config_tab", "Char", "VARCHAR", "—", "Nhóm cấu hình bị đổi"],
            ["param_label", "Char", "VARCHAR", "—", "Tên tham số"],
            ["detail", "Char", "VARCHAR", "—", "Nội dung thay đổi, dạng “cũ → mới”"],
            ["user_id", "Many2one", "INTEGER", "FK → res_users, DEFAULT env.uid",
             "Người thực hiện"],
            ["create_date", "Datetime", "TIMESTAMP", "auto", "Thời điểm — cột kiểm toán của Odoo"],
        ],
        extra=("Bảng chỉ ghi thêm (append-only) ở tầng nghiệp vụ: không có màn hình nào sửa hay "
               "xoá dòng nhật ký."),
    ),

    # ── Nhóm F ───────────────────────────────────────────────────────────────
    "procurement_group": dict(
        head="Table: procurement_group [Native]",
        desc=("Nhóm điều vận của Odoo. Khi một tuyến đường (route) sinh ra nhiều chặng — ở đây là "
              "tuyến nhận hàng hai bước NHẬN → KIỂM & CẤT — Odoo gắn các chặng vào cùng một "
              "procurement_group để biết chúng thuộc cùng một lần giao. Dự án không thêm cột nào."),
        cols=[
            ["id [Native]", "—", "SERIAL", "PK", "Auto-increment"],
            ["name [Native]", "Char required", "VARCHAR", "NOT NULL",
             "Thường là số chứng từ nguồn"],
            ["move_type [Native]", "Selection", "VARCHAR", "NOT NULL",
             "direct = giao từng phần · one = giao đủ mới xuất"],
            ["partner_id [Native]", "Many2one", "INTEGER", "FK → res_partner", "Địa chỉ giao"],
        ],
    ),
}

# ── hai bảng đã ngừng dùng, vẫn còn trong schema ─────────────────────────────

DEPRECATED = dict(
    label="Two tables still present in the schema but no longer used",
    text=("dl_pricing_waste (group_name, waste_pct) và dl_approval_level (sequence, name) là "
          "thiết kế của đợt cấu hình giá đầu tiên. Chúng đã được thay bằng dl_pricing_waste_rule "
          "và cột approval_level trên dl_pricing_approval_matrix. Hai bảng vẫn nằm trong "
          "PostgreSQL vì Odoo không DROP TABLE khi field bị gỡ khỏi source; chúng không còn màn "
          "hình, không còn khoá ngoại trỏ tới, và KHÔNG được vẽ vào ERD. Ghi ra đây để người đọc "
          "đối chiếu schema thật không tưởng là tài liệu bỏ sót."),
)

M2M = dict(
    label="Two many-to-many link tables",
    text=("dl_rfq_line_ir_attachment_rel (dl_quotation_request_line ⋈ ir_attachment — tệp đính "
          "kèm của dòng RFQ, khai tường minh) và dl_bom_line_dl_bom_operation_line_rel "
          "(dl_bom_line ⋈ dl_bom_operation_line — vật tư được chọn cho một công đoạn, do Odoo tự "
          "sinh). Mỗi bảng chỉ có 2 cột, cả hai đều là khoá ngoại và cùng tạo thành khoá chính. "
          "Lưu ý: hai field Many2many dlm_source_available_product_ids và "
          "dlm_orderable_product_ids trên stock_picking là compute KHÔNG store nên Odoo không "
          "sinh bảng liên kết cho chúng — tổng số bảng m2m toàn hệ vẫn là 2."),
)

TRANSIENT = dict(
    label="Transient (wizard) tables are intentionally excluded from §3.1 and §3.2",
    text=("15 model wizard dưới đây CÓ sinh bảng thật trong PostgreSQL, nhưng dữ liệu của chúng "
          "bị ORM vacuum xoá tự động sau transient_max_hours (mặc định 1 giờ). Chúng không giữ "
          "dữ liệu nghiệp vụ bền vững và không có ràng buộc toàn vẹn dài hạn để mô hình hoá; đưa "
          "vào sẽ thêm khoảng 40 cạnh chỉ để mô tả trạng thái tạm của giao diện: "
          "dl_bom_create_btp_wizard, dl_bom_from_template_wizard, "
          "dl_pricing_approval_reject_wizard, dl_pricing_ui, dl_quotation_export_wizard, "
          "dl_quotation_reject_wizard, dl_quotation_revision_wizard, dl_rfq_history_wizard, "
          "dl_rfq_line_infeasible_wizard, dl_rfq_line_supplement_wizard, dl_rfq_resolve_param, "
          "dl_rfq_resolve_wizard, dl_rfq_return_wizard, dl_rfq_return_wizard_line, "
          "dl_sale_order_reset_draft_wizard. Đây là lựa chọn có lý do, không phải bỏ sót."),
)
