import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

UNIT_TO_UOM_NAME = {
    'cái': 'Units',
    'm2': 'm²',
    'kg': 'kg',
}

CATEGORY_TO_NAME = {
    'steel_sheet': 'Thép tấm',
    'steel_pipe': 'Thép hộp - ống',
    'paint_coating': 'Sơn - mạ',
    'auxiliary': 'Vật tư phụ',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'dl_material' AND column_name = 'code'
    """)
    if not cr.fetchone():
        _logger.info('dlm_material migration 17.0.2.0.0: không còn cột cũ, bỏ qua (đã migrate trước đó).')
        return

    # ── 1. Snapshot dữ liệu cũ qua raw SQL ──────────────────────────────
    cr.execute("""
        SELECT id, code, name, unit, category, status
        FROM dl_material ORDER BY id
    """)
    old_materials = cr.fetchall()
    _logger.info('dlm_material migration: tìm thấy %s vật tư cũ cần chuyển.', len(old_materials))

    cr.execute("ALTER TABLE dl_material ADD COLUMN IF NOT EXISTS product_id integer")
    cr.execute("ALTER TABLE dl_material ADD COLUMN IF NOT EXISTS material_code varchar")
    cr.execute("ALTER TABLE dl_material_price ADD COLUMN IF NOT EXISTS uom_id integer")

    # Dọn cột mồ côi còn sót từ module purchase/stock đã cài rồi gỡ trước đây
    # trên máy dev — model hiện tại (chỉ phụ thuộc 'product') không biết field
    # này để tự set default, khiến INSERT product.template mới bị NotNullViolation.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'product_template' AND column_name = 'purchase_line_warn'
              AND is_nullable = 'NO'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE product_template ALTER COLUMN purchase_line_warn DROP NOT NULL")
        _logger.info(
            "dlm_material migration: gỡ NOT NULL trên cột mồ côi "
            "product_template.purchase_line_warn (còn sót từ module purchase/stock cũ).")

    # ── 2. Map unit tự do → uom.uom chuẩn (tra theo tên, không hardcode id) ──
    uom_cache = {}
    for unit_str, uom_name in UNIT_TO_UOM_NAME.items():
        uom = env['uom.uom'].search([('name', '=', uom_name)], limit=1)
        if not uom:
            raise ValueError("Không tìm thấy UoM '%s' cho unit cũ '%s'" % (uom_name, unit_str))
        uom_cache[unit_str] = uom
    fallback_uom = uom_cache.get('cái') or env.ref('uom.product_uom_unit')

    # ── 3. Tạo product.category con, giữ lại phân loại cũ ───────────────
    categ_cache = {}
    for cat_key, cat_name in CATEGORY_TO_NAME.items():
        categ = env['product.category'].search([('name', '=', cat_name)], limit=1)
        if not categ:
            categ = env['product.category'].create({'name': cat_name})
        categ_cache[cat_key] = categ
    fallback_categ = env.ref('product.product_category_all', raise_if_not_found=False) \
        or env['product.category'].search([], limit=1, order='id asc')

    # ── 4-5. Tạo product.product cho từng vật tư cũ, backfill bằng raw SQL ──
    material_uom_map = {}
    for mat_id, code, name, unit, category, status in old_materials:
        uom = uom_cache.get(unit)
        if not uom:
            _logger.warning(
                "dlm_material migration: vật tư id=%s có unit '%s' không nằm trong bảng map, "
                "dùng UoM mặc định 'Units'.", mat_id, unit)
            uom = fallback_uom
        categ = categ_cache.get(category) or fallback_categ

        product = env['product.product'].create({
            'name': name,
            'uom_id': uom.id,
            'uom_po_id': uom.id,
            'categ_id': categ.id,
            'type': 'consu',
            'sale_ok': False,
            'purchase_ok': True,
            'active': status != 'discontinued',
        })
        material_uom_map[mat_id] = uom

        # Raw SQL — không qua ORM write()/create() của dl.material để tránh
        # kích hoạt RBAC write() guard và tạo rác chatter tracking cho dữ liệu di trú.
        cr.execute(
            "UPDATE dl_material SET product_id = %s, material_code = %s WHERE id = %s",
            (product.id, code, mat_id),
        )
    _logger.info('dlm_material migration: đã tạo %s product.product tương ứng.', len(old_materials))

    # ── 6. Backfill uom_id cho dl_material_price từ material tương ứng ──
    cr.execute("""
        SELECT id, material_id, status FROM dl_material_price ORDER BY id
    """)
    old_prices = cr.fetchall()
    for price_id, mat_id, status in old_prices:
        uom = material_uom_map.get(mat_id) or fallback_uom
        cr.execute("UPDATE dl_material_price SET uom_id = %s WHERE id = %s", (uom.id, price_id))

    # ── 7. Xóa dòng giá rác: status=invalid VÀ valid_to < valid_from (dữ liệu
    #      đã hỏng logic từ trước, không thể giữ lại vì vi phạm constraint mới) ──
    cr.execute("""
        SELECT id, material_id, valid_from, valid_to FROM dl_material_price
        WHERE status = 'invalid' AND valid_to IS NOT NULL AND valid_to < valid_from
    """)
    broken_rows = cr.fetchall()
    for row_id, mat_id, vf, vt in broken_rows:
        _logger.warning(
            'dlm_material migration: XÓA dòng giá id=%s (material_id=%s, valid_from=%s, '
            'valid_to=%s) — dữ liệu rác đã hỏng (valid_to < valid_from) từ trước khi migrate, '
            'không có ý nghĩa nghiệp vụ và vi phạm constraint mới nếu giữ lại.',
            row_id, mat_id, vf, vt)
        cr.execute("DELETE FROM dl_material_price WHERE id = %s", (row_id,))

    # ── 8. Đóng sớm các dòng invalid còn lại (ngày hợp lệ nhưng từng bị đánh
    #      dấu sai) để không hồi sinh thành "đang hiệu lực" sau khi bỏ field status ──
    cr.execute("SELECT id, valid_from FROM dl_material_price WHERE status = 'invalid'")
    remaining_invalid = cr.fetchall()
    for row_id, valid_from in remaining_invalid:
        reason = ('Di trú dữ liệu (bỏ field status): dòng từng đánh dấu status=invalid, '
                   'đóng hồi tố về đúng Ngày hiệu lực để không hiển thị nhầm là đang hiệu lực.')
        cr.execute("""
            UPDATE dl_material_price
            SET valid_to = %s, is_override = TRUE, override_reason = %s
            WHERE id = %s
        """, (valid_from, reason, row_id))
        _logger.info('dlm_material migration: đóng sớm dòng giá invalid cũ id=%s.', row_id)

    # ── 9. Dòng status=expired: không cần xử lý, is_active tự tính False ──

    # ── 10. Xóa cột thừa, set NOT NULL thật ──────────────────────────────
    cr.execute("""
        ALTER TABLE dl_material
        DROP COLUMN IF EXISTS code,
        DROP COLUMN IF EXISTS unit,
        DROP COLUMN IF EXISTS category,
        DROP COLUMN IF EXISTS status,
        DROP COLUMN IF EXISTS technical_spec
    """)
    cr.execute("""
        ALTER TABLE dl_material_price
        DROP COLUMN IF EXISTS status,
        DROP COLUMN IF EXISTS invalid_reason
    """)
    cr.execute("ALTER TABLE dl_material ALTER COLUMN product_id SET NOT NULL")
    cr.execute("ALTER TABLE dl_material ALTER COLUMN material_code SET NOT NULL")
    cr.execute("ALTER TABLE dl_material_price ALTER COLUMN uom_id SET NOT NULL")

    # ── 11. Log tổng kết ──────────────────────────────────────────────────
    _logger.info(
        'dlm_material migration 17.0.2.0.0 hoàn tất: %s vật tư di trú, %s dòng giá còn lại '
        '(đã xóa %s dòng rác, đóng hồi tố %s dòng invalid cũ).',
        len(old_materials), len(old_prices) - len(broken_rows),
        len(broken_rows), len(remaining_invalid))
