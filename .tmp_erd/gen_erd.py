# -*- coding: utf-8 -*-
"""Sinh docs/DLM-ERP_Conceptual_ERD.drawio: 1 sơ đồ tổng thể + 5 sub-ERD."""
import html
import os

ROW_H = 18
HEAD_H = 26
BOX_W = 260
COL_GAP = 310
ROW_GAP = 40
TOP = 50
LEFT = 40

# ---------------------------------------------------------------- entities
# key: (Tên hiển thị, [attributes]) — attribute mở đầu bằng '*' là định danh
E = {
    "DOI_TAC": ("Đối tác\n(Partner)", [
        "*partner_id", "partner_name", "partner_role", "tax_code",
        "phone / mobile", "email", "address", "is_active"]),
    "KHACH_HANG": ("Khách hàng\n(Customer)", [
        "*customer_code", "customer_type", "customer_group", "win_rate",
        "amount_last_7days", "split_order_warning"]),
    "NHA_CUNG_CAP": ("Nhà cung cấp / Thầu phụ\n(Supplier)", [
        "*supplier_id", "supplier_name", "tax_code", "phone / email",
        "address", "is_active"]),
    "NHOM_SAN_PHAM": ("Nhóm sản phẩm\n(Product Category)", [
        "*category_id", "category_name", "parent_category_id",
        "category_branch", "is_active"]),
    "MAT_HANG": ("Mặt hàng\n(Item)", [
        "*item_code", "item_name", "product_kind", "category_id", "uom_id",
        "sale_price", "reference_cost", "lifecycle_state", "is_rfq_draft"]),
    "SAN_PHAM_GIA_CONG": ("Sản phẩm gia công\n(Manufactured Product)", [
        "length / width / height", "thickness", "main_material_id",
        "finishing_type", "estimated_weight"]),
    "SAN_PHAM_THUONG_MAI": ("Sản phẩm thương mại\n(Trading Product)", [
        "sale_price", "reference_cost", "margin_rate", "supplier_price_state"]),
    "VAT_TU": ("Vật tư\n(Raw Material)", [
        "density", "base_waste_rate", "is_recoverable", "recovery_rate",
        "scrap_product_id", "supplier_price_state"]),
    "BAN_THANH_PHAM": ("Bán thành phẩm\n(Processed Material)", [
        "length / width / height", "thickness", "main_material_id",
        "base_waste_rate", "is_recoverable"]),
    "BANG_GIA_NCC": ("Bảng giá Nhà cung cấp\n(Supplier Price List)", [
        "*price_id", "supplier_id", "item_id", "unit_price", "purchase_uom_id",
        "min_quantity", "date_start / date_end", "approval_state", "is_applied"]),
    "DON_VI_TINH": ("Đơn vị tính\n(Unit of Measure)", [
        "*uom_id", "uom_name", "uom_category_id", "conversion_factor"]),
    "BAN_VE": ("Bản vẽ kỹ thuật\n(Technical Drawing)", [
        "*drawing_code", "drawing_name", "product_id", "version",
        "attachment_id", "state", "is_current"]),
    "DINH_MUC": ("Định mức — BOM\n(Bill of Materials)", [
        "*bom_code", "product_id", "bom_type", "version", "output_quantity",
        "state", "is_current", "total_material_cost", "approved_by / date"]),
    "DONG_VAT_TU": ("Dòng vật tư của Định mức\n(BOM Material Line)", [
        "*line_id", "material_id", "dimensions", "computed_quantity",
        "quantity", "waste_rate", "actual_quantity", "unit_price_snapshot",
        "recovery_value", "subtotal"]),
    "DONG_CONG_DOAN": ("Dòng công đoạn của Định mức\n(BOM Operation Line)", [
        "*line_id", "operation_id", "pricing_method", "base_qty_per_unit",
        "material_base_scope", "is_outsourced", "subcontractor_id",
        "estimated_cost_per_unit"]),
    "CONG_DOAN": ("Công đoạn\n(Operation)", [
        "*operation_code", "operation_name", "is_active"]),
    "RFQ": ("Yêu cầu báo giá\n(Quotation Request)", [
        "*request_code", "customer_id", "received_date", "deadline", "state",
        "created_by", "assigned_to", "technical_progress", "deadline_status"]),
    "DONG_RFQ": ("Dòng yêu cầu báo giá\n(Quotation Request Line)", [
        "*line_id", "line_kind", "product_name", "quantity", "dimension_note",
        "resolved_product_id", "bom_id", "is_infeasible", "technical_state",
        "missing_supplier_price"]),
    "BAO_GIA": ("Báo giá\n(Quotation)", [
        "*quotation_no", "customer_id", "quotation_date", "pricing_date",
        "validity_date", "state", "version", "previous_quotation_id",
        "discount_rate / vat_rate", "amount_total", "total_cost",
        "approval_state"]),
    "DONG_BAO_GIA": ("Dòng báo giá\n(Quotation Line)", [
        "*line_id", "description", "quantity", "unit_price", "subtotal",
        "line_kind", "product_id", "bom_id", "bom_version", "unit_cost",
        "floor_price_per_unit"]),
    "CAU_PHAN_GIA": ("Cấu phần giá\n(Price Component)", [
        "*component_id", "component_type", "item_id", "source_type",
        "source_code", "source_version", "quantity", "unit_price", "subtotal",
        "is_discount_excluded"]),
    "DON_BAN_HANG": ("Đơn bán hàng\n(Sales Order)", [
        "*order_no", "customer_id", "source_quotation_id", "order_date",
        "state", "discount_rate / vat_rate", "amount_total"]),
    "DONG_DON": ("Dòng đơn bán hàng\n(Sales Order Line)", [
        "*line_id", "description", "quantity", "unit_price", "subtotal",
        "line_kind", "product_id", "bom_id", "bom_version"]),
    "CAU_HINH_GIA": ("Cấu hình giá\n(Pricing Configuration)", [
        "*rule_id", "rule_type", "target_ref", "calculation_method", "value",
        "date_start / date_end", "version", "change_reason", "state",
        "is_used_in_quotation"]),
    "MA_TRAN": ("Ma trận phê duyệt báo giá\n(Approval Matrix)", [
        "*matrix_id", "amount_threshold_from", "approval_level",
        "specific_approver_id", "revision_of_id", "version", "state"]),
    "YC_PHE_DUYET": ("Yêu cầu phê duyệt\n(Approval Request)", [
        "*request_id", "request_type", "target_ref", "old_value / new_value",
        "reason", "requested_by", "approval_level", "state",
        "approved_by / processed_date"]),
    "NGUOI_DUNG": ("Người dùng\n(User)", [
        "*user_id", "full_name", "login / email", "phone", "is_active",
        "backup_approver_id", "last_login"]),
    "VAI_TRO": ("Vai trò\n(Role)", [
        "*role_id", "role_name", "description", "is_system_role", "user_count"]),
    "CONG_TY": ("Công ty\n(Company)", [
        "*company_id", "company_name", "currency_id", "address"]),
}

