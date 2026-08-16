# -*- coding: utf-8 -*-
"""Sinh docs/erd/DLM-ERP_Physical_ERD.drawio tu DLM-ERP_Physical_ERD.md."""
import re, html, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "erd", "DLM-ERP_Physical_ERD.md")
OUT = os.path.join(ROOT, "docs", "erd", "DLM-ERP_Physical_ERD.drawio")

md = open(SRC, encoding="utf-8").read().splitlines()

# ---------------------------------------------------------------- parse §5
HEAD5 = re.compile(r"^#{3,4} 5\.[\d.]+\.\s+`([a-z0-9_]+)`")
HEAD5_NONAME = re.compile(r"^#{3,4} 5\.[\d.]+\.")
HEADX = re.compile(r"^#{2,4} ")

cols = {}          # table -> list of (name, type, pk, fk_target, uniq)
mixin_rule = []
cur, buf = None, []


def parse_rows(lines):
    out = []
    for ln in lines:
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 6 or c[0].startswith("---") or c[0] == "Column":
            continue
        name = c[0].strip("`")
        typ = re.sub(r"`", "", c[1])
        pk = "✅" in c[3]
        fk = ""
        m = re.search(r"`([a-z0-9_]+)\(id\)`", c[4])
        if m:
            fk = m.group(1)
        uniq = "✅" in c[5]
        out.append((name, typ, pk, fk, uniq))
    return out


def flush():
    global cur, buf
    if cur is not None:
        cols.setdefault(cur, []).extend(parse_rows(buf))
    cur, buf = None, []


i = 0
in5 = False
while i < len(md):
    ln = md[i]
    if ln.startswith("## 5."):
        in5 = True
    elif ln.startswith("## 6."):
        flush()
        in5 = False
    elif in5:
        m = HEAD5.match(ln)
        if m:
            flush()
            cur = m.group(1)
        elif HEAD5_NONAME.match(ln):          # 5.8 mixin block / 5.30 transient
            flush()
            cur = "__MIXIN__" if ln.startswith("### 5.8.") else None
        elif HEADX.match(ln):
            flush()
        elif cur:
            buf.append(ln)
    i += 1
flush()

RULE_TABLES = ["dl_pricing_waste_rule", "dl_pricing_operation_rule",
               "dl_pricing_cost_adjustment_rule", "dl_pricing_profit_rule",
               "dl_pricing_discount_rule", "dl_pricing_approval_matrix"]
mixin = cols.pop("__MIXIN__", [])
for t in RULE_TABLES:
    cols[t] = mixin + cols.get(t, [])
cols.pop(None, None)

