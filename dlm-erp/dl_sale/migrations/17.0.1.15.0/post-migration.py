def migrate(cr, version):
    """Không tự tạo báo giá khi nâng cấp; Sales chủ động tạo sau khi kiểm tra RFQ."""
