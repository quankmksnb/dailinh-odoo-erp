import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# K15 — Tách CHỖ CẤT khỏi CHỖ LÀM (docs/Thiet_ke_phan_he_kho.md §4.1).
#
#   TRƯỚC                                 SAU
#   DL/XUONG "Kho nhà máy sản xuất"       DL/KHOSX "Kho nhà máy sản xuất"
#   ├── Kho vật tư     (lot_stock)        ├── Kho nguyên vật liệu (lot_stock)
#   ├── Bán thành phẩm                    └── Phế liệu chờ bán
#   └── Phế liệu chờ bán                  DL/XUONG "Xưởng sản xuất"  ← ô LÁ
#
# Phần seed (`_dlm_setup_inventory_layout`) đã chạy XONG trước file này — data
# XML nạp trước post-migration. Nên tới đây thì `khosx` đã tồn tại, `xuong_pl`
# và lot_stock đã được đưa về dưới nó, và lot_stock đã mang tên mới.
#
# Còn đúng HAI việc seed cố ý không làm:
#
# 1. ĐỔI TÊN `stock_location_xuong`. Vòng lặp seed KHÔNG ghi đè `name` của vị trí
#    đã tồn tại (người dùng có thể đã đổi tên khu cho hợp cách gọi ở xưởng) ⇒
#    trên DB đã cài, khu này còn nguyên tên "Kho nhà máy sản xuất" — trùng hệt
#    tên của `khosx` vừa tạo. Hai ô cùng tên trong một dropdown là lỗi chọn nhầm
#    chờ sẵn, và đây đúng là cặp ô mà chọn nhầm thì hàng đi sai chỗ.
#
# 2. GỘP ô "Bán thành phẩm" vào Kho nguyên vật liệu (người dùng chốt 2026-08-13).
#    Ô cũ bị bỏ khỏi danh sách seed nên nó chỉ nằm im — tồn BTP sẽ kẹt ở một ô
#    không màn hình nào trỏ tới. Phải DỜI tồn rồi mới lưu trữ ô.
#
# 🔴 Vì sao dời quant chứ không sinh phiếu chuyển kho: đây không phải một cuộc
# luân chuyển vật lý — thùng BTP không nhúc nhích, chỉ có cái nhãn trên kệ đổi.
# Sinh phiếu là chế ra một sự kiện chưa từng xảy ra, và phiếu đó sẽ nằm trong
# lịch sử như thể ai đó đã khuân hàng đi.


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _doi_ten_xuong(env)
    _gop_o_btp(env)


def _doi_ten_xuong(env):
    xuong = env.ref(
        "dl_inventory.stock_location_xuong", raise_if_not_found=False)
    if not xuong:
        return
    if xuong.name == "Kho nhà máy sản xuất":
        xuong.name = "Xưởng sản xuất"
        _logger.info(
            "K15: đổi tên DL/XUONG 'Kho nhà máy sản xuất' → 'Xưởng sản xuất'. "
            "Tên cũ nay thuộc về khu cha DL/KHOSX.")
    else:
        # Người dùng đã tự đặt tên khác ⇒ TÔN TRỌNG, chỉ báo để họ biết ngữ
        # nghĩa của ô này vừa đổi (từ khu-chứa-kiêm-cha thành ô lá "chỗ làm").
        _logger.warning(
            "K15: DL/XUONG đang mang tên tự đặt '%s' — KHÔNG đổi. Lưu ý ô này "
            "nay là chỗ LÀM VIỆC (ô lá), không còn là khu cha; khu cha mới tên "
            "'Kho nhà máy sản xuất'.", xuong.name)


def _gop_o_btp(env):
    btp = env.ref(
        "dl_inventory.stock_location_xuong_btp", raise_if_not_found=False)
    if not btp:
        _logger.info("K15: DB này chưa từng có ô Bán thành phẩm — bỏ qua.")
        return
    kho = env.ref("dl_inventory.stock_location_nhan_kho")

    # active_test=False: ô có thể đã bị lưu trữ ở lần chạy trước (migration phải
    # chạy lại được mà không đổi kết quả).
    quants = env["stock.quant"].with_context(active_test=False).search([
        ("location_id", "=", btp.id),
    ])
    co_hang = quants.filtered(lambda q: q.quantity or q.reserved_quantity)
    if co_hang.filtered("reserved_quantity"):
        # Dời một quant đang bị phiếu khác giữ chỗ là để phiếu đó trỏ vào chỗ
        # trống. Dừng hẳn thay vì dời bừa — người thật phải xử phiếu đó trước.
        _logger.error(
            "K15: KHÔNG gộp được ô Bán thành phẩm — %s dòng tồn đang bị phiếu "
            "khác GIỮ CHỖ. Xử lý (xác nhận hoặc huỷ) các phiếu đó rồi chạy lại "
            "`-u dl_inventory`. Ô cũ tạm giữ nguyên, hàng không mất.",
            len(co_hang.filtered("reserved_quantity")))
        return

    for quant in co_hang:
        _logger.warning(
            "K15: dời %s %s ('%s', lô %s) từ 'Bán thành phẩm' sang '%s'.",
            quant.quantity, quant.product_id.uom_id.name,
            quant.product_id.display_name, quant.lot_id.name or "không lô",
            kho.display_name)
    if co_hang:
        # Ghi thẳng location_id: gộp hai ô thành một, không phải luân chuyển.
        # Nếu ô đích đã có quant cùng (sản phẩm, lô) thì Odoo để hai dòng cùng
        # vị trí — `_gather`/`_merge_quants` cộng lại khi đọc, không sai số.
        co_hang.write({"location_id": kho.id})

    trong = quants - co_hang
    if trong:
        trong.unlink()

    # 🔴 REPARENT trước khi lưu trữ — không phải chi tiết thẩm mỹ. Lưu trữ KHÔNG
    # gỡ bản ghi khỏi cây: `parent_path` vẫn còn, nên `DL/XUONG` vẫn có một ô con
    # (dù ẩn) và **thôi là ô lá**. Hôm nay vô hại (ô rỗng, không chọn được),
    # nhưng ngày ai đó bỏ lưu trữ nó thì vai trò kép quay lại NGUYÊN VẸN — cùng
    # cái lỗ `child_of` mà cả K15 sinh ra để đóng, và không lỗi nào sẽ nổ.
    # Đưa về dưới `khosx` cũng đúng nghĩa: hàng của nó đã chuyển vào ô anh em.
    khosx = env.ref("dl_inventory.stock_location_khosx", raise_if_not_found=False)
    if khosx and btp.location_id != khosx:
        btp.location_id = khosx

    if btp.active:
        btp.active = False
    _logger.info(
        "K15: đã lưu trữ ô 'Bán thành phẩm' (%s dòng tồn dời sang '%s'). "
        "Từ nay vật tư thô và BTP nằm chung một ô — đếm vật tư sẽ lẫn BTP, "
        "đánh đổi đã được chốt để thủ kho chỉ còn MỘT ô phải tìm.",
        len(co_hang), kho.display_name)
