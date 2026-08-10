def migrate(cr, version):
    """Vá attachment cũ của dòng RFQ (many2many_binary).

    Widget many2many_binary lưu ir.attachment với res_id=0 (file upload trước khi
    dòng có id). Attachment res_id=0 chỉ NGƯỜI TẠO + admin đọc được ⇒ vai trò khác
    (BA khác, Kỹ thuật, CEO...) mở RFQ có đính kèm bị AccessError.

    Gắn res_model/res_id về đúng dòng RFQ (dựa vào bảng quan hệ m2m) để ai đọc
    được dòng thì đọc được file. Từ nay code stamp tự động lúc tạo/sửa dòng, xem
    dl.quotation.request.line._stamp_attachments — migration này chỉ vá dữ liệu cũ.
    """
    cr.execute(
        """
        UPDATE ir_attachment a
        SET res_model = 'dl.quotation.request.line',
            res_id = rel.line_id
        FROM dl_rfq_line_ir_attachment_rel rel
        WHERE rel.attachment_id = a.id
          AND (a.res_id IS NULL OR a.res_id = 0)
        """
    )