# ------------------------------------------- cot cua bang Odoo mo rong (§2)
cols["res_partner"] = [
    ("id", "integer", True, "", True),
    ("name / vat / phone / email", "varchar", False, "", False),
    ("partner_role", "varchar", False, "", False),
    ("partner_type", "varchar", False, "", False),
    ("dlm_code", "varchar", False, "", True),
    ("pending_link_partner_id", "integer", False, "res_partner", False),
    ("dlm_allow_dup_tax", "boolean", False, "", False),
    ("dlm_has_photo", "boolean", False, "", False),
    ("dlm_customer_group", "varchar", False, "", False),
]
cols["res_users"] = [
    ("id", "integer", True, "", True),
    ("login", "varchar", False, "", True),
    ("partner_id", "integer", False, "res_partner", False),
    ("dl_backup_approver_id", "integer", False, "res_users", False),
]
cols["product_product"] = [
    ("id", "integer", True, "", True),
    ("product_tmpl_id", "integer", False, "product_template", False),
    ("default_code", "varchar", False, "", False),
    ("product_kind", "varchar", False, "", False),
    ("dlm_lifecycle_state", "varchar", False, "", False),
    ("dlm_calc_kind", "varchar", False, "", False),
    ("dlm_stock_length", "numeric", False, "", False),
    ("dlm_sheet_w / dlm_sheet_h", "numeric", False, "", False),
    ("dlm_mass_per_unit/_meter/_sqm", "numeric", False, "", False),
    ("dlm_waste_rate", "numeric", False, "", False),
    ("dlm_has_recovery", "boolean", False, "", False),
    ("dlm_recovery_rate", "numeric", False, "", False),
    ("dlm_scrap_product_id", "integer", False, "product_product", False),
    ("dlm_supplier_price_state", "varchar", False, "", False),
    ("dlm_dim_length/_width/_height", "double", False, "", False),
    ("dlm_thickness / dlm_est_weight", "double", False, "", False),
    ("dlm_main_material_id", "integer", False, "product_product", False),
    ("dlm_finish", "varchar", False, "", False),
    ("is_rfq_provisional", "boolean", False, "", False),
    ("rfq_source_line_id", "integer", False, "dl_quotation_request_line", False),
]
cols["product_category"] = [
    ("id", "integer", True, "", True),
    ("name", "varchar", False, "", False),
    ("parent_id", "integer", False, "product_category", False),
    ("parent_path", "varchar", False, "", False),
    ("active", "boolean", False, "", False),
    ("dl_branch", "varchar", False, "", False),
    ("bom_template_id", "integer", False, "dl_bom_template", False),
]
cols["product_supplierinfo"] = [
    ("id", "integer", True, "", True),
    ("partner_id", "integer", False, "res_partner", False),
    ("product_tmpl_id", "integer", False, "product_template", False),
    ("price / min_qty", "numeric", False, "", False),
    ("date_start", "date NOT NULL", False, "", False),
    ("date_end", "date", False, "", False),
    ("dl_product_kind", "varchar", False, "", False),
    ("approval_state", "varchar", False, "", False),
    ("is_applied", "boolean", False, "", False),
    ("display_state", "varchar", False, "", False),
    ("dlm_approved_uid", "integer", False, "res_users", False),
    ("dlm_applied_uid", "integer", False, "res_users", False),
    ("dlm_unapplied_uid", "integer", False, "res_users", False),
    ("dlm_approved/applied/unapplied_date", "timestamp", False, "", False),
]
# bang goc Odoo dung nguyen trang
cols["product_template"] = [
    ("id", "integer", True, "", True),
    ("name", "varchar", False, "", False),
    ("categ_id", "integer", False, "product_category", False),
    ("uom_id", "integer", False, "uom_uom", False),
    ("list_price", "numeric", False, "", False),
    ("detailed_type / active", "varchar", False, "", False),
]
cols["res_company"] = [("id", "integer", True, "", True), ("name", "varchar", False, "", False),
                       ("currency_id", "integer", False, "res_currency", False)]
cols["res_currency"] = [("id", "integer", True, "", True), ("name", "varchar", False, "", False)]
cols["uom_uom"] = [("id", "integer", True, "", True), ("name", "varchar", False, "", False),
                    ("category_id", "integer", False, "", False), ("factor", "numeric", False, "", False)]
cols["ir_attachment"] = [("id", "integer", True, "", True), ("name", "varchar", False, "", False),
                          ("res_model", "varchar", False, "", False), ("res_field", "varchar", False, "", False),
                          ("res_id", "integer", False, "", False), ("datas / store_fname", "bytea", False, "", False)]
cols["ir_model"] = [("id", "integer", True, "", True), ("model", "varchar", False, "", True)]
cols["res_groups"] = [("id", "integer", True, "", True), ("name", "jsonb", False, "", False)]
cols["ir_property"] = [("id", "integer", True, "", True), ("fields_id", "integer", False, "", False),
                        ("res_id", "varchar", False, "", False), ("value_float", "numeric", False, "", False),
                        ("company_id", "integer", False, "res_company", False)]
# bang M2M
cols["dl_rfq_line_ir_attachment_rel"] = [
    ("line_id", "integer", True, "dl_quotation_request_line", True),
    ("attachment_id", "integer", True, "ir_attachment", True)]
cols["dl_bom_line_dl_bom_operation_line_rel"] = [
    ("dl_bom_operation_line_id", "integer", True, "dl_bom_operation_line", True),
    ("dl_bom_line_id", "integer", True, "dl_bom_line", True)]