GROUPS = [
    ("A — Đối tác", ["DOI_TAC", "KHACH_HANG", "NHA_CUNG_CAP"]),
    ("B — Danh mục Sản phẩm & Vật tư",
     ["NHOM_SAN_PHAM", "MAT_HANG", "SAN_PHAM_GIA_CONG", "SAN_PHAM_THUONG_MAI",
      "VAT_TU", "BAN_THANH_PHAM", "BANG_GIA_NCC", "DON_VI_TINH"]),
    ("C — Kỹ thuật",
     ["BAN_VE", "DINH_MUC", "DONG_VAT_TU", "DONG_CONG_DOAN", "CONG_DOAN"]),
    ("D — Kinh doanh",
     ["RFQ", "DONG_RFQ", "BAO_GIA", "DONG_BAO_GIA", "CAU_PHAN_GIA",
      "DON_BAN_HANG", "DONG_DON"]),
    ("E — Cấu hình & Hệ thống",
     ["CAU_HINH_GIA", "MA_TRAN", "YC_PHE_DUYET", "NGUOI_DUNG", "VAI_TRO",
      "CONG_TY"]),
]

# card: 1 = đúng một, 0..1 = không hoặc một, N = một hoặc nhiều, 0..N = không hoặc nhiều
ARROW = {"1": "ERmandOne", "0..1": "ERzeroToOne", "N": "ERoneToMany",
         "0..N": "ERzeroToMany"}

