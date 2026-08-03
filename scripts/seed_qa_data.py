# -*- coding: utf-8 -*-
"""Seed du lieu QA/test cho DLM-ERP (Odoo 17).

Chay qua Odoo registry truc tiep (khong can HTTP server dang chay):

    C:\\odoo17\\odoo\\venv\\Scripts\\python.exe seed_qa_data.py

Idempotent: moi ban ghi "nghiep vu" (user, doi tac, san pham, BOM, bang gia NCC,
bao gia, don ban hang) duoc gan 1 external ID on dinh trong module gia
"dlm_qa_seed" (bang ir.model.data). Lan chay sau neu external ID da ton tai:
  - Du lieu "master" don gian (user/doi tac/san pham/danh muc/bang gia NCC):
    UPDATE lai gia tri (an toan, khong workflow).
  - Du lieu co state-machine + side-effect (BOM/bao gia/don ban hang): BO QUA
    hoan toan (khong goi lai action_*, tranh loi "sai trang thai hien tai").

Chay lai nhieu lan se KHONG tao trung, KHONG loi khoa trung.
"""

import sys

import odoo
from odoo.api import Environment

DB_NAME = "dlm_dev"
CONF_PATH = r"C:\odoo17\odoo\odoo.conf"
SEED_MODULE = "dlm_qa_seed"

odoo.tools.config.parse_config(["-c", CONF_PATH, "-d", DB_NAME])

REPORT = []  # list of (section, label, value) for final summary


def note(section, label, value=""):
    REPORT.append((section, label, value))
    print("[%s] %s %s" % (section, label, value))


# ---------------------------------------------------------------------------
# Idempotency helpers (external ID trong module gia SEED_MODULE)
# ---------------------------------------------------------------------------

def _find(env, xmlid):
    module, name = xmlid.split(".", 1)
    IMD = env["ir.model.data"].sudo()
    data = IMD.search([("module", "=", module), ("name", "=", name)], limit=1)
    if data and data.res_id:
        rec = env[data.model].sudo().browse(data.res_id)
        if rec.exists():
            return rec
    return None


def _bind(env, xmlid, record):
    module, name = xmlid.split(".", 1)
    IMD = env["ir.model.data"].sudo()
    data = IMD.search([("module", "=", module), ("name", "=", name)], limit=1)
    if data:
        data.write({"model": record._name, "res_id": record.id})
    else:
        IMD.create({
            "module": module, "name": name,
            "model": record._name, "res_id": record.id,
            "noupdate": False,
        })


def upsert(env, xmlid, model_name, values):
    """Master data don gian: tao moi hoac UPDATE lai gia tri theo external ID."""
    rec = _find(env, xmlid)
    if rec:
        rec.write(values)
        return rec, False
    rec = env[model_name].sudo().create(values)
    _bind(env, xmlid, rec)
    return rec, True


def once(env, xmlid, build_fn):
    """Du lieu co workflow: neu external ID da ton tai -> BO QUA (tra ve ban ghi
    cu, khong chay lai build_fn). Neu chua co -> chay build_fn() (tao + drive
    workflow) roi gan external ID."""
    rec = _find(env, xmlid)
    if rec:
        return rec, False
    rec = build_fn()
    _bind(env, xmlid, rec)
    return rec, True