# them cot id cho moi bang custom (parse §5 khong co id)
for t, cl in cols.items():
    if not cl or cl[0][0] != "id":
        if not t.endswith("_rel"):
            cols[t] = [("id", "integer", True, "", True)] + cl

# ---------------------------------------------------------------- parse §6
edges = []   # (parent, child, field, card, policy)
in6 = False
for ln in md:
    if ln.startswith("## 6."):
        in6 = True
        continue
    if ln.startswith("## 7."):
        break
    if not in6 or not ln.startswith("|"):
        continue
    c = [x.strip() for x in ln.strip().strip("|").split("|")]
    if len(c) < 5 or c[0].startswith("---") or c[0].startswith("Bảng cha") or c[0].startswith("Chính sách"):
        continue
    parent, child, field, card, pol = c[0], c[1], c[2], c[3], c[4]
    pol = re.sub(r"[*_]", "", pol).strip()
    if "↔" in parent:                       # dong M2M
        left, right = [x.strip().strip("`") for x in parent.split("↔")]
        rel = child.strip("`")
        edges.append((left, rel, re.sub(r"`", "", field).split(",")[0].strip(), "1 — *", "CASCADE"))
        edges.append((right, rel, re.sub(r"`", "", field).split(",")[-1].strip(), "1 — *", "CASCADE"))
        continue
    if "6 bảng rule" in child:               # res_company -> 8 bang
        for t in RULE_TABLES + ["dl_pricing_approval_setting", "dl_pricing_approval_request"]:
            edges.append(("res_company", t, "company_id", "1 — *", "RESTRICT"))
        continue
    parent, child = parent.strip("`"), child.strip("`")
    fields = [f.strip().strip("`") for f in re.sub(r"`", "", field).split("/")]
    card = re.sub(r"\*\((.*?)\)\*", r"(\1)", card).replace("----", "—")
    card = re.sub(r"\s*×\d+", "", card).strip()
    for f in fields:
        f = re.sub(r"\s*\(.*?\)\s*", "", f).strip()
        if f:
            edges.append((parent, child, f, card, pol))

# ------------------------------------------------------------ module / mau
MODULE = {}
for t in ["dl_rbac_feature", "dl_rbac_operation"]:
    MODULE[t] = "dl_base"
for t in ["dl_pricing_config", "dl_pricing_waste", "dl_approval_level", "dl_config_audit_log",
          "dl_pricing_complexity_level", "dl_pricing_operation", "dl_pricing_approval_setting",
          "dl_pricing_approval_request"] + RULE_TABLES:
    MODULE[t] = "dl_config"
for t in ["dl_measurement_type", "dl_measurement_shape", "dl_measurement_shape_param"]:
    MODULE[t] = "dl_product"
for t in ["dl_drawing", "dl_bom", "dl_bom_line", "dl_bom_operation_line", "dl_bom_template",
          "dl_bom_template_line", "dl_bom_template_param", "dl_bom_template_line_param_map",
          "dl_quotation_request", "dl_quotation_request_line", "dl_quotation_request_line_image"]:
    MODULE[t] = "dl_technical"
for t in ["dl_quotation", "dl_quotation_line", "dl_quotation_price_component",
          "dl_sale_order", "dl_sale_order_line"]:
    MODULE[t] = "dl_sale"
for t in ["product_product", "product_category", "product_supplierinfo"]:
    MODULE[t] = "odoo_ext_product"
for t in ["res_partner", "res_users"]:
    MODULE[t] = "odoo_ext_partner"
for t in ["product_template", "res_company", "res_currency", "uom_uom", "ir_attachment",
          "ir_model", "res_groups", "ir_property"]:
    MODULE[t] = "odoo_core"
for t in ["dl_rfq_line_ir_attachment_rel", "dl_bom_line_dl_bom_operation_line_rel"]:
    MODULE[t] = "m2m"