# ---------------------------------------------------------------- pages
# (tên trang, [cột: [entity keys]], [entity vẽ dạng biên], [quan hệ])
# quan hệ: (src, tgt, nhãn, card phía src, card phía tgt)

REL_OVERVIEW = [
    ("DOI_TAC", "KHACH_HANG", "ISA", "1", "0..1"),
    ("DOI_TAC", "NHA_CUNG_CAP", "ISA", "1", "0..1"),
    ("MAT_HANG", "SAN_PHAM_GIA_CONG", "ISA", "1", "0..1"),
    ("MAT_HANG", "VAT_TU", "ISA", "1", "0..1"),
    ("NHOM_SAN_PHAM", "MAT_HANG", "classifies", "1", "0..N"),
    ("NHA_CUNG_CAP", "BANG_GIA_NCC", "issues", "1", "0..N"),
    ("BANG_GIA_NCC", "MAT_HANG", "updates cost", "0..N", "1"),
    ("SAN_PHAM_GIA_CONG", "DINH_MUC", "produces", "1", "0..N"),
    ("SAN_PHAM_GIA_CONG", "BAN_VE", "references", "1", "0..N"),
    ("DINH_MUC", "DONG_VAT_TU", "contains", "1", "N"),
    ("DINH_MUC", "DONG_CONG_DOAN", "contains", "1", "0..N"),
    ("DONG_VAT_TU", "VAT_TU", "consumes", "0..N", "1"),
    ("DONG_CONG_DOAN", "CONG_DOAN", "references", "0..N", "1"),
    ("KHACH_HANG", "RFQ", "requests", "1", "0..N"),
    ("RFQ", "DONG_RFQ", "contains", "1", "N"),
    ("DONG_RFQ", "DINH_MUC", "references", "0..N", "0..1"),
    ("RFQ", "BAO_GIA", "generates", "1", "0..N"),
    ("BAO_GIA", "DONG_BAO_GIA", "contains", "1", "N"),
    ("DONG_BAO_GIA", "CAU_PHAN_GIA", "contains", "1", "N"),
    ("BAO_GIA", "DON_BAN_HANG", "converts", "1", "0..1"),
    ("DON_BAN_HANG", "DONG_DON", "contains", "1", "N"),
    ("CAU_HINH_GIA", "DONG_BAO_GIA", "calculates", "1", "0..N"),
    ("MA_TRAN", "BAO_GIA", "routes", "1", "0..N"),
    ("BAO_GIA", "YC_PHE_DUYET", "requests", "1", "0..N"),
    ("YC_PHE_DUYET", "NGUOI_DUNG", "notifies", "0..N", "1"),
    ("NGUOI_DUNG", "VAI_TRO", "assigns (N:M)", "0..N", "0..N"),
    ("CONG_TY", "BAO_GIA", "issues", "1", "0..N"),
]