# ---------------------------------------------------------------------------
def run(env):
    ref = env.ref
    Users = env["res.users"].sudo()
    Partners = env["res.partner"].sudo()
    Products = env["product.product"].sudo()
    Supplierinfo = env["product.supplierinfo"].sudo()
    Bom = env["dl.bom"].sudo()
    Quotation = env["dl.quotation"].sudo()
    SaleOrder = env["dl.sale.order"].sudo()
    ProfitRule = env["dl.pricing.profit.rule"].sudo()
    DiscountRule = env["dl.pricing.discount.rule"].sudo()

    main_company = ref("base.main_company")
    uom_kg = ref("uom.product_uom_kgm")
    uom_unit = ref("uom.product_uom_unit")

    # =======================================================================
    # PHASE 1 — USERS (7 tai khoan QA khop AGENT_TEST_PLAN_110TC_DLM-ERP.md)
    # =======================================================================
    print("\n=== PHASE 1: USERS ===")
    group_admin = ref("dl_base.dl_group_admin")
    group_ceo = ref("dl_base.dl_group_ceo")
    group_sales_manager = ref("dl_base.dl_group_sales_manager")
    group_ba = ref("dl_base.dl_group_ba")
    group_tech = ref("dl_base.dl_group_tech")
    group_accountant = ref("dl_base.dl_group_accountant")

    USER_SPECS = [
        ("user_admin", "admin@dlm.demo", "QA Admin/IT", group_admin),
        ("user_ceo", "ceo@dlm.demo", "QA CEO", group_ceo),
        ("user_truongkd", "truongkd@dlm.demo", "QA Truong phong Kinh doanh", group_sales_manager),
        ("user_sales1", "sales1@dlm.demo", "QA Sales 1", group_ba),
        ("user_sales2", "sales2@dlm.demo", "QA Sales 2", group_ba),
        ("user_kythuat", "kythuat@dlm.demo", "QA Ky thuat", group_tech),
        ("user_ketoan", "ketoan@dlm.demo", "QA Ke toan noi bo", group_accountant),
    ]
    users = {}
    for key, login, name, group in USER_SPECS:
        rec, created = upsert(env, "%s.%s" % (SEED_MODULE, key), "res.users", {
            "name": name,
            "login": login,
            "email": login,
            "password": "Demo@2026",
            "lang": "vi_VN",
            "groups_id": [(6, 0, [group.id])],
        })
        users[key] = rec
        note("USERS", ("created" if created else "kept"), "%s (%s)" % (login, name))

    u_admin = users["user_admin"]
    u_ceo = users["user_ceo"]
    u_truongkd = users["user_truongkd"]
    u_sales1 = users["user_sales1"]
    u_sales2 = users["user_sales2"]
    u_kythuat = users["user_kythuat"]
    u_ketoan = users["user_ketoan"]

    # =======================================================================
    # PHASE 2 — KHACH HANG (res.partner, partner_role=customer)
    # =======================================================================
    print("\n=== PHASE 2: CUSTOMERS ===")
    CUSTOMER_SPECS = [
        # key, name, partner_type, vat, phone, email, active
        ("cust_ca_nhan_01", "Nguyen Van An", "individual", False, "0901111201", "an.nguyen01@gmail.com", True),
        ("cust_ca_nhan_02", "Tran Thi Bich", "individual", False, "0901111202", "bich.tran02@gmail.com", True),
        ("cust_ca_nhan_03", "Le Hoang Nam", "individual", False, "0901111203", "nam.le03@gmail.com", True),
        ("cust_ca_nhan_04", "Pham Thi Hoa", "individual", False, "0901111204", "hoa.pham04@gmail.com", True),
        ("cust_ca_nhan_05", "Do Minh Quan", "individual", False, "0901111205", "quan.do05@gmail.com", True),
        ("cust_ca_nhan_06_inactive", "Vu Thi Lan", "individual", False, "0901111206", "lan.vu06@gmail.com", False),
        ("cust_dn_01", "Cong ty TNHH Co khi Dai Phat", "company", "0301872563", "0281111301", "kd@daiphat.com.vn", True),
        ("cust_dn_02", "Cong ty CP Xay dung Thanh Do", "company", "0308123456", "0281111302", "info@thanhdo.com.vn", True),
        ("cust_dn_03", "Cong ty TNHH SX Thep Viet Cuong", "company", "0309988771", "0281111303", "sales@vietcuong.com.vn", True),
        ("cust_dn_04", "Cong ty CP Dau tu Kim Long", "company", "0310223344", "0281111304", "contact@kimlong.com.vn", True),
        ("cust_dn_05_inactive", "Cong ty TNHH Noi that Hoa Phat Home", "company", "0311556677", "0281111305", "cs@hoaphathome.com.vn", False),
        ("cust_dn_06", "Cong ty TNHH MTV Co dien Phuong Nam", "company", "0312445566", "0281111306", "info@phuongnam.com.vn", True),
        ("cust_dl_01", "Dai ly Sat thep Mien Dong", "dealer", "0313111222", "0281111401", "daily.miendong@gmail.com", True),
        ("cust_dl_02", "Dai ly VLXD Thanh Binh", "dealer", "0314222333", "0281111402", "daily.thanhbinh@gmail.com", True),
        ("cust_dl_03", "Dai ly Ngu kim Sai Gon", "dealer", "0315333444", "0281111403", "daily.nguukim@gmail.com", True),
        ("cust_dl_04", "Dai ly Co khi Dong Nam Bo", "dealer", "0316444555", "0281111404", "daily.dongnambo@gmail.com", True),
        ("cust_dl_05", "Dai ly Vat tu Cong nghiep An Phat", "dealer", "0317555666", "0281111405", "daily.anphat@gmail.com", True),
        ("cust_dl_06", "Dai ly Kim khi Long Thanh", "dealer", "0318666777", "0281111406", "daily.longthanh@gmail.com", True),
    ]
    customers = {}
    for key, name, ptype, vat, phone, email, active in CUSTOMER_SPECS:
        values = {
            "name": name,
            "partner_role": "customer",
            "partner_type": ptype,
            "phone": phone,
            "email": email,
            "active": active,
            "country_id": ref("base.vn").id,
        }
        if vat:
            values["vat"] = vat
        rec, created = upsert(env, "%s.%s" % (SEED_MODULE, key), "res.partner", values)
        customers[key] = rec
        note("CUSTOMERS", ("created" if created else "kept"),
             "%s [%s] active=%s -> %s" % (rec.dlm_code or "?", ptype, active, name))

    # =======================================================================
    # PHASE 3 — NHA CUNG CAP (res.partner, partner_role=supplier/both)
    # =======================================================================
    print("\n=== PHASE 3: SUPPLIERS ===")
    SUPPLIER_SPECS = [
        ("supp_01", "Cong ty TNHH Thep Mien Nam", "0320111222", "0281112201", "sales@thepmiennam.com.vn", True, "supplier"),
        ("supp_02", "Cong ty CP Kim khi Viet Nhat", "0321222333", "0281112202", "sales@kimkhivietnhat.com.vn", True, "supplier"),
        ("supp_03", "Cong ty TNHH Son Cong nghiep Dong A", "0322333444", "0281112203", "sales@sondonga.com.vn", True, "supplier"),
        ("supp_04_inactive", "Cong ty TNHH Vat tu Han Quang", "0323444555", "0281112204", "sales@hanquang.com.vn", False, "supplier"),
        ("supp_05_both", "Cong ty TNHH TM DV Kim Son", "0324555666", "0281112205", "sales@kimson.com.vn", True, "both"),
    ]
    suppliers = {}
    for key, name, vat, phone, email, active, role in SUPPLIER_SPECS:
        values = {
            "name": name,
            "partner_role": role,
            "vat": vat,
            "phone": phone,
            "email": email,
            "active": active,
            "country_id": ref("base.vn").id,
        }
        if role in ("customer", "both"):
            values["partner_type"] = "company"
        rec, created = upsert(env, "%s.%s" % (SEED_MODULE, key), "res.partner", values)
        suppliers[key] = rec
        note("SUPPLIERS", ("created" if created else "kept"),
             "role=%s active=%s -> %s" % (role, active, name))

    supplier_main = suppliers["supp_01"]
    supplier_alt = suppliers["supp_02"]

    # =======================================================================
    # PHASE 4 — SAN PHAM & VAT TU
    # =======================================================================
    print("\n=== PHASE 4: PRODUCTS & MATERIALS ===")
    categ_finished = ref("dl_product.categ_khung_thep_han")
    categ_ban_ghe = ref("dl_product.categ_ban_ghe_sat")
    categ_mat_sheet = ref("dl_product.material_categ_steel_sheet")
    categ_mat_consumable = ref("dl_product.material_categ_consumable")
    categ_mat_paint = ref("dl_product.material_categ_paint")
    categ_mat_semi = ref("dl_product.material_categ_semi")

    prod_ct500, _c = upsert(env, "%s.prod_ct500" % SEED_MODULE, "product.product", {
        "name": "Khung thep han CT-500 (QA)",
        "default_code": "SP-CT500-QA",
        "product_kind": "manufactured",
        "categ_id": categ_finished.id,
        "uom_id": uom_unit.id,
        "uom_po_id": uom_unit.id,
        "dlm_lifecycle_state": "active",
        "list_price": 0.0,
    })
    prod_ks150, _c = upsert(env, "%s.prod_ks150" % SEED_MODULE, "product.product", {
        "name": "Ke sat de hang KS-150 (QA)",
        "default_code": "SP-KS150-QA",
        "product_kind": "manufactured",
        "categ_id": categ_ban_ghe.id,
        "uom_id": uom_unit.id,
        "uom_po_id": uom_unit.id,
        "dlm_lifecycle_state": "active",
        "list_price": 0.0,
    })
    prod_gx200, _c = upsert(env, "%s.prod_gx200" % SEED_MODULE, "product.product", {
        "name": "Ghe xoay van phong GX-200 (QA)",
        "default_code": "SP-GX200-QA",
        "product_kind": "trading",
        "categ_id": categ_ban_ghe.id,
        "uom_id": uom_unit.id,
        "uom_po_id": uom_unit.id,
        "dlm_lifecycle_state": "active",
        "list_price": 850000.0,
    })
    mat_thep_tam, _c = upsert(env, "%s.mat_thep_tam" % SEED_MODULE, "product.product", {
        "name": "Thep tam CT3 day 3mm (QA)",
        "default_code": "VT-CT3-3-QA",
        "product_kind": "material",
        "categ_id": categ_mat_sheet.id,
        "uom_id": uom_kg.id,
        "uom_po_id": uom_kg.id,
        "dlm_lifecycle_state": "active",
        "dlm_waste_rate": 3.0,
    })
    mat_quehan, _c = upsert(env, "%s.mat_quehan" % SEED_MODULE, "product.product", {
        "name": "Que han 3.2mm (QA)",
        "default_code": "VT-QUEHAN32-QA",
        "product_kind": "material",
        "categ_id": categ_mat_consumable.id,
        "uom_id": uom_kg.id,
        "uom_po_id": uom_kg.id,
        "dlm_lifecycle_state": "active",
        "dlm_waste_rate": 1.0,
    })
    mat_son_no_price, _c = upsert(env, "%s.mat_son_no_price" % SEED_MODULE, "product.product", {
        "name": "Son tinh dien mau den RAL9005 (QA - CHUA CO GIA)",
        "default_code": "VT-SONDEN-QA",
        "product_kind": "material",
        "categ_id": categ_mat_paint.id,
        "uom_id": uom_kg.id,
        "uom_po_id": uom_kg.id,
        "dlm_lifecycle_state": "active",
    })
    btp_kov02, _c = upsert(env, "%s.btp_kov02" % SEED_MODULE, "product.product", {
        "name": "Khung ong vuong da cat KOV-02 (QA - Ban thanh pham)",
        "default_code": "BTP-KOV02-QA",
        "product_kind": "material_processed",
        "categ_id": categ_mat_semi.id,
        "uom_id": uom_unit.id,
        "uom_po_id": uom_unit.id,
        "dlm_lifecycle_state": "active",
    })
    note("PRODUCTS", "manufactured", "%s / %s" % (prod_ct500.default_code, prod_ks150.default_code))
    note("PRODUCTS", "trading", prod_gx200.default_code)
    note("PRODUCTS", "material (co gia sau Phase 5)", "%s / %s" % (mat_thep_tam.default_code, mat_quehan.default_code))
    note("PRODUCTS", "material CHUA CO GIA (khong seed supplierinfo)", mat_son_no_price.default_code)
    note("PRODUCTS", "ban thanh pham (material_processed)", btp_kov02.default_code)

    # Vat tu da co san trong demo data goc (dl_product) - deu dang "chua co gia"
    existing_no_price_materials = []
    for xmlid in ("dl_product.seed_mat_tt_ct3_2", "dl_product.demo_product_thep_cuon",
                  "dl_product.demo_product_oc_vit"):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            existing_no_price_materials.append(rec.default_code)
    note("PRODUCTS", "vat tu co san (demo goc) van CHUA CO GIA", ", ".join(existing_no_price_materials))

    # =======================================================================
    # PHASE 5 — BANG GIA NHA CUNG CAP (product.supplierinfo)
    # =======================================================================
    print("\n=== PHASE 5: SUPPLIER PRICE LISTS ===")
    from datetime import date, timedelta
    today = date.today()

    si_thep_tam, c1 = upsert(env, "%s.si_thep_tam_main" % SEED_MODULE, "product.supplierinfo", {
        "partner_id": supplier_main.id,
        "product_tmpl_id": mat_thep_tam.product_tmpl_id.id,
        "price": 18500.0,
        "currency_id": main_company.currency_id.id,
        "date_start": date(2024, 1, 1),
        "min_qty": 0,
        "approval_state": "approved",
        "is_applied": True,
    })
    si_quehan, c2 = upsert(env, "%s.si_quehan_main" % SEED_MODULE, "product.supplierinfo", {
        "partner_id": supplier_main.id,
        "product_tmpl_id": mat_quehan.product_tmpl_id.id,
        "price": 45000.0,
        "currency_id": main_company.currency_id.id,
        "date_start": date(2024, 1, 1),
        "min_qty": 0,
        "approval_state": "approved",
        "is_applied": True,
    })
    si_thep_tam_draft, c3 = upsert(env, "%s.si_thep_tam_alt_draft" % SEED_MODULE, "product.supplierinfo", {
        "partner_id": supplier_alt.id,
        "product_tmpl_id": mat_thep_tam.product_tmpl_id.id,
        "price": 19000.0,
        "currency_id": main_company.currency_id.id,
        "date_start": date(2024, 6, 1),
        "min_qty": 0,
        "approval_state": "draft",
        "is_applied": False,
    })

    # 1 bang gia SAP HET HAN (validity_state='expiring', <=30 ngay) tren vat tu
    # da co san trong demo goc (dl_product.demo_product_ong_vuong).
    mat_ong_vuong = env.ref("dl_product.demo_product_ong_vuong")
    si_expiring, c4 = upsert(env, "%s.si_ong_vuong_expiring" % SEED_MODULE, "product.supplierinfo", {
        "partner_id": supplier_alt.id,
        "product_tmpl_id": mat_ong_vuong.product_tmpl_id.id,
        "price": 32000.0,
        "currency_id": main_company.currency_id.id,
        "date_start": today - timedelta(days=300),
        "date_end": today + timedelta(days=15),
        "min_qty": 0,
        "approval_state": "approved",
        "is_applied": True,
    })
    # 1 bang gia DRAFT (chua duyet) tren vat tu co san khac.
    mat_th40 = env.ref("dl_product.seed_mat_th_40")
    si_draft2, c5 = upsert(env, "%s.si_th40_draft" % SEED_MODULE, "product.supplierinfo", {
        "partner_id": supplier_main.id,
        "product_tmpl_id": mat_th40.product_tmpl_id.id,
        "price": 21000.0,
        "currency_id": main_company.currency_id.id,
        "date_start": date(2025, 1, 1),
        "min_qty": 0,
        "approval_state": "draft",
        "is_applied": False,
    })
    note("SUPPLIERINFO", "approved+applied (co gia)", "%s, %s" % (mat_thep_tam.default_code, mat_quehan.default_code))
    note("SUPPLIERINFO", "draft (chua duyet)", "%s (NCC phu), %s (NCC chinh)" % (mat_thep_tam.default_code, mat_th40.default_code))
    note("SUPPLIERINFO", "SAP HET HAN (date_end=+15 ngay)", "%s -> id=%s" % (mat_ong_vuong.default_code, si_expiring.id))
    note("SUPPLIERINFO", "LUU Y GAP", "Model chi co 2 trang thai that: draft/approved. Khong co pending/rejected.")

    # =======================================================================
    # PHASE 6 — BOM (dl.bom): 1 CONFIRMED + 1 DRAFT
    # =======================================================================
    print("\n=== PHASE 6: BOM ===")

    def _build_bom_confirmed():
        bom = Bom.create({
            "product_id": prod_ct500.id,
            "category_id": categ_finished.id,
            "bom_type": "quotation",
            "product_qty": 1.0,
            "line_ids": [
                (0, 0, {"material_id": mat_thep_tam.id, "quantity": 10.0}),
                (0, 0, {"material_id": mat_quehan.id, "quantity": 2.0}),
            ],
        })
        bom.action_confirm()
        return bom

    bom_confirmed, created = once(env, "%s.bom_ct500_confirmed" % SEED_MODULE, _build_bom_confirmed)
    note("BOM", ("created+confirmed" if created else "kept"),
         "%s (status=%s) cho san pham %s" % (bom_confirmed.name, bom_confirmed.status, prod_ct500.default_code))

    def _build_bom_draft():
        return Bom.create({
            "product_id": prod_ks150.id,
            "category_id": categ_ban_ghe.id,
            "bom_type": "quotation",
            "product_qty": 1.0,
            "line_ids": [
                (0, 0, {"material_id": mat_thep_tam.id, "quantity": 6.0}),
                (0, 0, {"material_id": mat_quehan.id, "quantity": 1.5}),
            ],
        })

    bom_draft, created = once(env, "%s.bom_ks150_draft" % SEED_MODULE, _build_bom_draft)
    note("BOM", ("created" if created else "kept"),
         "%s (status=%s) cho san pham %s -- DUNG DE TEST RULE CHAN" % (
             bom_draft.name, bom_draft.status, prod_ks150.default_code))

    # =======================================================================
    # PHASE 7 — CAU HINH PRICING (profit rule + discount rule 3 nhom + approval
    # matrix). Approval matrix (dl.pricing.approval.matrix) DA active san co
    # trong pricing_seed.xml (0 / 20.000.001 / 100.000.001) -- khong dong vao.
    # =======================================================================
    print("\n=== PHASE 7: PRICING CONFIG (profit + discount rules) ===")

    # upsert thuong khong dung duoc o day: mot khi rule da duoc 1 bao gia dung
    # lam snapshot (used_in_snapshot=True), mixin khoa write() cac field nghiep
    # vu -> dung "once" (bo qua neu da ton tai) thay vi ghi de.
    def _build_profit_rule():
        return ProfitRule.create({
            "target_markup": 25.0,
            "min_markup": 10.0,
            "state": "active",
            "valid_from": date(2020, 1, 1),
            "company_id": main_company.id,
        })
    profit_rule, created = once(env, "%s.profit_rule_default" % SEED_MODULE, _build_profit_rule)
    note("PRICING", ("created" if created else "kept"),
         "profit_rule target=25%% floor=10%% state=%s" % profit_rule.state)

    DISCOUNT_SPECS = [
        ("discount_rule_new", "new", 5.0, 8.0),
        ("discount_rule_existing", "existing", 8.0, 12.0),
        ("discount_rule_loyal", "loyal", 10.0, 15.0),
    ]
    discount_rules = {}
    for key, group, default_rate, max_rate in DISCOUNT_SPECS:
        def _build_discount_rule(group=group, default_rate=default_rate, max_rate=max_rate):
            return DiscountRule.create({
                "customer_group": group,
                "default_rate": default_rate,
                "max_rate": max_rate,
                "state": "active",
                "valid_from": date(2020, 1, 1),
                "company_id": main_company.id,
            })
        rec, created = once(env, "%s.%s" % (SEED_MODULE, key), _build_discount_rule)
        discount_rules[group] = rec
        note("PRICING", ("created" if created else "kept"),
             "discount_rule[%s] default=%s%% max=%s%%" % (group, default_rate, max_rate))

    matrix_rows = env["dl.pricing.approval.matrix"].sudo().search([
        ("state", "=", "active"), ("company_id", "=", main_company.id),
    ], order="value_from asc")
    note("PRICING", "approval matrix active (co san tu pricing_seed.xml)",
         ", ".join("%s->%s" % (r.value_from, r.approval_level) for r in matrix_rows))

    # =======================================================================
    # PHASE 8 — BAO GIA (dl.quotation) -- DU 10 TRANG THAI + NGUONG DUYET
    # =======================================================================
    print("\n=== PHASE 8: QUOTATIONS ===")

    def make_quote(partner, amount, discount_pct=0.0, name_hint=""):
        quo = Quotation.create({
            "partner_id": partner.id,
            "date_order": today,
            "discount_pct": discount_pct,
        })
        quo.write({
            "line_ids": [(0, 0, {
                "name": name_hint or "Dong hang QA",
                "qty": 1.0,
                "price_unit": amount,
                "line_type": "trading",
            })],
        })
        return quo

    special = {}  # for final report

    # Q1 - draft don gian, khong vuot nguong.
    def _b():
        return make_quote(customers["cust_ca_nhan_01"], 5_000_000, name_hint="Bao gia don gian")
    q1, created = once(env, "%s.quote_draft_small" % SEED_MODULE, _b)
    special["Q_DRAFT (Nhap, khong can duyet)"] = q1

    # Q2 - dung tai 20.000.000 -- VAN la "none" (bien duoi cua nguong Truong KD).
    def _b():
        return make_quote(customers["cust_ca_nhan_02"], 20_000_000, name_hint="Bien duoi nguong Truong KD")
    q2, created = once(env, "%s.quote_boundary_none_20m" % SEED_MODULE, _b)
    special["Q_BOUNDARY_NONE_20M (dung 20.000.000d - KHONG can duyet)"] = q2

    # Q3 - dung tai 20.000.001 -- vuot nguong Truong KD (de nguyen PENDING).
    def _b():
        return make_quote(customers["cust_ca_nhan_03"], 20_000_001, name_hint="Dung nguong Truong KD")
    q3, created = once(env, "%s.quote_boundary_sm_20m_plus1" % SEED_MODULE, _b)
    special["Q_BOUNDARY_SALES_MANAGER (dung 20.000.001d - PENDING Truong KD)"] = q3

    # Q4 - dung tai 100.000.000 -- VAN la Truong KD (bien duoi nguong CEO).
    def _b():
        return make_quote(customers["cust_ca_nhan_04"], 100_000_000, name_hint="Bien duoi nguong CEO")
    q4, created = once(env, "%s.quote_boundary_sm_100m" % SEED_MODULE, _b)
    special["Q_BOUNDARY_100M (dung 100.000.000d - PENDING Truong KD, chua len CEO)"] = q4

    # Q5 - dung tai 100.000.001 -- vuot nguong CEO (de nguyen PENDING).
    def _b():
        return make_quote(customers["cust_ca_nhan_05"], 100_000_001, name_hint="Dung nguong CEO")
    q5, created = once(env, "%s.quote_boundary_ceo_100m_plus1" % SEED_MODULE, _b)
    special["Q_BOUNDARY_CEO (dung 100.000.001d - PENDING CEO)"] = q5

    # Q6 - 30.000.000 (Truong KD) -> Truong KD duyet that -> state=approved.
    def _b():
        quo = make_quote(customers["cust_dn_01"], 30_000_000, name_hint="Can Truong KD duyet")
        req = quo.approval_request_id
        assert req and req.state == "pending", "Q6 khong o trang thai cho duyet nhu ky vong"
        req.with_user(u_truongkd).action_approve()
        return quo
    q6, created = once(env, "%s.quote_approved" % SEED_MODULE, _b)
    special["Q_APPROVED (30.000.000d, Truong KD da duyet that -> Da duyet noi bo)"] = q6

    # Q7 - 8.000.000, khong can duyet -> gui thang cho khach.
    def _b():
        quo = make_quote(customers["cust_dn_02"], 8_000_000, name_hint="Gui khach ngay")
        quo.action_send()
        return quo
    q7, created = once(env, "%s.quote_sent" % SEED_MODULE, _b)
    special["Q_SENT (Da gui khach)"] = q7

    # Q8 - 15.000.000, KH = Thanh Do -> accepted (muc tieu nhom 'Khach cu').
    def _b():
        quo = make_quote(customers["cust_dn_02"], 15_000_000, name_hint="KH dong y - muc tieu Khach cu")
        quo.action_send()
        quo.action_customer_accept()
        return quo
    q8, created = once(env, "%s.quote_accepted" % SEED_MODULE, _b)
    special["Q_ACCEPTED (15.000.000d, Khach dong y, KH=Thanh Do -> se thanh 'Khach cu')"] = q8

    # Q9 - 200.000.000, KH = Dai Phat -> CEO duyet that -> sent -> accepted ->
    # tao Don ban hang (Da len don). Vuot 150tr -> muc tieu 'Khach than thiet'.
    def _b():
        quo = make_quote(customers["cust_dn_01"], 200_000_000, name_hint="CEO duyet - muc tieu Khach than thiet")
        req = quo.approval_request_id
        assert req and req.state == "pending" and req.approval_level == "ceo", (
            "Q9 khong dung nguong CEO nhu ky vong")
        req.with_user(u_ceo).action_approve()
        quo.action_send()
        quo.action_customer_accept()
        quo.action_create_sale_order()
        return quo
    q9, created = once(env, "%s.quote_ordered" % SEED_MODULE, _b)
    special["Q_ORDERED (200.000.000d, CEO da duyet that, KH=Dai Phat -> se thanh 'Khach than thiet')"] = q9

    # Q10 - tu choi, ly do gia cao.
    def _b():
        quo = make_quote(customers["cust_dl_01"], 6_000_000, name_hint="Se tu choi")
        quo._apply_reject("price_high", "Khach phan hoi gia cao hon du kien.")
        return quo
    q10, created = once(env, "%s.quote_rejected" % SEED_MODULE, _b)
    special["Q_REJECTED (tu choi, ly do: Gia cao)"] = q10

    # Q11 - sent -> khach yeu cau dieu chinh (thuong mai/chiet khau).
    def _b():
        quo = make_quote(customers["cust_dl_02"], 7_000_000, name_hint="Se yeu cau dieu chinh")
        quo.action_send()
        quo._apply_revision_request("commercial", "Khach muon them chiet khau 5%.")
        return quo
    q11, created = once(env, "%s.quote_revision_requested" % SEED_MODULE, _b)
    special["Q_REVISION_REQUESTED (Yeu cau dieu chinh - gia/chiet khau)"] = q11

    # Q12 - sent -> het hieu luc.
    def _b():
        quo = make_quote(customers["cust_dl_03"], 9_000_000, name_hint="Se het hieu luc")
        quo.action_send()
        # action_expire() chi kiem tra state, khong kiem tra validity_date thuc
        # te qua han hay chua -- khong can chinh ngay o day.
        quo.action_expire()
        return quo
    q12, created = once(env, "%s.quote_expired" % SEED_MODULE, _b)
    special["Q_EXPIRED (Het hieu luc)"] = q12

    # Q13 - sent -> tao revision (ban goc thanh 'superseded', tu sinh ban -R2).
    def _b():
        quo = make_quote(customers["cust_dl_04"], 8_500_000, name_hint="Se bi thay bang ban moi")
        quo.action_send()
        quo.action_create_revision()
        return quo
    q13, created = once(env, "%s.quote_superseded" % SEED_MODULE, _b)
    special["Q_SUPERSEDED (Da thay bang ban moi -- xem them ban -R2 lien ket)"] = q13

    # Q14 - ep thang 'cancelled' (khong co action nghiep vu nao dat duoc trang
    # thai nay -- ghi de truc tiep qua ORM, nhu da thong nhat voi nguoi dung).
    def _b():
        quo = make_quote(customers["cust_dl_05"], 4_000_000, name_hint="Se bi huy (force write)")
        quo.sudo().write({"state": "cancelled"})
        return quo
    q14, created = once(env, "%s.quote_cancelled" % SEED_MODULE, _b)
    special["Q_CANCELLED (Da huy -- state ghi de truc tiep, khong co action that)"] = q14

    # Q15 - truc chiet khau: discount_pct=9% > max_rate(8%) cua nhom 'new'.
    def _b():
        quo = make_quote(customers["cust_dl_06"], 10_000_000, discount_pct=9.0,
                          name_hint="Chiet khau vuot muc toi da nhom Khach moi")
        return quo
    q15, created = once(env, "%s.quote_discount_above_max" % SEED_MODULE, _b)
    special["Q_DISCOUNT_ABOVE_MAX (chiet khau 9%% > 8%% toi da nhom Khach moi -> PENDING Truong KD)"] = q15

    # Q16 - truc gia san: dong gia cong voi floor_price ghi thang > price_unit.
    def _b():
        quo = Quotation.create({
            "partner_id": customers["cust_dn_03"].id,
            "date_order": today,
        })
        quo.write({
            "line_ids": [(0, 0, {
                "name": "Dong gia cong duoi gia san (QA)",
                "qty": 1.0,
                "price_unit": 8_000_000,
                "line_type": "manufactured",
                "product_id": prod_ct500.id,
                "total_cost": 7_000_000,
                "floor_price": 9_000_000,
            })],
        })
        return quo
    q16, created = once(env, "%s.quote_below_floor" % SEED_MODULE, _b)
    special["Q_BELOW_FLOOR (gia ban 8tr < gia san 9tr -> PENDING CEO)"] = q16

    # Q17 - accepted -> tao Don ban hang -> Hoan tat.
    def _b():
        quo = make_quote(customers["cust_dl_01"], 12_000_000, name_hint="Se tao don Hoan tat")
        quo.action_send()
        quo.action_customer_accept()
        quo.action_create_sale_order()
        quo.sale_order_id.action_done()
        return quo
    q17, created = once(env, "%s.quote_for_so_done" % SEED_MODULE, _b)
    special["Q17 -> Don ban hang trang thai HOAN TAT"] = q17

    # Q18 - accepted -> tao Don ban hang -> Huy.
    def _b():
        quo = make_quote(customers["cust_dl_02"], 10_000_000, name_hint="Se tao don Huy")
        quo.action_send()
        quo.action_customer_accept()
        quo.action_create_sale_order()
        quo.sale_order_id.action_cancel()
        return quo
    q18, created = once(env, "%s.quote_for_so_cancel" % SEED_MODULE, _b)
    special["Q18 -> Don ban hang trang thai HUY"] = q18

    # =======================================================================
    # PHASE 8b — 1 bao gia THAT qua RFQ -> pricing service (BOM confirmed that)
    # =======================================================================
    print("\n=== PHASE 8b: REAL RFQ -> QUOTATION (dung BOM da xac nhan that) ===")

    def _build_real_quote():
        RFQ = env["dl.quotation.request"].sudo()
        rfq = RFQ.create({
            "customer_id": customers["cust_dn_06"].id,
            "requested_date": __import__("odoo").fields.Datetime.now(),
            "deadline": today + __import__("datetime").timedelta(days=7),
        })
        line = env["dl.quotation.request.line"].sudo().create({
            "quotation_request_id": rfq.id,
            "product_type": "manufactured",
            "product_name": prod_ct500.name,
            "quantity": 5.0,
        })
        # Ky thuat xac dinh San pham + BOM (bo qua wizard UI, gan truc tiep).
        line.write({
            "resolved_product_id": prod_ct500.id,
            "resolved_bom_id": bom_confirmed.id,
        })
        rfq.invalidate_recordset(["status"])
        assert rfq.status == "confirmed", (
            "RFQ chua tu chuyen 'confirmed' sau khi resolve dong - status=%s" % rfq.status)
        env["dl.quotation.pricing.service"].sudo().create_from_rfq(rfq)
        return env["dl.quotation"].sudo().search(
            [("quotation_request_id", "=", rfq.id)], limit=1)

    q_real, created = once(env, "%s.quote_real_bom_pricing" % SEED_MODULE, _build_real_quote)
    special["Q_REAL_BOM (tao that qua RFQ + Pricing Service, dung BOM confirmed)"] = q_real

    # =======================================================================
    # PHASE 9 — DON BAN HANG DOC LAP (Nhap, khong gan bao gia nao)
    # =======================================================================
    print("\n=== PHASE 9: STANDALONE SALE ORDER (Nhap) ===")

    def _build_so_draft():
        so = SaleOrder.create({
            "partner_id": customers["cust_dl_03"].id,
            "date_order": today,
            "state": "draft",
        })
        so.write({
            "line_ids": [(0, 0, {
                "name": "Don ban truc tiep (khong qua bao gia) - QA",
                "qty": 2.0,
                "price_unit": 3_500_000,
            })],
        })
        return so

    so_draft, created = once(env, "%s.so_standalone_draft" % SEED_MODULE, _build_so_draft)
    note("SALE_ORDER", ("created" if created else "kept"),
         "%s state=%s (don doc lap, khong qua bao gia)" % (so_draft.name, so_draft.state))

    # =======================================================================
    # TONG KET
    # =======================================================================
    return {
        "customers": customers,
        "suppliers": suppliers,
        "special_quotes": special,
        "q9": q9, "q17": q17, "q18": q18, "so_draft": so_draft,
        "si_expiring": si_expiring,
        "bom_confirmed": bom_confirmed, "bom_draft": bom_draft,
    }