STYLE = {
    "dl_base":          ("#E1D5E7", "#9673A6", "#4B286D"),
    "dl_config":        ("#FFE6CC", "#D79B00", "#7F5200"),
    "dl_product":       ("#D5E8D4", "#82B366", "#38571A"),
    "dl_technical":     ("#DAE8FC", "#6C8EBF", "#1F3D63"),
    "dl_sale":          ("#FFF2CC", "#D6B656", "#7A5C00"),
    "odoo_ext_product": ("#D0F0E0", "#4CA37E", "#1C5C42"),
    "odoo_ext_partner": ("#FFE0E6", "#C06C84", "#7A2E42"),
    "odoo_core":        ("#F0F0F0", "#9E9E9E", "#3C3C3C"),
    "m2m":              ("#F8CECC", "#B85450", "#7A1F1C"),
}
LABEL = {
    "dl_base": "dl_base", "dl_config": "dl_config", "dl_product": "dl_product",
    "dl_technical": "dl_technical", "dl_sale": "dl_sale",
    "odoo_ext_product": "Odoo mở rộng — Sản phẩm", "odoo_ext_partner": "Odoo mở rộng — Đối tác",
    "odoo_core": "Odoo lõi (không sửa)", "m2m": "Bảng nối Many2many",
}

# ------------------------------------------------------------------ layout
LAYOUT = [   # (x, [tables tu tren xuong])
    (40,   ["ir_model", "res_groups", "dl_rbac_feature", "dl_rbac_operation",
            "res_company", "res_currency", "uom_uom", "ir_property", "ir_attachment"]),
    (400,  ["res_partner", "res_users", "dl_config_audit_log", "dl_pricing_config",
            "dl_pricing_waste", "dl_approval_level", "dl_pricing_complexity_level",
            "dl_pricing_operation"]),
    (760,  ["dl_pricing_waste_rule", "dl_pricing_operation_rule",
            "dl_pricing_cost_adjustment_rule", "dl_pricing_profit_rule"]),
    (1120, ["dl_pricing_discount_rule", "dl_pricing_approval_matrix",
            "dl_pricing_approval_setting", "dl_pricing_approval_request"]),
    (1480, ["product_template", "product_category", "product_supplierinfo",
            "dl_measurement_type", "dl_measurement_shape", "dl_measurement_shape_param"]),
    (1840, ["product_product", "dl_drawing", "dl_bom_template", "dl_bom_template_line",
            "dl_bom_template_param", "dl_bom_template_line_param_map"]),
    (2200, ["dl_bom", "dl_bom_line", "dl_bom_operation_line",
            "dl_bom_line_dl_bom_operation_line_rel", "dl_rfq_line_ir_attachment_rel"]),
    (2560, ["dl_quotation_request", "dl_quotation_request_line",
            "dl_quotation_request_line_image"]),
    (2920, ["dl_quotation", "dl_quotation_line", "dl_quotation_price_component"]),
    (3280, ["dl_sale_order", "dl_sale_order_line"]),
]
placed = [t for _, g in LAYOUT for t in g]
missing = [t for t in cols if t not in placed]
if missing:
    LAYOUT.append((3640, missing))

W, HDR, ROW, GAP, TOP = 320, 30, 18, 46, 120

cells = []
cid = 2
node_id = {}


def esc(s):
    return html.escape(s, quote=True)


for x, group in LAYOUT:
    y = TOP
    for t in group:
        cl = cols.get(t, [])
        mod = MODULE.get(t, "odoo_core")
        fill, stroke, fg = STYLE[mod]
        h = HDR + ROW * len(cl) + 6
        lines = []
        for (n, ty, pk, fk, uq) in cl:
            mark = "PK" if pk else ("FK" if fk else ("U" if uq else ""))
            deco = "b" if pk else ("i" if fk else None)
            nm = n
            if deco:
                nm = "<%s>%s</%s>" % (deco, nm, deco)
            badge = ("<span style='color:#B85450'>&nbsp;%s</span>" % mark) if mark else ""
            lines.append("<div style='padding:1px 6px'>%s%s <span style='color:#777'>: %s</span></div>"
                         % (nm, badge, ty))
        label = ("<div style='font-weight:bold;padding:5px;text-align:center;"
                 "border-bottom:1px solid %s'>%s</div>%s" % (stroke, t, "".join(lines)))
        style = ("rounded=0;whiteSpace=wrap;html=1;verticalAlign=top;align=left;overflow=hidden;"
                 "fillColor=%s;strokeColor=%s;fontColor=%s;fontSize=10;strokeWidth=1.5;" % (fill, stroke, fg))
        node_id[t] = str(cid)
        cells.append('<mxCell id="%d" value="%s" style="%s" vertex="1" parent="1">'
                     '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/></mxCell>'
                     % (cid, html.escape(label, quote=True), style, x, y, W, h))
        cid += 1
        y += h + GAP