PAGES = [
    dict(
        name="0. Tổng thể (Overview)",
        overview=True,
        rels=REL_OVERVIEW,
    ),
    dict(
        name="1. Đối tác & Danh mục",
        cols=[["DOI_TAC", "KHACH_HANG", "NHA_CUNG_CAP"],
              ["NHOM_SAN_PHAM", "MAT_HANG", "DON_VI_TINH"],
              ["SAN_PHAM_GIA_CONG", "SAN_PHAM_THUONG_MAI", "VAT_TU",
               "BAN_THANH_PHAM"],
              ["BANG_GIA_NCC"]],
        edge=[],
        rels=[
            ("DOI_TAC", "KHACH_HANG", "ISA — partner_role", "1", "0..1"),
            ("DOI_TAC", "NHA_CUNG_CAP", "ISA — partner_role", "1", "0..1"),
            ("NHOM_SAN_PHAM", "NHOM_SAN_PHAM", "phân cấp cây", "0..1", "0..N"),
            ("NHOM_SAN_PHAM", "MAT_HANG", "classifies", "1", "0..N"),
            ("DON_VI_TINH", "MAT_HANG", "assigns", "1", "0..N"),
            ("MAT_HANG", "SAN_PHAM_GIA_CONG", "ISA — product_kind", "1", "0..1"),
            ("MAT_HANG", "SAN_PHAM_THUONG_MAI", "ISA — product_kind", "1", "0..1"),
            ("MAT_HANG", "VAT_TU", "ISA — product_kind", "1", "0..1"),
            ("MAT_HANG", "BAN_THANH_PHAM", "ISA — product_kind", "1", "0..1"),
            ("NHA_CUNG_CAP", "BANG_GIA_NCC", "issues", "1", "0..N"),
            ("MAT_HANG", "BANG_GIA_NCC", "is quoted for", "1", "0..N"),
            ("DON_VI_TINH", "BANG_GIA_NCC", "converts", "1", "0..N"),
            ("VAT_TU", "MAT_HANG", "produces (phế liệu)", "0..N", "0..1"),
            ("SAN_PHAM_GIA_CONG", "VAT_TU", "made of (vật liệu chính)", "0..N", "0..1"),
            ("BAN_THANH_PHAM", "VAT_TU", "cut from (vật liệu gốc)", "0..N", "0..1"),
        ],
    ),
    dict(
        name="2. Kỹ thuật (BOM & Bản vẽ)",
        cols=[["SAN_PHAM_GIA_CONG", "BAN_THANH_PHAM", "VAT_TU"],
              ["BAN_VE", "DINH_MUC"],
              ["DONG_VAT_TU", "DONG_CONG_DOAN"],
              ["CONG_DOAN", "NHA_CUNG_CAP", "DON_VI_TINH", "CAU_HINH_GIA"]],
        edge=["SAN_PHAM_GIA_CONG", "BAN_THANH_PHAM", "VAT_TU", "NHA_CUNG_CAP",
              "DON_VI_TINH", "CAU_HINH_GIA"],
        rels=[
            ("SAN_PHAM_GIA_CONG", "BAN_VE", "references", "1", "0..N"),
            ("BAN_THANH_PHAM", "BAN_VE", "references", "1", "0..N"),
            ("SAN_PHAM_GIA_CONG", "DINH_MUC", "produces", "1", "0..N"),
            ("BAN_THANH_PHAM", "DINH_MUC", "produces", "1", "0..N"),
            ("BAN_VE", "DINH_MUC", "references", "0..1", "0..N"),
            ("DINH_MUC", "DONG_VAT_TU", "contains", "1", "N"),
            ("DINH_MUC", "DONG_CONG_DOAN", "contains", "1", "0..N"),
            ("VAT_TU", "DONG_VAT_TU", "consumes", "1", "0..N"),
            ("BAN_THANH_PHAM", "DONG_VAT_TU", "consumes", "0..1", "0..N"),
            ("DON_VI_TINH", "DONG_VAT_TU", "converts", "1", "0..N"),
            ("CONG_DOAN", "DONG_CONG_DOAN", "references", "1", "0..N"),
            ("NHA_CUNG_CAP", "DONG_CONG_DOAN", "performs (thuê ngoài)", "0..1", "0..N"),
            ("DONG_CONG_DOAN", "DONG_VAT_TU", "checks (N:M)", "0..N", "0..N"),
            ("CAU_HINH_GIA", "DONG_CONG_DOAN", "prices", "1", "0..N"),
        ],
    ),
    dict(
        name="3. Kinh doanh (RFQ → Báo giá)",
        cols=[["KHACH_HANG", "NGUOI_DUNG", "NHOM_SAN_PHAM",
               "SAN_PHAM_GIA_CONG", "SAN_PHAM_THUONG_MAI"],
              ["RFQ", "DONG_RFQ"],
              ["BAO_GIA"],
              ["DONG_BAO_GIA", "MAT_HANG", "DINH_MUC"]],
        edge=["KHACH_HANG", "NGUOI_DUNG", "NHOM_SAN_PHAM", "SAN_PHAM_GIA_CONG",
              "SAN_PHAM_THUONG_MAI", "MAT_HANG", "DINH_MUC"],
        rels=[
            ("KHACH_HANG", "RFQ", "requests", "1", "0..N"),
            ("NGUOI_DUNG", "RFQ", "created_by (Kinh doanh)", "1", "0..N"),
            ("NGUOI_DUNG", "RFQ", "assigned_to (Kỹ thuật)", "0..1", "0..N"),
            ("RFQ", "DONG_RFQ", "contains", "1", "N"),
            ("NHOM_SAN_PHAM", "DONG_RFQ", "classifies", "0..1", "0..N"),
            ("SAN_PHAM_GIA_CONG", "DONG_RFQ", "resolves (SP xác định)", "0..1", "0..N"),
            ("SAN_PHAM_THUONG_MAI", "DONG_RFQ", "selects (dòng thương mại)", "0..1", "0..N"),
            ("DINH_MUC", "DONG_RFQ", "references (BOM tham chiếu)", "0..1", "0..N"),
            ("RFQ", "BAO_GIA", "generates", "1", "0..N"),
            ("KHACH_HANG", "BAO_GIA", "receives", "1", "0..N"),
            ("BAO_GIA", "BAO_GIA", "supersedes (phiên bản)", "0..1", "0..N"),
            ("BAO_GIA", "DONG_BAO_GIA", "contains", "1", "N"),
            ("DONG_RFQ", "DONG_BAO_GIA", "generates", "1", "0..1"),
            ("MAT_HANG", "DONG_BAO_GIA", "is quoted as", "0..1", "0..N"),
            ("DINH_MUC", "DONG_BAO_GIA", "snapshot BOM", "0..1", "0..N"),
        ],
    ),
    dict(
        name="4. Chốt đơn & Giải trình giá (snapshot)",
        cols=[["BAO_GIA", "DONG_BAO_GIA", "MAT_HANG", "DINH_MUC"],
              ["CAU_PHAN_GIA"],
              ["DON_BAN_HANG", "KHACH_HANG", "CONG_TY"],
              ["DONG_DON"]],
        edge=["BAO_GIA", "DONG_BAO_GIA", "MAT_HANG", "DINH_MUC", "KHACH_HANG",
              "CONG_TY"],
        rels=[
            ("BAO_GIA", "CAU_PHAN_GIA", "contains", "1", "N"),
            ("DONG_BAO_GIA", "CAU_PHAN_GIA", "explains", "1", "N"),
            ("MAT_HANG", "CAU_PHAN_GIA", "references", "0..1", "0..N"),
            ("BAO_GIA", "DON_BAN_HANG", "converts", "1", "0..1"),
            ("KHACH_HANG", "DON_BAN_HANG", "signs", "1", "0..N"),
            ("CONG_TY", "DON_BAN_HANG", "issues", "1", "0..N"),
            ("DON_BAN_HANG", "DONG_DON", "contains", "1", "N"),
            ("DONG_BAO_GIA", "DONG_DON", "converts", "1", "0..1"),
            ("MAT_HANG", "DONG_DON", "is sold as", "0..1", "0..N"),
            ("DINH_MUC", "DONG_DON", "locks BOM", "0..1", "0..N"),
        ],
    ),
    dict(
        name="5. Cấu hình giá, Phê duyệt & Phân quyền",
        cols=[["NHOM_SAN_PHAM", "VAT_TU", "CONG_DOAN", "KHACH_HANG"],
              ["CAU_HINH_GIA", "MA_TRAN"],
              ["YC_PHE_DUYET", "CAU_PHAN_GIA"],
              ["NGUOI_DUNG", "VAI_TRO", "CONG_TY", "BAO_GIA", "DONG_BAO_GIA"]],
        edge=["NHOM_SAN_PHAM", "VAT_TU", "CONG_DOAN", "KHACH_HANG", "BAO_GIA",
              "DONG_BAO_GIA", "CAU_PHAN_GIA"],
        rels=[
            ("NHOM_SAN_PHAM", "CAU_HINH_GIA", "assigns (hao hụt)", "0..1", "0..N"),
            ("VAT_TU", "CAU_HINH_GIA", "assigns (hao hụt)", "0..1", "0..N"),
            ("CONG_DOAN", "CAU_HINH_GIA", "assigns (đơn giá)", "0..1", "0..N"),
            ("KHACH_HANG", "CAU_HINH_GIA", "references (chiết khấu)", "0..N", "0..1"),
            ("CAU_HINH_GIA", "DONG_BAO_GIA", "calculates", "1", "0..N"),
            ("CAU_HINH_GIA", "CAU_PHAN_GIA", "issues", "1", "0..N"),
            ("CAU_HINH_GIA", "YC_PHE_DUYET", "requests", "1", "0..N"),
            ("MA_TRAN", "MA_TRAN", "revision_of", "0..1", "0..N"),
            ("MA_TRAN", "BAO_GIA", "routes", "1", "0..N"),
            ("MA_TRAN", "YC_PHE_DUYET", "issues", "1", "0..N"),
            ("BAO_GIA", "YC_PHE_DUYET", "requests", "1", "0..N"),
            ("NGUOI_DUNG", "YC_PHE_DUYET", "approves", "1", "0..N"),
            ("NGUOI_DUNG", "VAI_TRO", "assigns (N:M)", "0..N", "0..N"),
            ("NGUOI_DUNG", "NGUOI_DUNG", "backup_approver", "0..1", "0..N"),
            ("CONG_TY", "CAU_HINH_GIA", "assigns", "1", "0..N"),
            ("CONG_TY", "BAO_GIA", "issues", "1", "0..N"),
        ],
    ),
]