def print_summary(env, data):
    print("\n" + "=" * 78)
    print("TOM TAT SEED DATA")
    print("=" * 78)

    def count(model, domain=None):
        return env[model].sudo().with_context(active_test=False).search_count(domain or [])

    counts = [
        ("res.users (QA moi tao)", 7),
        ("res.partner (Khach hang, ke ca inactive)", len(data["customers"])),
        ("res.partner (Nha cung cap, ke ca inactive)", len(data["suppliers"])),
        ("product.product (moi tao trong script)", 7),
        ("product.supplierinfo (Bang gia NCC moi tao)", 5),
        ("dl.bom", 2),
        ("dl.pricing.profit.rule", 1),
        ("dl.pricing.discount.rule", 3),
        ("dl.quotation (moi tao trong script, khong tinh -R2 tu sinh)", 19),
        ("dl.sale.order (moi tao trong script)", 4),
    ]
    for label, n in counts:
        print("  - %-55s %s" % (label, n))

    print("\n--- CAC BAN GHI DAC BIET (map thang vao Playwright test) ---")
    for label, rec in data["special_quotes"].items():
        line = "  %-90s %s (id=%s, state=%s" % (label, rec.name, rec.id, rec.state)
        if rec.approval_state and rec.approval_state != "not_required":
            line += ", approval_state=%s, approval_level=%s" % (
                rec.approval_state, rec.approval_level)
        line += ")"
        print(line)

    so9 = data["q9"].sale_order_id
    print("\n  %-90s %s (id=%s, state=%s)" % (
        "Don ban hang tao tu Q_ORDERED (Q9)", so9.name, so9.id, so9.state))
    so17 = data["q17"].sale_order_id
    print("  %-90s %s (id=%s, state=%s)" % (
        "Don ban hang HOAN TAT (tu Q17)", so17.name, so17.id, so17.state))
    # sale_order_id la field compute loai tru don 'cancelled' (theo thiet ke
    # cua model - chi tro toi don DANG con hieu luc) nen phai search truc tiep
    # o day de lay dung don da bi huy cua Q18.
    so18 = env["dl.sale.order"].sudo().search(
        [("quotation_id", "=", data["q18"].id)], limit=1)
    print("  %-90s %s (id=%s, state=%s)" % (
        "Don ban hang HUY (tu Q18)", so18.name, so18.id, so18.state))
    print("  %-90s %s (id=%s, state=%s)" % (
        "Don ban hang NHAP (doc lap, khong qua bao gia)",
        data["so_draft"].name, data["so_draft"].id, data["so_draft"].state))

    print("\n  %-90s id=%s (date_end=%s -> validity_state=%s)" % (
        "Bang gia NCC SAP HET HAN", data["si_expiring"].id,
        data["si_expiring"].date_end, data["si_expiring"].validity_state))
    print("  %-90s %s (status=%s)" % (
        "BOM DA XAC NHAN (dung duoc cho bao gia)", data["bom_confirmed"].name,
        data["bom_confirmed"].status))
    print("  %-90s %s (status=%s)" % (
        "BOM NHAP (chua xac nhan - dung de test rule chan)", data["bom_draft"].name,
        data["bom_draft"].status))

    cust_daiphat = data["customers"]["cust_dn_01"]
    cust_thanhdo = data["customers"]["cust_dn_02"]
    cust_daiphat.invalidate_recordset(["dlm_customer_group"])
    cust_thanhdo.invalidate_recordset(["dlm_customer_group"])
    print("\n  %-90s nhom=%s (ky vong: loyal/Khach than thiet)" % (
        cust_daiphat.name, cust_daiphat.dlm_customer_group))
    print("  %-90s nhom=%s (ky vong: existing/Khach cu)" % (
        cust_thanhdo.name, cust_thanhdo.dlm_customer_group))

    print("\n--- GAP/GHI CHU QUAN TRONG (khong tu suy dien, chi ghi nhan) ---")
    gaps = [
        "Bang gia NCC (product.supplierinfo.approval_state) CHI co 2 gia tri that: draft/approved.",
        "  -> Khong co 'cho duyet'/'tu choi' nhu yeu cau ban dau cua PRD/FDS-tom tat.",
        "TC-S02-04/05 trong AGENT_TEST_PLAN_110TC_DLM-ERP.md se FAIL that: man 'Cau hinh He thong'",
        "  (model dl.approval.level) KHONG duoc noi vao luong duyet bao gia thuc su.",
        "  Chi dl.pricing.approval.matrix (menu 'Cau hinh Bao gia') moi anh huong that.",
        "dl.quotation.state co 10 gia tri that (khong phai 7): them revision_requested/",
        "  expired/superseded. 'cancelled' khong co action nghiep vu nao dat toi -- da ghi de",
        "  truc tiep qua ORM cho Q_CANCELLED (theo dung quyet dinh da thong nhat).",
    ]
    for g in gaps:
        print("  " + g)
    print("=" * 78)


def main():
    registry = odoo.registry(DB_NAME)
    with registry.cursor() as cr:
        env = Environment(cr, odoo.SUPERUSER_ID, {})
        try:
            data = run(env)
            print_summary(env, data)
            cr.commit()
            print("\n>>> DA COMMIT THANH CONG vao database '%s'." % DB_NAME)
        except Exception:
            cr.rollback()
            print("\n>>> LOI - DA ROLLBACK TOAN BO. Xem traceback ben duoi.")
            raise


if __name__ == "__main__":
    main()