# ------------------------------------------------------------------- edges
POL_STYLE = {
    "CASCADE":  "strokeColor=#B85450;",
    "RESTRICT": "strokeColor=#2D7600;",
    "SET NULL": "strokeColor=#7A7A7A;dashed=1;",
}
seen = set()
for (p, c, f, card, pol) in edges:
    if p not in node_id or c not in node_id:
        continue
    key = (p, c, f)
    if key in seen:
        continue
    seen.add(key)
    pol_key = next((k for k in POL_STYLE if k in pol.upper()), None)
    ex = POL_STYLE.get(pol_key, "strokeColor=#7A7A7A;")
    style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
             "endArrow=ERmany;endFill=0;startArrow=ERone;startFill=0;fontSize=9;fontColor=#444444;"
             + ex + ("" if p != c else "curved=1;"))
    lbl = esc("%s (%s)" % (f, pol_key or pol))
    cells.append('<mxCell id="%d" value="%s" style="%s" edge="1" parent="1" source="%s" target="%s">'
                 '<mxGeometry relative="1" as="geometry"/></mxCell>'
                 % (cid, lbl, style, node_id[p], node_id[c]))
    cid += 1

# ----------------------------------------------------------------- chu giai
lx, ly = 40, TOP - 100
cells.append('<mxCell id="%d" value="DLM-ERP — PHYSICAL ERD (Database Diagram) — PostgreSQL 16 / Odoo 17" '
             'style="text;html=1;fontSize=26;fontStyle=1;align=left;fontColor=#1F3D63;" vertex="1" parent="1">'
             '<mxGeometry x="40" y="20" width="1200" height="40" as="geometry"/></mxCell>' % cid)
cid += 1
lgx = 40
for mod, (fill, stroke, fg) in STYLE.items():
    cells.append('<mxCell id="%d" value="%s" style="rounded=0;html=1;fontSize=11;fontStyle=1;'
                 'fillColor=%s;strokeColor=%s;fontColor=%s;" vertex="1" parent="1">'
                 '<mxGeometry x="%d" y="70" width="200" height="30" as="geometry"/></mxCell>'
                 % (cid, esc(LABEL[mod]), fill, stroke, fg, lgx))
    cid += 1
    lgx += 210
for i, (txt, st) in enumerate([("ON DELETE CASCADE", "strokeColor=#B85450;"),
                               ("ON DELETE RESTRICT", "strokeColor=#2D7600;"),
                               ("ON DELETE SET NULL", "strokeColor=#7A7A7A;dashed=1;")]):
    cells.append('<mxCell id="%d" value="%s" style="html=1;fontSize=11;endArrow=ERmany;endFill=0;'
                 'startArrow=ERone;startFill=0;%s" edge="1" parent="1">'
                 '<mxGeometry relative="1" as="geometry">'
                 '<mxPoint x="%d" y="45" as="sourcePoint"/><mxPoint x="%d" y="45" as="targetPoint"/>'
                 '</mxGeometry></mxCell>' % (cid, txt, st, 2000 + i * 260, 2130 + i * 260))
    cid += 1

xml = ('<mxfile host="app.diagrams.net" version="24.0.0">\n'
       '  <diagram id="dlm-physical-erd" name="DLM-ERP Physical ERD">\n'
       '    <mxGraphModel dx="1800" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
       'arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="826" math="0" shadow="0">\n'
       '      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n        '
       + "\n        ".join(cells) +
       '\n      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n')

open(OUT, "w", encoding="utf-8").write(xml)
print("tables:", len(cols), "| placed:", len(node_id), "| edges:", len(seen))
print("missing:", missing)
print("->", OUT)