# ---------------------------------------------------------------- render
SW = ("swimlane;html=1;startSize={h};fontStyle=1;fontSize=11;align=center;"
      "childLayout=stackLayout;horizontal=1;horizontalStack=0;resizeParent=0;"
      "resizeParentMax=0;collapsible=0;marginBottom=0;whiteSpace=wrap;"
      "fillColor=none;")
SW_EDGE = ("rounded=0;whiteSpace=wrap;html=1;dashed=1;fontSize=11;fontStyle=2;"
           "fillColor=#F5F5F5;strokeColor=#9E9E9E;fontColor=#616161;")
ROW = ("text;html=1;strokeColor=none;fillColor=none;align=left;"
       "verticalAlign=middle;spacingLeft=8;spacingRight=6;overflow=hidden;"
       "points=[[0,0.5],[1,0.5]];portConstraint=eastwest;fontSize=10;")
NAMEBOX = "rounded=0;whiteSpace=wrap;html=1;fontSize=11;fontStyle=1;fillColor=none;"
CONTAINER = ("rounded=1;whiteSpace=wrap;html=1;fillColor=none;dashed=1;"
             "strokeColor=#9E9E9E;verticalAlign=top;fontSize=12;fontStyle=1;"
             "fontColor=#616161;")
EDGE = ("edgeStyle=entityRelationEdgeStyle;rounded=0;html=1;fontSize=10;"
        "startArrow={s};startFill=0;endArrow={e};endFill=0;")
