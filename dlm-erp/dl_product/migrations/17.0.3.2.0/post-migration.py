import logging

_logger = logging.getLogger(__name__)

# Quy cách MUA đổi từ MILIMÉT sang MÉT (chiều dài cây · khổ tấm). Dữ liệu cũ
# đang là mm nên phải chia 1000, nếu không mọi định mức cắt đoạn/tấm sẽ chia cho
# một mẫu số lớn gấp 1000 lần ⇒ số cây ra ~0 ⇒ giá vốn ~0 mà KHÔNG có lỗi nào
# nổ ra. Đây là cách hỏng ÂM THẦM, nên migration này là bắt buộc.
#
# Kích thước CẮT (dl.bom.line.dim_length/dim_width) cố ý GIỮ mm — số trên bản
# vẽ — nên không đụng tới ở đây.
_COLUMNS = ("dlm_stock_length", "dlm_sheet_w", "dlm_sheet_h")


def migrate(cr, version):
    if not version:
        return                      # cài mới: default đã là mét, không có gì để đổi
    for column in _COLUMNS:
        cr.execute("""
            UPDATE product_product
               SET %(col)s = %(col)s / 1000.0
             WHERE %(col)s IS NOT NULL
               AND %(col)s != 0
        """ % {"col": column})
        _logger.info("mm→m: %s bản ghi đổi đơn vị cột %s.", cr.rowcount, column)
