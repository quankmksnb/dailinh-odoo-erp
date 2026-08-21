def migrate(cr, version):
    """Điền ĐVT cho dòng báo giá / đơn bán hàng đã có trước khi thêm field.

    Chạy ở PRE để tự điền trước khi Odoo tạo cột: cột `required` mà để Odoo tạo
    thì mọi dòng cũ bị gán cứng "Đơn vị", che mất đơn vị thật khách đã đặt (bộ /
    mét / kg) đang nằm ở dòng RFQ. Dòng nào không truy được nguồn thì cứ để
    trống — Odoo sẽ áp default "Đơn vị" ngay sau đó."""
    cr.execute("""
        ALTER TABLE dl_quotation_line ADD COLUMN IF NOT EXISTS uom_id integer;
        ALTER TABLE dl_sale_order_line ADD COLUMN IF NOT EXISTS uom_id integer;
    """)

    # 1. Báo giá ← dòng RFQ nguồn (nguồn đúng nhất: khách đặt theo đơn vị nào).
    cr.execute("""
        UPDATE dl_quotation_line l
           SET uom_id = r.uom_id
          FROM dl_quotation_request_line r
         WHERE l.rfq_line_id = r.id
           AND l.uom_id IS NULL
           AND r.uom_id IS NOT NULL
    """)

    # 2. Báo giá ← đơn vị tính của sản phẩm (dòng Sales thêm tay, không có RFQ).
    cr.execute("""
        UPDATE dl_quotation_line l
           SET uom_id = t.uom_id
          FROM product_product p
          JOIN product_template t ON t.id = p.product_tmpl_id
         WHERE l.product_id = p.id
           AND l.uom_id IS NULL
    """)

    # 3. Đơn bán ← dòng báo giá tương ứng (khớp theo mô tả: lúc lên đơn mô tả
    #    được chép nguyên văn từ báo giá).
    cr.execute("""
        UPDATE dl_sale_order_line ol
           SET uom_id = ql.uom_id
          FROM dl_sale_order o
          JOIN dl_quotation_line ql ON ql.quotation_id = o.quotation_id
         WHERE ol.order_id = o.id
           AND ql.name = ol.name
           AND ol.uom_id IS NULL
           AND ql.uom_id IS NOT NULL
    """)

    # 4. Đơn bán ← đơn vị tính của sản phẩm (phần còn sót).
    cr.execute("""
        UPDATE dl_sale_order_line ol
           SET uom_id = t.uom_id
          FROM product_product p
          JOIN product_template t ON t.id = p.product_tmpl_id
         WHERE ol.product_id = p.id
           AND ol.uom_id IS NULL
    """)