TITLE = ("text;html=1;strokeColor=none;fillColor=none;align=left;"
         "verticalAlign=middle;fontSize=16;fontStyle=1;")
NOTE = ("text;html=1;strokeColor=none;fillColor=none;align=left;"
        "verticalAlign=top;fontSize=10;fontColor=#616161;whiteSpace=wrap;")


def esc(s):
    return html.escape(s, quote=True).replace("\n", "&#10;")


def label(text):
    """Nhãn nhiều dòng cho header entity."""
    parts = text.split("\n")
    out = "<b>%s</b>" % html.escape(parts[0])
    if len(parts) > 1:
        out += "<br><i style='font-weight:normal;font-size:9px'>%s</i>" % \
            html.escape(parts[1])
    return html.escape(out, quote=True)


class Doc:
    def __init__(self):
        self.n = 0

    def nid(self, p):
        self.n += 1
        return "%s%d" % (p, self.n)


def entity_cell(doc, key, x, y, as_edge):
    name, attrs = E[key]
    cells = []
    if as_edge:
        h = 56
        cells.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
            '          <mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry" />\n'
            '        </mxCell>\n'
            % (key, label(name + "\n(entity biên)"), SW_EDGE, x, y, BOX_W, h))
        return "".join(cells), h
    h = HEAD_H + ROW_H * len(attrs)
    cells.append(
        '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
        '          <mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry" />\n'
        '        </mxCell>\n'
        % (key, label(name), SW.format(h=HEAD_H), x, y, BOX_W, h))
    for i, a in enumerate(attrs):
        pk = a.startswith("*")
        txt = a[1:] if pk else a
        val = "<u>%s</u>" % html.escape(txt) if pk else html.escape(txt)
        cells.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">\n'
            '          <mxGeometry y="%d" width="%d" height="%d" as="geometry" />\n'
            '        </mxCell>\n'
            % (doc.nid("a"), html.escape(val, quote=True), ROW, key,
               HEAD_H + i * ROW_H, BOX_W, ROW_H))
    return "".join(cells), h


