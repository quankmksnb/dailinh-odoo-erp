# Dọn data demo (noupdate=1) trên DB đã cài từ trước — đưa vật tư/BTP demo
# về đúng nhóm sản phẩm chuẩn + mã theo convention seed. DB cài mới nhận
# thẳng từ dl_demo_data.xml, migration này chỉ đồng bộ DB cũ.
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    def ref(xmlid):
        return env.ref("dl_product.%s" % xmlid, raise_if_not_found=False)

    scrap = ref("seed_scrap_steel")

    # ── Bước 1: dời SẢN PHẨM demo về đúng nhóm trước (nhóm đích thuộc nhánh
    # Vật tư đã được data XML gắn cha sẵn — constraint pass). ──
    product_fixes = [
        ("demo_product_thep_cuon", {
            "default_code": "VT-TT-CT3-CUON",
            "categ_id": ref("material_categ_steel_sheet"),
            "dlm_scrap_product_id": scrap,
        }),
        ("demo_product_ong_vuong", {
            "name": "Thép hộp vuông 25×25×1.5mm",
            "default_code": "VT-TH-25",
            "categ_id": ref("material_categ_steel_box"),
            "dlm_scrap_product_id": scrap,
        }),
        ("demo_product_oc_vit", {
            "default_code": "VT-OCVIT-M6",
            "categ_id": ref("material_categ_consumable"),
        }),
        ("demo_product_tam_sat", {"categ_id": ref("material_categ_semi")}),
        ("demo_product_khung_ong", {
            "name": "Khung hàn thép hộp 25×25×1.5mm (bộ)",
            "categ_id": ref("material_categ_semi"),
        }),
    ]
    for xmlid, vals in product_fixes:
        rec = ref(xmlid)
        if not rec:
            continue  # demo bị xóa tay trên DB đó — bỏ qua
        vals = {k: (v.id if hasattr(v, "id") else v) for k, v in vals.items() if v}
        if vals:
            rec.write(vals)

    # ── Bước 2: gắn nhóm demo vào gốc Thành phẩm. install_mode để bỏ qua
    # guard _check_branch_products — sản phẩm user tạo tay còn sai nhánh
    # trong nhóm sẽ được quét dọn ở Bước 3 ngay sau đây. ──
    root_finished = ref("categ_root_finished")
    if root_finished:
        for xmlid in ("categ_khung_thep_han", "categ_ban_ghe_sat"):
            categ = ref(xmlid)
            if categ:
                categ.with_context(install_mode=True).write(
                    {"parent_id": root_finished.id})

    # ── Bước 3: quét toàn bộ sản phẩm đang nằm SAI NHÁNH (vd SP gia công
    # test nằm trong nhóm Thép hộp) → đưa về nhóm GỐC đúng nhánh; user gán
    # lại nhóm con phù hợp sau. Từ đây constraint chặn cứng giữ bất biến. ──
    root_material = ref("categ_root_material")
    Product = env["product.product"].with_context(active_test=False)
    moves = [
        # (kind, nhánh đang đứng SAI, nhóm gốc đích)
        (("manufactured", "trading"), "material", root_finished),
        (("material", "material_processed"), "finished", root_material),
    ]
    for kinds, wrong_branch, target in moves:
        if not target:
            continue
        bad = Product.search([
            ("product_kind", "in", kinds),
            ("categ_id.dl_branch", "=", wrong_branch),
        ])
        if bad:
            bad.write({"categ_id": target.id})