def edge_cell(doc, src, tgt, lbl, cs, ct):
    style = EDGE.format(s=ARROW[cs], e=ARROW[ct])
    if src == tgt:
        style += "exitX=1;exitY=0.25;exitDx=0;exitDy=0;entryX=1;entryY=0.75;entryDx=0;entryDy=0;"
    return ('        <mxCell id="%s" value="%s" style="%s" edge="1" parent="1" '
            'source="%s" target="%s">\n'
            '          <mxGeometry relative="1" as="geometry" />\n'
            '        </mxCell>\n'
            % (doc.nid("e"), esc(lbl), style, src, tgt))


def render_page(doc, page, idx):
    body = []
    body.append('        <mxCell id="t" value="%s" style="%s" vertex="1" '
                'parent="1">\n          <mxGeometry x="40" y="0" width="900" '
                'height="30" as="geometry" />\n        </mxCell>\n'
                % (esc("Conceptual ERD — DLM-ERP · " + page["name"]), TITLE))
    if page.get("overview"):
        x = LEFT
        for gname, keys in GROUPS:
            y = TOP + 30
            for k in keys:
                body.append(
                    '        <mxCell id="%s" value="%s" style="%s" vertex="1" '
                    'parent="1">\n          <mxGeometry x="%d" y="%d" '
                    'width="%d" height="%d" as="geometry" />\n'
                    '        </mxCell>\n'
                    % (k, label(E[k][0]), NAMEBOX, x + 15, y, BOX_W - 30, 44))
                y += 44 + 26
            body.insert(1,
                        '        <mxCell id="%s" value="%s" style="%s" '
                        'vertex="1" parent="1">\n          <mxGeometry x="%d" '
                        'y="%d" width="%d" height="%d" as="geometry" />\n'
                        '        </mxCell>\n'
                        % (doc.nid("g"), esc("Nhóm " + gname), CONTAINER, x,
                           TOP, BOX_W, y - TOP + 10))
            x += COL_GAP
        body.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
            '          <mxGeometry x="40" y="%d" width="1420" height="60" as="geometry" />\n'
            '        </mxCell>\n'
            % (doc.nid("n"), esc(
                "Sơ đồ tổng thể chỉ hiển thị tên thực thể và các quan hệ chính. "
                "Attribute đầy đủ xem ở 5 sub-ERD. Ký hiệu chân quạ (crow's foot): "
                "|| = đúng một · O| = không hoặc một · |< = một hoặc nhiều · O< = không hoặc nhiều. "
                "ISA = quan hệ phân lớp cha/con."), NOTE, TOP + 640))
    else:
        edge_keys = set(page.get("edge", []))
        for ci, col in enumerate(page["cols"]):
            x = LEFT + ci * COL_GAP
            y = TOP
            for k in col:
                cell, h = entity_cell(doc, k, x, y, k in edge_keys)
                body.append(cell)
                y += h + ROW_GAP
        body.append(
            '        <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">\n'
            '          <mxGeometry x="40" y="%d" width="1240" height="50" as="geometry" />\n'
            '        </mxCell>\n'
            % (doc.nid("n"), esc(
                "Hộp nét đứt xám = entity biên (thuộc sơ đồ khác, chỉ vẽ để nối quan hệ). "
                "Thuộc tính gạch chân = định danh. Quan hệ chỉ được vẽ một lần, ở sơ đồ chủ sở hữu."),
               NOTE, TOP + 940))
    for r in page["rels"]:
        body.append(edge_cell(doc, *r))
    return ('  <diagram id="erd%d" name="%s">\n'
            '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
            'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" '
            'pageScale="1" pageWidth="1600" pageHeight="1100" math="0" shadow="0">\n'
            '      <root>\n        <mxCell id="0" />\n'
            '        <mxCell id="1" parent="0" />\n%s'
            '      </root>\n    </mxGraphModel>\n  </diagram>\n'
            % (idx, esc(page["name"]), "".join(body)))


def main():
    doc = Doc()
    out = ['<mxfile host="Electron">\n']
    for i, p in enumerate(PAGES):
        out.append(render_page(doc, p, i))
    out.append("</mxfile>\n")
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "DLM-ERP_Conceptual_ERD.drawio")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print("written:", path)
    print("pages:", len(PAGES))
    print("entities:", len(E))
    print("relations:", sum(len(p["rels"]) for p in PAGES))


if __name__ == "__main__":
    main()
