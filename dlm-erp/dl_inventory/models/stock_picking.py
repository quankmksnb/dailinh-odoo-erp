# -*- coding: utf-8 -*-
"""K3–K5 — Phiếu kho: lô tự sinh, truy vết nguồn gốc, và kiểm hàng NCC.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §3.4, §6, §11.3, §11.4.

Nhận hàng đi HAI BƯỚC:

    [1] NH/xxxxx  NCC → Chờ kiểm hàng      thủ kho đếm số NCC giao
    [2] KC/xxxxx  Chờ kiểm → Vật tư & HTM  thủ kho kiểm chất lượng, ghi Đạt/Loại
    [3] TR/xxxxx  Chờ trả NCC → NCC        NHÁP, Mua hàng quyết định

Phiếu [2] là màn quan trọng nhất của phân hệ: nó là chỗ duy nhất phân biệt được
"NCC giao thiếu" với "NCC giao hàng kém" — xem ``stock_move.py``.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import format_datetime
from odoo.tools.float_utils import float_compare, float_is_zero

# Mã trình tự của loại hoạt động — neo vào đây thay vì XML ID vì `sequence_code`
# không đổi khi người dùng sửa tên hiển thị (cùng lý do như ir_rule.xml).
_DLM_QC_CODE = "KC"
_DLM_RETURN_CODE = "TR"
_DLM_TO_SCRAP_CODE = "HPL"
_DLM_FG_RECEIPT_CODE = "NTP"

# RS-02 — Form/list Đại Linh theo từng loại việc. MỌI đường mở phiếu kho phải đi
# qua bảng này; thiếu nó là rơi về form gốc Odoo với nguyên bộ nút native.
# Tra thẳng (không `.get`): loại việc mới mà quên khai ở đây thì KeyError kêu to
# ngay, còn hơn im lặng mở lại cửa native mà không ai biết.
_DLM_FORM_BY_KIND = {
    "receipt": "dl_inventory.view_dl_receipt_form",
    "qc": "dl_inventory.view_dl_qc_form",
    "transfer": "dl_inventory.view_dl_transfer_form",
    "delivery": "dl_inventory.view_dl_delivery_form",
    "vendor_return": "dl_inventory.view_dl_vendor_return_form",
    "scrap_sale": "dl_inventory.view_dl_scrap_sale_form",
    "to_scrap": "dl_inventory.view_dl_to_scrap_form",
    "fg_receipt": "dl_inventory.view_dl_fg_receipt_form",
}
# Loại hàng được phép NẰM ở Kho thành phẩm. Đại Linh chỉ bán sản phẩm thương mại
# và sản phẩm gia công hoàn chỉnh (người dùng chốt 2026-08-12), mà Kho thành phẩm
# chính là nơi phiếu Giao hàng lấy hàng (§5.3) — vật tư/BTP lọt vào đây thì sớm
# muộn cũng bị giao cho khách.
_DLM_FG_KINDS = ("trading", "manufactured")
# Loại hàng được phép NẰM ở Khu nhập hàng (và 2 vị trí con còn lại: Chờ kiểm +
# Chờ trả NCC). Khu này chỉ hứng hàng NCC giao, mà Đại Linh chỉ MUA vật tư và
# hàng thương mại — BTP và sản phẩm gia công là do mình tự làm, không bao giờ đi
# qua đây. Cùng một luật đã dùng ở domain phiếu Nhận hàng (SM-01), viết lại ở đây
# cho vế "khu nào chứa gì".
_DLM_INBOUND_KINDS = ("material", "trading")
# Loại hàng được phép NẰM ở Xưởng sản xuất (`DL/XUONG` — từ K15 là ô LÁ, chỗ
# công nhân làm việc). Ba thứ có việc ở xưởng: vật tư đã bàn giao, bán thành phẩm
# đang làm dở, và hàng gia công quay lại SỬA. Hàng thương mại thì KHÔNG: mua về
# bán thẳng, và `dl.bom.line.material_id` chỉ nhận ("material",
# "material_processed") nên nó không bao giờ là thành phần sản xuất — đưa vào
# xưởng là đi lạc, chưa kể còn phải chuyển ngược ra Kho thành phẩm.
_DLM_WORKSHOP_KINDS = ("material", "material_processed", "manufactured")
# Loại hàng được phép NẰM ở Kho nguyên vật liệu (`DL/KHOSX/KHO`, = lot_stock_id).
#
# 🔴 K15 — thêm `material_processed` (bán thành phẩm). Người dùng chốt 2026-08-13
# GỘP ô `DL/XUONG/BTP` cũ vào đây, sau khi đã được nêu cái giá: đếm vật tư thô từ
# nay lẫn BTP, ngược với lý do §4.1 tách hai ô ("để kiểm kê vật tư tách khỏi
# BTP"). Đổi lại thủ kho chỉ còn MỘT ô để tìm hàng thay vì hai.
#
# Hàng thương mại vẫn KHÔNG vào đây: đạt kiểm là đi THẲNG sang Kho thành phẩm ở
# bước [2] Kiểm & cất (§5.3).
_DLM_MATERIAL_STORE_KINDS = ("material", "material_processed")
# K13 — Loại hàng xưởng BÁO LÀM XONG trên phiếu [8] Nhập thành phẩm. Đúng hai
# thứ xưởng đẻ ra: sản phẩm gia công hoàn chỉnh (về Kho thành phẩm) và bán thành
# phẩm (về Kho nguyên vật liệu, chờ công đoạn sau). Vật tư và hàng thương mại
# KHÔNG vào đây — chúng đi vào bằng phiếu Nhận hàng NCC, không phải do mình làm.
_DLM_FG_RECEIPT_KINDS = ("manufactured", "material_processed")


def _dlm_kind_domain(kinds):
    return [("product_kind", "in", list(kinds))]


def _dlm_domain_kinds(domain):
    """Tuple loại hàng của một vị từ, hoặc None nếu nó không nói về loại hàng.

    Cần vì câu giải thích cho người dùng phải nêu **kết quả cuối** — giao của
    hai đầu — chứ không phải ghép hai luật lại. Ghép lại là liệt kê cả loại hàng
    phiếu KHÔNG chuyển được, đúng cái bí ẩn mà dải này sinh ra để gỡ.
    """
    if (len(domain) == 1 and domain[0][0] == "product_kind"
            and domain[0][1] == "in"):
        return tuple(domain[0][2])
    return None


# Bản đồ LUẬT CỐ ĐỊNH "khu nào chứa hàng gì" — nguồn: Thiet_ke_phan_he_kho.md
# §4.2 "Món nào nằm ở đâu". Khớp theo cây nên khu con thừa hưởng luật của cha.
#
# 🔴 K11 — mỗi luật nay mang một VỊ TỪ, không phải một tuple loại hàng. Bắt buộc
# vì luật khu Phế liệu KHÔNG đọc `product_kind` (SCRAP-STEEL cũng là `material`
# y hệt thép thật) mà đọc cờ `dlm_is_scrap`.
#
# Vị từ hiện thực bằng DOMAIN chứ không phải lambda: domain vẫn là vị từ, nhưng
# thêm hai thứ lambda không có — chạy được dưới SQL (`search` không phải nạp cả
# danh mục sản phẩm vào RAM) và giao được với nhau bằng `expression.AND`. Đánh
# giá trong Python thì dùng `filtered_domain`.
#
# Bốn cột: (XML ID khu, vị từ, NHÃN đọc được, LÝ DO).
# Nhãn phải nằm ngay đây chứ không suy từ selection `product_kind` — từ khi có
# luật không đọc `product_kind` thì suy ngược sẽ ra câu chặn nói SAI tên loại
# hàng mà vẫn chặn ĐÚNG: kiểu lỗi khó thấy nhất.
# Lý do đi kèm vì mọi câu chặn đều phải nêu hệ quả, không chỉ nêu luật.
_DLM_LOCATION_RULES = (
    ("dl_inventory.stock_location_tp", _dlm_kind_domain(_DLM_FG_KINDS),
     "hàng thương mại, sản phẩm gia công",
     "Kho thành phẩm là nơi phiếu Giao hàng lấy hàng — thứ lọt vào đây sớm "
     "muộn cũng bị giao cho khách."),
    # 🔴 PHẢI đặt TRƯỚC luật khu cha `stock_location_khosx` — cả hai luật dưới
    # đây đều thế. `_dlm_location_rule` lấy match ĐẦU TIÊN theo cây; đặt sau
    # luật cha thì luật hẹp không bao giờ chạy, và KHÔNG lỗi nào nổ.
    # (Trước K15 khu cha là `stock_location_xuong` — nó nay là ô lá, không còn
    # con nào, nên thứ tự so với nó không còn ý nghĩa.)
    ("dl_inventory.stock_location_xuong_pl", [("dlm_is_scrap", "=", True)],
     "mặt hàng phế liệu",
     "Khu phế liệu chỉ chứa phế liệu — thép nguyên cây lọt vào đây là bị bán "
     "ve chai, và Lệnh sản xuất lại rút chính nó ra làm hàng."),
    ("dl_inventory.stock_location_nhan_kho",
     _dlm_kind_domain(_DLM_MATERIAL_STORE_KINDS), "vật tư, bán thành phẩm",
     "Kho nguyên vật liệu chứa thứ chờ đưa vào sản xuất — hàng thương mại đã "
     "đi thẳng sang Kho thành phẩm ở bước kiểm, không cất về đây nữa."),
    ("dl_inventory.stock_location_nhan", _dlm_kind_domain(_DLM_INBOUND_KINDS),
     "vật tư, hàng thương mại",
     "Khu nhập hàng chỉ hứng hàng nhà cung cấp giao, mà Đại Linh chỉ mua vật "
     "tư và hàng thương mại."),
    # Container thuần — không chứa hàng trực tiếp và đã cấm chọn tay bằng
    # `dlm_no_inventory`. Luật này là lớp thứ HAI: cấm chọn tay chỉ chặn phiếu
    # do người dựng, còn ngày nào đó có ô con thứ ba thì nó thừa hưởng luật này
    # thay vì rơi vào "không hạn chế".
    ("dl_inventory.stock_location_khosx",
     _dlm_kind_domain(_DLM_MATERIAL_STORE_KINDS), "vật tư, bán thành phẩm",
     "Kho nhà máy sản xuất là khu gom nhóm — chọn ô con cụ thể (Kho nguyên vật "
     "liệu hoặc Phế liệu chờ bán)."),
    ("dl_inventory.stock_location_xuong",
     _dlm_kind_domain(_DLM_WORKSHOP_KINDS),
     "vật tư, bán thành phẩm, sản phẩm gia công",
     "Xưởng chỉ nhận thứ đưa vào sản xuất hoặc hàng gia công quay lại sửa."),
)
# 🔴 K11 — Loại việc ĐƯỢC PHÉP đụng khu quá cảnh (Chờ kiểm / Chờ trả NCC / Khu
# nhập cha). Đây là toàn bộ lý do hai khu đó tồn tại: chúng là chặng của luồng
# nhận hàng. Mọi loại việc KHÁC — chuyển kho, giao hàng, bán phế liệu, hoá phế
# liệu, và bất kỳ loại nào thêm về sau — đều bị chặn.
#
# Viết theo chiều "ai ĐƯỢC phép" chứ không "ai bị cấm": danh sách cấm thì loại
# việc thứ tám mặc định LỌT, danh sách cho phép thì nó mặc định bị chặn. Cùng
# một lỗi đã sai hai lần (K9 bịt Chuyển kho, vẫn hở Giao hàng).
#
# `to_scrap` nằm trong danh sách này vì nó là LỐI RA DUY NHẤT của hàng kẹt ở khu
# Chờ trả NCC (§6.4.1). Nó không phá lá chắn: phiếu [9] KHÔNG tạo tay được và
# hai ô vị trí trên form đều chỉ-đọc — hàng nào, từ đâu là do nút bấm dựng sẵn,
# không phải một dropdown mở toang.
_DLM_TRANSIT_KINDS = ("receipt", "qc", "vendor_return", "to_scrap")
# RS-03 — Ai được QUYẾT ĐỊNH trả hàng NCC (chốt / huỷ). Thủ kho không nằm đây.
_DLM_RETURN_DECIDERS = (
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# 🔴 K15 — Ai được KÝ NHẬN hàng về xưởng. **Thủ kho CỐ Ý không nằm đây** — đó là
# toàn bộ lý do chữ ký này tồn tại: người giao không được tự ký là mình đã nhận,
# không thì sáu tháng sau truy "ai nhận đống thép này" lại ra chính người xuất.
# Admin/CEO có mặt làm lối thoát khi trưởng KT nghỉ, không phải để dùng thường.
_DLM_RECEIPT_SIGNERS = (
    "dl_base.dl_group_tech",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# 🔴 K16 — chiều NGƯỢC lại: hàng từ xưởng về kho thì THỦ KHO là người ký nhận,
# và bên Kỹ thuật cố ý không nằm đây. Cùng một nguyên tắc, soi gương: người lập
# phiếu không bao giờ là người xác nhận đã nhận.
_DLM_STORE_SIGNERS = (
    "dl_base.dl_group_warehouse",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# Chiều bàn giao → (ai ký nhận, nhãn bên nhận). `to_workshop` là tuyến [3] vật
# tư ra xưởng (K15); `from_workshop` là tuyến [8] xưởng nộp về (K16).
_DLM_RECEIPT_FLOWS = {
    "to_workshop": (_DLM_RECEIPT_SIGNERS, "bên Xưởng"),
    "from_workshop": (_DLM_STORE_SIGNERS, "Thủ kho"),
}
_DLM_TREE_BY_KIND = {
    "receipt": "dl_inventory.view_dl_picking_tree",
    "qc": "dl_inventory.view_dl_picking_tree_nocreate",
    "transfer": "dl_inventory.view_dl_transfer_tree",
    "delivery": "dl_inventory.view_dl_delivery_tree",
    "vendor_return": "dl_inventory.view_dl_vendor_return_tree",
    "scrap_sale": "dl_inventory.view_dl_picking_tree_nocreate",
    "to_scrap": "dl_inventory.view_dl_picking_tree_nocreate",
    "fg_receipt": "dl_inventory.view_dl_fg_receipt_tree",
}


def _dlm_fmt(qty):
    """Số lượng cho câu thông báo: bỏ số 0 thừa, dấu thập phân kiểu Việt."""
    return ("%g" % qty).replace(".", ",")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ── K5 — Liên kết chứng từ ───────────────────────────────────────────────
    dlm_origin_picking_id = fields.Many2one(
        "stock.picking", string="Phiếu nhận gốc", index=True, copy=False,
        help="Phiếu nhận hàng đã sinh ra phiếu trả NCC này.")
    # Đếm (không phải o2m ngược): phiếu trả neo vào phiếu NHẬN, nên o2m ngược sẽ
    # rỗng khi đang đứng ở phiếu KIỂM — đúng chỗ vừa bấm ra phiếu trả. Một hàm
    # tra chung cho cả hai chặng thay vì hai field nói cùng một chuyện.
    dlm_return_count = fields.Integer(
        string="Số phiếu trả NCC", compute="_compute_dlm_return_count")

    # ── K6 — Liên kết phiếu giao ↔ đơn bán hàng ──────────────────────────────
    # ⚠️ Chính field này KÍCH HOẠT khoá reset-nháp của đơn: _reset_draft_blockers
    # (dl_sale) dò MỌI many2one lưu trữ trỏ tới dl.sale.order bằng metadata, nên
    # không phải viết thêm gì — nhưng cũng có nghĩa là ĐỔI TÊN/GỠ field này sẽ
    # âm thầm mở lại đường đưa đơn đã giao về nháp.
    dlm_sale_order_id = fields.Many2one(
        "dl.sale.order", string="Đơn bán hàng", index=True, copy=False,
        ondelete="restrict",
        help="Đơn đã sinh ra phiếu giao này.")
    # Tổng số lượng trên phiếu — cột "Số lượng trả" của màn Trả hàng NCC. Không
    # store: chỉ dùng để đọc, và store sẽ phải theo dõi mọi thay đổi dòng hàng
    # của MỌI phiếu kho chỉ để phục vụ một cột của một màn.
    dlm_qty_total = fields.Float(
        string="Tổng số lượng", digits="Product Unit of Measure",
        compute="_compute_dlm_qty_total")
    dlm_reject_summary = fields.Char(
        string="Lý do", compute="_compute_dlm_reject_summary")

    # ── P1 (SM-03/SM-04) — Lọc mặt hàng theo ngữ cảnh phiếu ──────────────────
    # Nguồn: docs/Thiet_ke_kho_thong_minh_context_aware.md SM-03, SM-04.
    # Hai field này nuôi domain của product_id trên dòng hàng: chỉ hiện mặt hàng
    # HỢP LỆ trong ngữ cảnh thay vì mọi SP. Phải đặt invisible trên form để web
    # client có giá trị mà evaluate `parent.<field>` trong domain. Non-store:
    # chỉ phục vụ domain, tính lại mỗi lần đổi vị trí đích / đơn (đúng cơ chế
    # "domain phụ thuộc field khác").
    dlm_blocked_product_ids = fields.Many2many(
        "product.product", string="Mặt hàng không hợp lệ cho phiếu này",
        compute="_compute_dlm_blocked_product_ids",
        help="Sản phẩm mà nơi lấy hoặc nơi nhận không được phép chứa — dùng "
             "LOẠI TRỪ khỏi danh sách mặt hàng của phiếu chuyển kho.")
    dlm_orderable_product_ids = fields.Many2many(
        "product.product", string="Mặt hàng trong đơn",
        compute="_compute_dlm_orderable_product_ids",
        help="Sản phẩm nằm trên đơn bán gắn với phiếu giao — dùng lọc dòng "
             "giao hàng, tránh giao thứ khách không đặt.")

    # ── K8 — Loại việc cho "Hàng đợi phiếu" ──────────────────────────────────
    # Một action gộp mọi loại phiếu chỉ khai được MỘT form view, mà form Nhận
    # hàng và form Kiểm hàng dùng nhãn cột trái ngược nhau ("Dự kiến/Thực nhận"
    # ≠ "NCC giao/Đạt/Loại"). Field này cho JS (picking_todo.js) biết mở phiếu
    # bằng ĐÚNG action chuyên biệt của từng loại — không dồn về một form chung.
    # Non-store: chỉ để hiển thị/định tuyến, suy thẳng từ loại hoạt động.
    dlm_picking_kind = fields.Selection([
        ("receipt", "Nhận hàng"),
        ("qc", "Kiểm hàng"),
        ("transfer", "Chuyển kho"),
        ("delivery", "Giao hàng"),
        ("vendor_return", "Trả hàng NCC"),
        ("scrap_sale", "Bán phế liệu"),
        ("to_scrap", "Hoá phế liệu"),
        ("fg_receipt", "Nhập kho từ xưởng"),
        ("other", "Khác"),
    ], string="Loại việc", compute="_compute_dlm_picking_kind")

    # ── K13 — Mặt hàng được phép lên phiếu [8] Nhập thành phẩm ────────────────
    # Danh sách CHO PHÉP (không phải loại trừ như `dlm_blocked_product_ids`): ở
    # đây tập hợp lệ nhỏ và đóng — đúng thứ xưởng làm ra — nên nói thẳng "chỉ
    # những cái này" rẻ hơn và đọc ra ngay được ý định.
    dlm_fg_product_ids = fields.Many2many(
        "product.product", string="Mặt hàng xưởng làm ra",
        compute="_compute_dlm_fg_product_ids",
        help="Sản phẩm gia công và bán thành phẩm; gắn đơn bán hàng thì thu hẹp "
             "tiếp về đúng những gì đơn đó đặt.")

    @api.depends("dlm_sale_order_id", "dlm_sale_order_id.line_ids.product_id")
    def _compute_dlm_fg_product_ids(self):
        """Lọc theo loại hàng, và THU HẸP theo đơn khi phiếu có gắn đơn.

        Thu hẹp theo đơn không phải để tiện: nhập nhầm thành phẩm của đơn khác
        vào một phiếu đã gắn đơn là làm `dlm_delivery_state` của cả hai đơn nói
        sai — một đơn tưởng đã xong, một đơn tưởng còn nợ hàng.

        🔴 K16 — PHẾ LIỆU cũng nộp về ở bảng này. Một mẻ đẻ ra ba thứ: hàng làm
        xong, bán thành phẩm, và vụn. Bắt khai vụn ở màn khác là mời người ta
        quên — mà quên thì khối lượng đầu vào không bao giờ khớp đầu ra.
        Phế liệu KHÔNG bị thu hẹp theo đơn: nó không thuộc đơn nào.
        """
        Product = self.env["product.product"]
        for picking in self:
            domain = [("product_kind", "in", list(_DLM_FG_RECEIPT_KINDS))]
            if picking.dlm_sale_order_id:
                domain.append(
                    ("id", "in",
                     picking.dlm_sale_order_id.line_ids.product_id.ids))
            products = Product.search(domain)
            picking.dlm_fg_product_ids = (
                products | Product.search([("dlm_is_scrap", "=", True)]))

    # ── K16 — Hai bảng của phiếu mẻ, cùng một `move_ids` ─────────────────────
    # Tách bằng DOMAIN chứ không bằng hai model: chúng là cùng một dòng dịch
    # chuyển, chỉ khác vai trò. Hai bảng vì hai bảng trả lời hai câu hỏi khác
    # nhau ("xưởng làm ra cái gì" / "hết bao nhiêu vật tư") và người khai nghĩ
    # về chúng ở hai thời điểm khác nhau — gộp một bảng thì cột "vai trò" phải
    # đọc kỹ mới thấy, và người ta bỏ sót bảng vật tư.
    dlm_fg_move_ids = fields.One2many(
        "stock.move", "picking_id", string="Xưởng nộp về",
        domain=[("dlm_move_kind", "=", "output")])
    dlm_material_move_ids = fields.One2many(
        "stock.move", "picking_id", string="Vật tư ra khỏi xưởng",
        domain=[("dlm_move_kind", "in", ("consume", "return"))])

    def _dlm_moves(self):
        """Dòng hàng của phiếu — HỢP của cả ba ô one2many.

        🔴 Bắt buộc, không phải cho gọn: `move_ids`, `dlm_fg_move_ids` và
        `dlm_material_move_ids` cùng trỏ vào một inverse, nhưng với giao thức
        onchange của Odoo chúng là BA ô ĐỘC LẬP. Người dùng gõ vào hai bảng của
        phiếu [8] thì client chỉ gửi lên hai field kia — `move_ids` rỗng cho tới
        khi bấm Lưu.

        Hậu quả khi đọc thẳng `move_ids`: phiếu đã có 2 dòng trên màn mà dải đỏ
        vẫn nói "Phiếu chưa có dòng nào", và nút Xác nhận bị ẩn vì `dlm_blocked`
        — người dùng nhìn thấy dòng của mình mà không có cách nào đi tiếp.

        Sau khi lưu thì ba ô cùng trỏ một tập bản ghi nên phép hợp là vô hại.
        """
        self.ensure_one()
        return self.move_ids | self.dlm_fg_move_ids | self.dlm_material_move_ids

    # ── K16 — Vật tư ĐANG NẰM ở Xưởng, cho bảng "Vật tư ra khỏi xưởng" ────────
    # Danh sách CHO PHÉP dựng từ TỒN THỰC, không từ danh mục: thứ chưa bàn giao
    # ra xưởng thì không có gì để dùng hay để trả, và cho chọn nó là mời tạo tồn
    # âm. Đây là ngoại lệ CÓ CHỦ Ý của chính sách SM-03 ("hết tồn thì vẫn hiện,
    # chỉ nói ra") — xem lý do ở `_dlm_fg_receipt_problems`.
    dlm_workshop_material_ids = fields.Many2many(
        "product.product", string="Vật tư đang ở xưởng",
        compute="_compute_dlm_workshop_material_ids")

    @api.depends("move_ids.product_id", "dlm_material_move_ids.product_id",
                 "state")
    def _compute_dlm_workshop_material_ids(self):
        xuong = self.env.ref(
            "dl_inventory.stock_location_xuong", raise_if_not_found=False)
        products = self.env["product.product"]
        if xuong:
            quants = self.env["stock.quant"].sudo().search([
                ("location_id", "=", xuong.id),
                ("quantity", ">", 0),
            ])
            products = quants.product_id
        for picking in self:
            # Dòng đã khai giữ nguyên trong danh sách kể cả khi tồn vừa về 0 —
            # không thì mở lại phiếu cũ thấy ô mặt hàng trống trơn.
            picking.dlm_workshop_material_ids = (
                products | picking._dlm_moves().filtered(
                    lambda m: m.dlm_move_kind in ("consume", "return")
                ).product_id)

    # ── K16 — Cấp vật tư BỔ SUNG ngoài định mức (phiếu [3]) ───────────────────
    # Ca thật: BOM tính 100 cây, đã cấp đủ 100, thợ cắt hỏng 1 sản phẩm và cần
    # thêm 10 cây. Không có chỗ khai thì phiếu cấp lần hai trông y hệt lần đầu,
    # và con số "hao hụt thật" vĩnh viễn không tồn tại.
    #
    # 🔴 CỐ Ý KHÔNG có tầng phê duyệt riêng ở B1: vai trò Quản đốc/QLSX chưa tồn
    # tại (xem menus.xml — "Tổ SX chưa là một vai trò ở B1"). Dựng tạm bằng CEO
    # rồi gỡ khi B2 có vai thật là làm hai lần. Lá chắn ở B1 là: vẫn phải qua
    # Thủ kho lập + hai chữ ký + lý do ghi vết + con số vượt hiện ngay trên phiếu.
    dlm_is_extra_issue = fields.Boolean(
        string="Cấp bổ sung ngoài định mức", copy=False,
        help="Đánh dấu khi phiếu này cấp thêm vật tư ngoài số BOM đã tính — "
             "làm hỏng, cắt lỗi, hao hụt thực tế cao hơn định mức.")
    dlm_extra_reason = fields.Selection([
        ("damaged", "Làm hỏng / cắt lỗi"),
        ("defect", "Vật tư lỗi phát hiện khi làm"),
        ("waste_over", "Hao hụt thực cao hơn định mức"),
        ("design_change", "Đổi thiết kế giữa chừng"),
        ("other", "Khác"),
    ], string="Lý do cấp bổ sung", copy=False)
    dlm_extra_note = fields.Char(string="Diễn giải", copy=False)

    # Đối chiếu định mức — chỉ hiện khi phiếu gắn đơn. Non-store: nó đọc tổng số
    # đã cấp của MỌI phiếu khác, thứ đổi mỗi lần có phiếu mới; lưu lại là để một
    # con số cũ nói về tình hình hôm nay.
    dlm_bom_hint = fields.Html(
        string="Đối chiếu định mức", compute="_compute_dlm_bom_hint",
        sanitize=False)

    @api.depends("dlm_sale_order_id", "move_ids.product_id",
                 "move_ids.product_uom_qty", "state")
    def _compute_dlm_bom_hint(self):
        for picking in self:
            picking.dlm_bom_hint = picking._dlm_build_bom_hint()

    # ── K12 — Hoá phế liệu ───────────────────────────────────────────────────
    # Lý do BẮT BUỘC: đây là bút toán làm một mặt hàng biến mất khỏi sổ. Không
    # có lý do thì sáu tháng sau không ai giải thích nổi vì sao 8 cây thép bốc
    # hơi — và đó đúng là lúc người ta cần giải thích.
    dlm_scrap_reason = fields.Char(
        string="Lý do hoá phế liệu", copy=False,
        help="Vì sao lô hàng này thành phế liệu: NCC giảm trừ công nợ và mình "
             "giữ hàng lại, thép để lâu bị gỉ, cắt hỏng…")
    # Nuôi nút [Chuyển thành phế liệu] trên phiếu trả đã huỷ. Non-store: nó đọc
    # TỒN THẬT, mà tồn đổi theo mọi phiếu khác — lưu lại là để một con số cũ
    # quyết định xem lối thoát còn mở hay không.
    dlm_has_stuck_stock = fields.Boolean(
        string="Còn hàng kẹt ở khu nguồn",
        compute="_compute_dlm_has_stuck_stock")

    @api.depends("state", "location_id", "move_ids.product_id")
    def _compute_dlm_has_stuck_stock(self):
        for picking in self:
            picking.dlm_has_stuck_stock = bool(
                picking.dlm_picking_kind == "vendor_return"
                and picking.state == "cancel"
                and picking._dlm_stuck_quants())

    # ── K15 — Chữ ký nhận hàng của bên Xưởng (2 bước, chặn cứng) ──────────────
    # Người dùng chốt 2026-08-13: hàng ra khỏi Kho nguyên vật liệu thì bên Xưởng
    # (trưởng Kỹ thuật) phải KÝ NHẬN, "để sau này còn truy vấn và truy cứu xem
    # ai nhận hàng".
    #
    # Vì sao chữ ký là thứ HOÀN TẤT phiếu, chứ không phải một ô điền thêm sau:
    # phiếu đã `done` là hàng đã rời sổ Kho nguyên vật liệu. Nếu chữ ký đến sau
    # đó thì luôn tồn tại một khoảng thời gian hàng "đã xuất mà chưa ai nhận" —
    # đúng khoảng trống mà việc truy cứu cần soi. Cho chữ ký làm bước validate
    # thì khoảng đó không tồn tại: chưa ký ⇒ thép vẫn thuộc kho, cả trên sổ lẫn
    # ngoài đời.
    #
    # 🔴 K16 — cùng cơ chế, HAI CHIỀU. Hàng ra xưởng thì Thủ kho giao / Kỹ thuật
    # ký; hàng từ xưởng về kho thì Kỹ thuật giao / Thủ kho ký. Nhãn vì thế không
    # được viết cứng "xưởng" nữa — chúng lấy từ `_DLM_RECEIPT_FLOWS`.
    dlm_receipt_flow = fields.Selection([
        ("none", "Không cần ký"),
        ("to_workshop", "Kho bàn giao ra xưởng"),
        ("from_workshop", "Xưởng nộp về kho"),
    ], string="Chiều bàn giao", compute="_compute_dlm_receipt_state", store=True)
    dlm_needs_receipt = fields.Boolean(
        string="Cần chữ ký nhận hàng", compute="_compute_dlm_receipt_state",
        store=True)
    # 🔴 store=True (đổi ở K16, trước là non-stored): màn phiếu [8] lọc và nhóm
    # theo field này — "phiếu nào đang chờ tôi đếm" là hàng đợi thật của Thủ
    # kho. Field compute non-stored KHÔNG dùng được trong domain/group_by, và
    # Odoo báo lỗi lúc nạp view chứ không âm thầm bỏ qua. Mọi `depends` đều là
    # field đã lưu nên tính lại đúng và rẻ.
    dlm_receipt_state = fields.Selection([
        ("none", "Không cần ký"),
        ("ready", "Chờ bàn giao"),
        ("waiting", "Chờ bên nhận xác nhận"),
        ("received", "Bên nhận đã ký"),
    ], string="Tình trạng bàn giao", compute="_compute_dlm_receipt_state",
        store=True)
    # store=True cho CẢ BỐN field của compute này — không phải vì cần tra cứu,
    # mà vì Odoo cảnh báo (registry.field_computed) khi một compute vừa ghi field
    # lưu vừa ghi field không lưu: đọc field không lưu sẽ âm thầm ghi lại field
    # lưu. Đồng nhất rẻ hơn tách làm hai hàm cho cùng một phép suy luận.
    dlm_receiver_label = fields.Char(
        string="Bên nhận", compute="_compute_dlm_receipt_state", store=True,
        help="Ai phải ký nhận phiếu này — đọc từ chiều bàn giao.")
    # copy=False: nhân bản phiếu mà kéo theo chữ ký cũ là chế ra bằng chứng một
    # lần nhận hàng chưa từng xảy ra.
    dlm_handover_uid = fields.Many2one(
        "res.users", string="Thủ kho bàn giao", readonly=True, copy=False)
    dlm_handover_date = fields.Datetime(
        string="Thời điểm bàn giao", readonly=True, copy=False)
    dlm_received_uid = fields.Many2one(
        "res.users", string="Người nhận (bên Xưởng)", readonly=True, copy=False)
    dlm_received_date = fields.Datetime(
        string="Thời điểm nhận", readonly=True, copy=False)

    # Depends `picking_type_id` chứ không `dlm_picking_kind`: field kia cũng là
    # computed non-stored, xâu chuỗi hai lớp compute chỉ để đọc lại đúng cái
    # `picking_type_id` mà mình đã có sẵn.
    @api.depends("picking_type_id", "location_dest_id",
                 "dlm_handover_uid", "dlm_received_uid")
    def _compute_dlm_receipt_state(self):
        # ĐÍCH DANH, không `child_of`: từ K15 Xưởng sản xuất là ô LÁ. Ngày nào
        # ai đó chia nó thành nhiều máy/tổ thì đây là chỗ phải sửa — và sửa
        # thành `child_of` sẽ đúng, không phải sửa cả cơ chế.
        xuong = self.env.ref(
            "dl_inventory.stock_location_xuong", raise_if_not_found=False)
        for picking in self:
            if picking.dlm_picking_kind == "fg_receipt":
                flow = "from_workshop"
            elif (xuong and picking.dlm_picking_kind == "transfer"
                    and picking.location_dest_id == xuong):
                flow = "to_workshop"
            else:
                flow = "none"
            picking.dlm_receipt_flow = flow
            picking.dlm_needs_receipt = flow != "none"
            picking.dlm_receiver_label = (
                _DLM_RECEIPT_FLOWS[flow][1] if flow != "none" else "")
            if flow == "none":
                picking.dlm_receipt_state = "none"
            elif picking.dlm_received_uid:
                picking.dlm_receipt_state = "received"
            elif picking.dlm_handover_uid:
                picking.dlm_receipt_state = "waiting"
            else:
                picking.dlm_receipt_state = "ready"

    # ── K5 — Trạng thái kiểm hàng ────────────────────────────────────────────
    dlm_is_qc = fields.Boolean(
        string="Là phiếu kiểm hàng", compute="_compute_dlm_is_qc")
    dlm_qty_rejected_total = fields.Float(
        string="Số loại", digits="Product Unit of Measure",
        compute="_compute_dlm_qty_rejected_total", store=True)
    dlm_qc_state = fields.Selection([
        ("none", "—"),
        ("pending", "Chờ kiểm"),
        ("passed", "Đạt toàn bộ"),
        ("has_reject", "Có hàng loại"),
    ], string="Kết quả kiểm", compute="_compute_dlm_qc_state", store=True)

    # ── K5 — Chặn xác nhận + dải thông báo (INLINE, không modal) ─────────────
    dlm_blocked = fields.Boolean(
        string="Đang bị chặn", compute="_compute_dlm_banner")
    dlm_banner_level = fields.Selection([
        ("info", "Thông tin"),
        ("success", "Xong"),
        ("warning", "Cảnh báo"),
        ("danger", "Chặn"),
    ], string="Mức thông báo", compute="_compute_dlm_banner")
    dlm_banner_message = fields.Html(
        string="Thông báo", compute="_compute_dlm_banner", sanitize=False)

    # ── Compute ──────────────────────────────────────────────────────────────
    @api.depends("picking_type_id")
    def _compute_dlm_is_qc(self):
        for picking in self:
            picking.dlm_is_qc = (
                picking.picking_type_id.sequence_code == _DLM_QC_CODE)

    @api.depends("picking_type_id")
    def _compute_dlm_picking_kind(self):
        """Suy loại việc từ loại hoạt động — thứ tự kiểm QUAN TRỌNG.

        Phiếu kiểm (KC), chuyển kho (CK), hoá phế liệu (HPL) và nhập thành phẩm
        (NTP) đều là `internal`;
        phiếu trả (TR) và bán phế liệu (BPL) đều là `outgoing`. Phải khớp
        `sequence_code` TRƯỚC khi rơi về `code`, không thì kiểm hàng bị nhận nhầm
        là chuyển kho — và phiếu hoá phế liệu mở bằng form chuyển kho, nơi hai ô
        vị trí sửa được tự do (đúng thứ §11.14 cấm).
        """
        for picking in self:
            code = picking.picking_type_id.code
            seq = picking.picking_type_id.sequence_code
            if code == "incoming":
                kind = "receipt"
            elif seq == _DLM_QC_CODE:
                kind = "qc"
            elif seq == _DLM_RETURN_CODE:
                kind = "vendor_return"
            elif seq == "BPL":
                kind = "scrap_sale"
            elif seq == _DLM_TO_SCRAP_CODE:
                kind = "to_scrap"
            elif seq == _DLM_FG_RECEIPT_CODE:
                kind = "fg_receipt"
            elif code == "internal":
                kind = "transfer"
            elif code == "outgoing":
                kind = "delivery"
            else:
                kind = "other"
            picking.dlm_picking_kind = kind

    @api.depends("dlm_origin_picking_id", "state", "move_ids")
    def _compute_dlm_return_count(self):
        for picking in self:
            picking.dlm_return_count = len(picking._dlm_vendor_returns())

    @api.depends("move_ids.product_uom_qty",
                 "dlm_fg_move_ids.product_uom_qty",
                 "dlm_material_move_ids.product_uom_qty")
    def _compute_dlm_qty_total(self):
        for picking in self:
            picking.dlm_qty_total = sum(
                picking._dlm_moves().mapped("product_uom_qty"))

    @api.depends("move_ids.dlm_reject_reason", "move_ids.dlm_reject_note")
    def _compute_dlm_reject_summary(self):
        """Gộp lý do loại của các dòng thành MỘT dòng đọc được trên list.

        Mua hàng cần biết "trả vì cái gì" ngay ở danh sách để xếp thứ tự gọi NCC
        — giao sai mặt hàng gấp hơn hẳn vài cây thép cong.
        """
        labels = dict(
            self.env["stock.move"]._fields["dlm_reject_reason"].selection)
        for picking in self:
            reasons = []
            for reason in picking.move_ids.mapped("dlm_reject_reason"):
                if reason and labels.get(reason) not in reasons:
                    reasons.append(labels.get(reason))
            picking.dlm_reject_summary = ", ".join(reasons)

    @api.depends("location_id", "location_dest_id")
    def _compute_dlm_blocked_product_ids(self):
        """SM-03 (sửa 2026-08-12): loại trừ theo LUẬT của hai đầu phiếu.

        Bản đầu lọc thêm "phải có tồn > 0 ở nơi lấy". Đúng nghiệp vụ (chọn hàng
        không có tồn thì phiếu treo) nhưng sai UX: thủ kho gõ tên vật tư mình
        BIẾT là kho có ghi nhận, dropdown không ra gì, và không có cách nào phân
        biệt "khu đó hết hàng" với "hệ thống hỏng". Hết hàng là tình trạng nhất
        thời — nó phải được NÓI RA (nhãn trong dropdown, cột "Tồn ở nơi lấy",
        dải cảnh báo), không phải bị giấu đi.

        Loại hàng cấm ở một khu thì ngược lại: là luật cố định (§4.2 "Món nào
        nằm ở đâu") nên vẫn lọc thẳng khỏi danh sách. Ràng CẢ HAI ĐẦU, không
        chỉ đầu nhận: tuyến "Vật tư ra xưởng" lấy hàng từ Khu nhập hàng — nơi
        chỉ có vật tư và hàng thương mại — nên xổ ra cả BTP lẫn sản phẩm gia
        công là mời chọn thứ chưa từng và sẽ không bao giờ nằm ở đó.

        Là danh sách LOẠI TRỪ chứ không phải danh sách cho phép: khi cả hai đầu
        đều không hạn chế thì field rỗng và `('id','not in',[])` cho qua tất cả
        — không phải nạp cả danh mục sản phẩm vào form chỉ để nói "không cấm
        gì".
        """
        Product = self.env["product.product"]
        for picking in self:
            domain = picking._dlm_transfer_allowed_domain()
            if domain is None:
                picking.dlm_blocked_product_ids = Product
            else:
                # NOT của vị từ, chạy dưới SQL — không nạp cả danh mục vào RAM.
                picking.dlm_blocked_product_ids = Product.search(
                    ["!"] + domain)

    def _dlm_transfer_allowed_domain(self):
        """Vị từ mặt hàng hợp lệ ở CẢ nơi lấy lẫn nơi nhận (None = không hạn chế).

        GIAO hai vị từ, không phải hợp: mặt hàng phải vừa nằm được ở nơi lấy vừa
        nằm được ở nơi nhận. Với domain, phép giao là `expression.AND` — và nó
        vẫn đúng khi hai vị từ đọc hai field khác nhau (`product_kind` ở đầu
        này, `dlm_is_scrap` ở đầu kia), thứ mà phép giao hai tuple không làm nổi.

        Phân biệt `None` (không đầu nào ràng) với một domain **không khớp gì**
        (hai đầu ràng nhưng không có mặt hàng chung — cấm sạch): trả `None` cho
        ca thứ hai là mở toang đúng lúc phải đóng chặt nhất.
        """
        self.ensure_one()
        domains = [
            self._dlm_location_rule(location)[0]
            for location in (self.location_id, self.location_dest_id)
        ]
        domains = [d for d in domains if d]
        if not domains:
            return None
        return expression.AND(domains)

    def _dlm_location_rule(self, location):
        """(vị từ, nhãn, lý do) của một vị trí — `([], "", "")` = không hạn chế.

        Khớp theo CÂY (`parent_path`) chứ không theo đúng một bản ghi: ngày ai
        đó chia "DL/TP/Khu A" mà luật chỉ khớp `DL/TP` thì vật tư lại vào được,
        không lỗi nào nổ. Khu con vì thế thừa hưởng luật của khu cha — trừ khu
        nào có luật RIÊNG đứng trước trong `_DLM_LOCATION_RULES` (Kho nguyên
        vật liệu, khu Phế liệu — cả hai đều là con của Kho nhà máy sản xuất và
        vì thế PHẢI đứng trước luật của khu đó).
        """
        if not location or not location.parent_path:
            return [], "", ""
        for xml_id, domain, label, reason in _DLM_LOCATION_RULES:
            area = self.env.ref(xml_id, raise_if_not_found=False)
            if (area and area.parent_path
                    and location.parent_path.startswith(area.parent_path)):
                return domain, label, reason
        return [], "", ""

    def _dlm_dest_rule(self):
        """Luật của vị trí ĐÍCH — vị từ + nhãn + lý do.

        Neo vào VỊ TRÍ ĐÍCH chứ không vào nút lối tắt vừa bấm: hai ô vị trí vẫn
        là nguồn sự thật (xem ghi chú ở `action_dlm_preset_to_workshop`), người
        dùng sửa tay sau khi bấm nút thì cái nút không hề biết.

        CỐ Ý chỉ soi đầu ĐÍCH, không soi đầu nguồn như
        `_dlm_transfer_allowed_domain`: đây là lá chắn CHẶN lúc xác nhận, và câu
        chặn nói "không được đưa VÀO %s". Hàng sai chỗ ở đầu nguồn thì đã có
        cảnh báo hết tồn bắt (không thể lấy ra thứ không nằm ở đó), không cần
        chặn cứng thêm lần nữa.
        """
        self.ensure_one()
        return self._dlm_location_rule(self.location_dest_id)

    @api.depends("dlm_sale_order_id", "dlm_sale_order_id.line_ids.product_id")
    def _compute_dlm_orderable_product_ids(self):
        """SM-04: SP nằm trên đơn bán gắn với phiếu giao. Rỗng khi chưa gắn đơn
        (khi đó form khoá bảng dòng + mời chọn đơn — xem delivery_views)."""
        for picking in self:
            picking.dlm_orderable_product_ids = (
                picking.dlm_sale_order_id.line_ids.product_id)

    @api.depends("move_ids.dlm_qty_rejected")
    def _compute_dlm_qty_rejected_total(self):
        for picking in self:
            picking.dlm_qty_rejected_total = sum(
                picking.move_ids.mapped("dlm_qty_rejected"))

    @api.depends("state", "picking_type_id", "dlm_qty_rejected_total")
    def _compute_dlm_qc_state(self):
        for picking in self:
            if picking.picking_type_id.sequence_code != _DLM_QC_CODE:
                picking.dlm_qc_state = "none"
            elif picking.dlm_qty_rejected_total > 0:
                picking.dlm_qc_state = "has_reject"
            elif picking.state == "done":
                picking.dlm_qc_state = "passed"
            else:
                picking.dlm_qc_state = "pending"

    @api.depends(
        "state", "picking_type_id", "partner_id", "location_id",
        "location_dest_id", "dlm_qty_rejected_total",
        "move_ids.quantity", "move_ids.product_uom_qty", "move_ids.dlm_qc_over",
        "move_ids.dlm_qty_rejected", "move_ids.dlm_reject_reason",
        "move_ids.dlm_reject_note", "move_ids.product_id", "move_ids.state",
        "move_line_ids.lot_id", "move_line_ids.lot_name",
        "dlm_handover_uid", "dlm_received_uid",
        # 🔴 Hai ô của phiếu [8] phải có mặt trong depends, không thì dải không
        # nổ lại khi người dùng gõ dòng vào chúng — xem `_dlm_moves`.
        "dlm_fg_move_ids.product_id", "dlm_fg_move_ids.product_uom_qty",
        "dlm_fg_move_ids.dlm_move_kind",
        "dlm_material_move_ids.product_id",
        "dlm_material_move_ids.product_uom_qty",
        "dlm_material_move_ids.dlm_move_kind")
    def _compute_dlm_banner(self):
        """MỘT dải thông báo theo ngữ cảnh cho cả phiếu nhận lẫn phiếu kiểm.

        Gộp thay vì rải nhiều `<div class="alert">` có điều kiện chồng nhau —
        tiền lệ đã chốt ở form Báo giá (`_compute_status_banner`): mỗi trạng
        thái chỉ được hiện đúng MỘT dải, nội dung do model quyết định.

        Dải phải nêu **hệ quả** ("sẽ tạo phiếu trả nháp cho Mua hàng"), không
        chỉ nêu sự kiện — người dùng cần biết bấm tiếp thì chuyện gì xảy ra.
        """
        for picking in self:
            level, message, blocked = picking._dlm_banner_vals()
            picking.dlm_banner_level = level
            picking.dlm_banner_message = message
            picking.dlm_blocked = blocked

    def _dlm_banner_vals(self):
        """Trả về (mức, nội dung HTML, có chặn xác nhận không)."""
        self.ensure_one()
        if self.state in ("cancel",):
            return False, False, False
        if self.dlm_is_qc:
            return self._dlm_banner_qc()
        if self.picking_type_id.code == "incoming":
            return self._dlm_banner_receipt()
        if self.picking_type_id.sequence_code == _DLM_RETURN_CODE:
            return self._dlm_banner_return()
        if self.picking_type_id.sequence_code == "BPL":
            return self._dlm_banner_scrap_sale()
        # PHẢI đứng trước nhánh `internal` chung: HPL cũng là internal, rơi vào
        # dải Chuyển kho thì nó nói "sẽ dời hàng sang vị trí đích" — sai hẳn
        # bản chất (đây là ĐỔI MẶT HÀNG, không đảo ngược được).
        if self.picking_type_id.sequence_code == _DLM_TO_SCRAP_CODE:
            return self._dlm_banner_to_scrap()
        # Cũng phải đứng trước nhánh `internal` chung, và vì một lý do NẶNG hơn
        # nhãn sai: dải Chuyển kho gọi `_dlm_shortage_lines`, mà nguồn của phiếu
        # [8] là vị trí ẢO Sản xuất — nơi không bao giờ có tồn. Rơi vào đó thì
        # MỌI phiếu nhập thành phẩm đều bị bêu "không đủ hàng để chuyển".
        if self.picking_type_id.sequence_code == _DLM_FG_RECEIPT_CODE:
            return self._dlm_banner_fg_receipt()
        if self.picking_type_id.code == "outgoing":
            return self._dlm_banner_delivery()
        if self.picking_type_id.code == "internal":
            return self._dlm_banner_transfer()
        return False, False, False

    # ── RS-11 — Ca ngoại lệ báo INLINE, không modal tiếng Anh ────────────────
    def _dlm_confirm_problems(self):
        """Lỗi CHẶN xác nhận, dùng chung cho dải đỏ và guard server.

        Một nguồn sự thật: dải đỏ trên form và lỗi khi bấm phải nói cùng một
        câu, không thì người dùng sửa theo dải rồi vẫn bị chặn bởi câu khác.
        """
        self.ensure_one()
        problems = []
        if (self.dlm_picking_kind == "transfer" and self.location_id
                and self.location_id == self.location_dest_id):
            problems.append(_(
                "Lấy hàng từ và Chuyển tới đang là cùng một chỗ (%s) — phiếu "
                "này không làm tồn kho thay đổi gì.")
                % self.location_id.display_name)
        # Lá chắn server cho §4.1.1: domain trên view chỉ lọc dropdown, còn
        # import/RPC vẫn nhét được khu quá cảnh (Chờ kiểm / Chờ trả NCC / Khu
        # nhập cha) vào phiếu. Rút tay khỏi chúng = QC hình thức hoặc xoá bằng
        # chứng đòi NCC. Số ở đó chỉ đổi qua phiếu Nhận / Kiểm & cất / Trả.
        #
        # 🔴 K11 — luật phát biểu theo VỊ TRÍ, không theo MÀN. Bản trước chỉ áp
        # cho `dlm_picking_kind == "transfer"` nên phiếu GIAO HÀNG lấy nguồn
        # "Chờ kiểm hàng" lọt sạch ⇒ giao thẳng hàng chưa kiểm cho khách, nặng
        # hơn hẳn hai cửa kia cộng lại. Lá chắn neo vào loại việc thì loại việc
        # thứ tám sẽ lọt — đã sai hai lần, lần này bỏ hẳn điều kiện.
        #
        # Phiếu do HỆ THỐNG sinh (Nhận hàng, Kiểm & cất, Trả NCC) vẫn phải đi
        # qua hai khu đó — đấy là việc của chúng. Nhận biết bằng loại việc, và
        # đây là chiều NGƯỢC lại: liệt kê ai ĐƯỢC phép, không liệt kê ai bị cấm.
        if self.dlm_picking_kind not in _DLM_TRANSIT_KINDS:
            cam = (self.location_id | self.location_dest_id).filtered(
                "dlm_no_inventory")
            if cam:
                problems.append(_(
                    "Không được chọn khu quá cảnh (%s) trên phiếu này — số ở đó "
                    "chỉ đổi qua phiếu Nhận hàng / Kiểm & cất / Trả NCC. "
                    "Chọn khu chứa hàng thật.")
                    % ", ".join(cam.mapped("display_name")))
        rong = [
            move.product_id.display_name for move in self._dlm_moves()
            if float_compare(move.product_uom_qty, 0.0,
                             precision_rounding=move.product_uom.rounding
                             or 0.01) <= 0]
        if rong:
            problems.append(_(
                "Số lượng phải lớn hơn 0: %s.") % ", ".join(rong))
        # Lọc dropdown chỉ chặn được dòng THÊM MỚI. Ca lọt: thêm dòng vật tư
        # (tuyến mặc định ra xưởng — hợp lệ) rồi mới bấm lối tắt sang Kho thành
        # phẩm — `_dlm_set_transfer_route` ghi đè đích của CẢ dòng đã có, dòng
        # vật tư âm thầm thành sai chỗ mà không ô nào đổi màu.
        problems.extend(self._dlm_dest_rule_problems())
        if self.dlm_picking_kind == "fg_receipt":
            problems.extend(self._dlm_fg_receipt_problems())
        # K16 — cấp bổ sung ngoài định mức phải nói VÌ SAO ngay lúc cấp. Hỏi sau
        # thì không ai nhớ, và đây là dữ liệu duy nhất cho biết hao hụt thật lệch
        # định mức bao nhiêu.
        if self.dlm_is_extra_issue and not self.dlm_extra_reason:
            problems.append(_(
                "Phiếu đánh dấu \"Cấp bổ sung ngoài định mức\" thì phải chọn "
                "lý do — đây là chỗ duy nhất ghi lại vì sao xưởng cần thêm vật "
                "tư ngoài BOM."))
        return problems

    def _dlm_dest_rule_problems(self):
        """Luật "khu nào chứa hàng gì" — áp theo ĐÍCH CỦA TỪNG DÒNG.

        🔴 K12 — không soi `self.location_dest_id` nữa. Hai loại phiếu đã có
        đích khác nhau trên từng dòng: [2] Kiểm & cất định tuyến 3 ngả, và [9]
        Hoá phế liệu có dòng ra đi vào Điều chỉnh tồn còn dòng vào đi vào khu
        Phế liệu. Soi đích đầu phiếu là kết luận SAI cho cả hai — với phiếu [9]
        nó sẽ chặn đúng dòng thép gốc, thứ bắt buộc phải có.
        """
        self.ensure_one()
        problems = []
        theo_dich = {}
        for move in self._dlm_moves():
            if not move.product_id:
                continue
            dest = move.location_dest_id or self.location_dest_id
            # filtered_domain: đánh giá vị từ trong Python trên đúng mặt hàng
            # đang xét. Không dùng `product_kind not in kinds` nữa — luật khu
            # Phế liệu đọc `dlm_is_scrap`, không đọc `product_kind`.
            domain, label, reason = self._dlm_location_rule(dest)
            if not domain or move.product_id.filtered_domain(domain):
                continue
            theo_dich.setdefault(
                (dest, label, reason), []).append(move.product_id.display_name)
        for (dest, label, reason), ten in theo_dich.items():
            # Câu chặn sinh từ chính bản đồ luật (nhãn nằm trong luật): câu viết
            # cứng theo một khu sẽ nói sai khu ngay khi có luật thứ hai.
            problems.append(_(
                "%s không được đưa vào %s — khu này chỉ chứa: %s. %s"
            ) % (", ".join(dict.fromkeys(ten)), dest.display_name,
                 label, reason))
        return problems

    def _dlm_banner_problems(self, problems, loi_mo_dau):
        """Dải đỏ chuẩn cho danh sách lỗi chặn."""
        return "danger", "%s<ul>%s</ul>" % (
            loi_mo_dau,
            "".join("<li>%s</li>" % p for p in problems)), True

    def _dlm_banner_transfer(self):
        """Dải cho phiếu [4] Chuyển kho nội bộ."""
        if self.state == "done":
            if self.dlm_received_uid:
                return "success", _(
                    "Đã bàn giao ra Xưởng sản xuất. <b>%s</b> ký nhận lúc %s."
                ) % (self.dlm_received_uid.name,
                     format_datetime(self.env, self.dlm_received_date)), False
            return "success", _("Đã chuyển hàng sang vị trí đích."), False
        # K15 — đứng TRƯỚC `_dlm_confirm_problems`: khi đã bàn giao thì việc còn
        # lại không phải của thủ kho nữa, dải phải nói ai đang cầm bóng chứ
        # không lặp lại checklist mà họ đã làm xong.
        if self.dlm_receipt_state == "waiting":
            return "warning", _(
                "<b>%s</b> đã bàn giao lúc %s — phiếu đang chờ bên Xưởng "
                "(Kỹ thuật) bấm <b>Xác nhận đã nhận</b>. Hàng vẫn thuộc Kho "
                "nguyên vật liệu cho tới lúc đó."
            ) % (self.dlm_handover_uid.name,
                 format_datetime(self.env, self.dlm_handover_date)), False
        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        # Chuyển nhiều hơn tồn ở khu nguồn: domain SM-03 chỉ lọc mặt hàng CÓ tồn
        # (>0), không nói gì về SỐ LƯỢNG — chọn đúng mặt hàng rồi gõ số vượt tồn
        # vẫn lọt. Native để phiếu treo `confirmed` mà không nói vì sao.
        thieu = self._dlm_shortage_lines()
        if thieu:
            return "warning", _(
                "%s không đủ hàng để chuyển:<ul>%s</ul>Xác nhận thì phiếu treo "
                "chờ hàng, không chuyển được ngay. Sửa lại số, hoặc chọn khu "
                "khác đang có hàng."
            ) % (self.location_id.display_name or _("Khu nguồn"),
                 "".join("<li>%s</li>" % t for t in thieu)), False
        if self.state == "draft":
            # Nói ra vì sao danh sách mặt hàng ngắn đi — không giải thích thì
            # dropdown thiếu món thành bí ẩn, đúng cái bẫy mà việc bỏ lọc "hết
            # hàng" vừa gỡ ra.
            notice = self._dlm_kinds_notice()
            if notice:
                return "info", notice, False
            return "info", _(
                "Chọn nơi lấy hàng và nơi nhận, hoặc bấm một trong hai lối tắt "
                "phía trên. Xác nhận phiếu để hệ thống <b>giữ chỗ</b> hàng."
            ), False
        if self.dlm_needs_receipt:
            return "info", _(
                "Đã giữ chỗ. Bấm <b>Bàn giao ra xưởng</b> khi cân đo và trao "
                "hàng xong — phiếu sẽ chờ bên Xưởng ký nhận rồi mới hoàn tất."
            ), False
        return "info", _(
            "Đã giữ chỗ. Xác nhận chuyển kho sẽ dời hàng sang vị trí đích."
        ), False

    def _dlm_kinds_notice(self):
        """Câu giải thích danh sách mặt hàng bị thu hẹp (rỗng nếu không hạn chế).

        Gộp hai đầu vào MỘT câu thay vì mỗi đầu một dải: người dùng chỉ cần
        biết "phiếu này chuyển được những loại gì", không cần biết luật đến từ
        đầu nào.
        """
        self.ensure_one()
        ten = self._dlm_allowed_label()
        if not ten:
            return ""
        return _(
            "Phiếu đi từ <b>%s</b> sang <b>%s</b> nên chỉ chuyển được: "
            "<b>%s</b> — danh sách mặt hàng đã bỏ các loại khác. Mặt hàng đang "
            "hết ở nơi lấy <b>vẫn hiện</b>, có ghi rõ <i>hết hàng</i>."
        ) % (self.location_id.display_name or _("(chưa chọn)"),
             self.location_dest_id.display_name or _("(chưa chọn)"), ten)

    def _dlm_allowed_label(self):
        """Nhãn KẾT QUẢ CUỐI của hai đầu phiếu ("" = không hạn chế).

        🔴 Phải là GIAO của hai đầu, không phải ghép hai luật. Nơi lấy "Kho
        nguyên vật liệu" (vật tư + BTP) giao nơi nhận "Xưởng sản xuất" (vật tư +
        BTP + gia công) ⇒ đúng **Vật tư, Bán thành phẩm** — KHÔNG kèm hàng gia
        công. Ghép lại là liệt kê cả thứ phiếu KHÔNG chuyển được, đúng cái bí ẩn
        mà dải này sinh ra để gỡ.

        Hai đầu đều theo `product_kind` ⇒ giao được thành tuple, đọc nhãn từ
        chính selection field (một nguồn tên gọi). Có đầu KHÔNG theo loại hàng
        (khu Phế liệu đọc cờ `dlm_is_scrap`) ⇒ giao không biểu diễn được bằng
        loại hàng, dùng nhãn riêng của luật đó: nó luôn là luật HẸP hơn — cả bốn
        luật theo loại đều cho `material`, mà phế liệu chính là một `material`.
        """
        self.ensure_one()
        rules = [self._dlm_location_rule(location)
                 for location in (self.location_id, self.location_dest_id)]
        rules = [r for r in rules if r[0]]
        if not rules:
            return ""
        khong_theo_loai = [r for r in rules if _dlm_domain_kinds(r[0]) is None]
        if khong_theo_loai:
            return khong_theo_loai[0][1]
        kinds = None
        for domain, _label, _reason in rules:
            cua_khu = _dlm_domain_kinds(domain)
            kinds = cua_khu if kinds is None else tuple(
                k for k in kinds if k in cua_khu)
        labels = dict(self.env["product.product"].fields_get(
            ["product_kind"])["product_kind"]["selection"])
        return ", ".join(labels.get(k, k) for k in kinds) or _("không loại nào")

    def _dlm_shortage_lines(self):
        """Dòng đang đòi chuyển nhiều hơn tồn thực ở khu nguồn.

        Cộng gộp theo mặt hàng: hai dòng cùng SP mỗi dòng 3 trong khi tồn 5 thì
        từng dòng đều "đủ" mà cả phiếu vẫn thiếu.

        Đọc số KHẢ DỤNG (đã trừ chỗ giữ của phiếu khác) — xem
        `_dlm_qty_available`. Câu báo tách ba ca vì ba ca phải làm ba việc khác
        nhau: hết sạch ⇒ đi mua · bị giữ hết ⇒ đi nói chuyện với người giữ ·
        thiếu một phần ⇒ chuyển ít lại hoặc chờ.
        """
        self.ensure_one()
        can = {}
        for move in self.move_ids:
            if move.state in ("done", "cancel"):
                continue
            can.setdefault(move.product_id, 0.0)
            can[move.product_id] += move.product_uom_qty
        thieu = []
        for product, qty in can.items():
            con = self._dlm_qty_available(product)
            rounding = product.uom_id.rounding or 0.01
            if float_compare(qty, con, precision_rounding=rounding) <= 0:
                continue
            ten = product.display_name
            dvt = product.uom_id.name
            if float_compare(con, 0.0, precision_rounding=rounding) > 0:
                thieu.append(
                    _("%s: cần chuyển %s nhưng ở đó chỉ còn %s %s dùng được")
                    % (ten, _dlm_fmt(qty), _dlm_fmt(con), dvt))
                continue
            # Khả dụng = 0. Còn tồn thực nghĩa là hàng CÓ mặt nhưng đã có chủ —
            # gộp chung với "hết hàng" là đẩy người dùng đi mua thứ đang nằm
            # trong kho.
            tren_ke = self._dlm_qty_on_hand(product)
            if float_compare(tren_ke, 0.0, precision_rounding=rounding) > 0:
                thieu.append(_(
                    "%s: nơi lấy còn %s %s nhưng <b>phiếu khác đã giữ hết</b> — "
                    "cần chuyển %s. Xem ai đang giữ ở màn Tồn kho, cột "
                    "<b>Đang giữ chỗ</b>.")
                    % (ten, _dlm_fmt(tren_ke), dvt, _dlm_fmt(qty)))
            else:
                thieu.append(_("%s: nơi lấy <b>đang hết hàng</b> (tồn 0) — "
                               "cần chuyển %s %s") % (ten, _dlm_fmt(qty), dvt))
        return thieu

    def _dlm_banner_scrap_sale(self):
        """Dải cho phiếu [6] Bán phế liệu."""
        if self.state == "done":
            return "success", _("Đã giao phế liệu cho người mua."), False
        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        # Bán nhiều hơn tồn ở khu phế liệu: native chỉ để phiếu treo `confirmed`
        # mà không nói vì sao. Nêu thẳng số cân được.
        # ⚠️ `_dlm_qty_available` cộng lại phần CHÍNH phiếu này đang giữ, nếu
        # không thì phiếu vừa xác nhận xong sẽ tự tố mình bán quá tay.
        thieu = []
        for move in self.move_ids:
            con = self._dlm_qty_available(move.product_id)
            rounding = move.product_uom.rounding or 0.01
            if float_compare(move.product_uom_qty, con,
                             precision_rounding=rounding) > 0:
                thieu.append(_("%s: bán %s nhưng khu phế liệu chỉ còn %s %s "
                               "dùng được") % (
                    move.product_id.display_name,
                    _dlm_fmt(move.product_uom_qty), _dlm_fmt(con),
                    move.product_uom.name))
        if thieu:
            return "warning", _(
                "Số bán đang vượt tồn thực:<ul>%s</ul>Xác nhận thì phiếu treo "
                "chờ hàng, không giao được. Cân lại rồi sửa số."
            ) % "".join("<li>%s</li>" % t for t in thieu), False
        return "info", _(
            "Nhập số cân thực tế và đơn giá thoả thuận với người mua."), False

    def _dlm_qty_available(self, product, location=None):
        """Số KHẢ DỤNG của `product` tại/dưới vị trí lấy hàng của phiếu.

        Chỉ là lớp vỏ mỏng quanh `stock.quant._dlm_available_qty` — toàn bộ lập
        luận (vì sao trừ chỗ giữ, vì sao cộng lại phần của chính mình) nằm ở đó,
        một chỗ duy nhất.
        """
        self.ensure_one()
        location = location or self.location_id
        return self.env["stock.quant"]._dlm_available_qty(
            product, location, own_move_lines=self.move_ids.move_line_ids)

    def _dlm_qty_on_hand(self, product, location=None):
        """Tồn THỰC (chưa trừ chỗ giữ) — chỉ để nói đúng LÝ DO khi thiếu."""
        self.ensure_one()
        location = location or self.location_id
        return self.env["stock.quant"]._dlm_on_hand_qty(product, location)

    def _dlm_banner_qc(self):
        """Dải cho phiếu [2] Kiểm & cất hàng."""
        if self.state == "done":
            if self.dlm_qty_rejected_total > 0:
                returns = ", ".join(self._dlm_vendor_returns().mapped("name"))
                return "warning", _(
                    "Đã cất hàng đạt vào kho. <b>%s</b> đơn vị hàng loại đang ở "
                    "khu <b>Chờ trả NCC</b>%s — Mua hàng xử lý tiếp với nhà "
                    "cung cấp."
                ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                     _(" (phiếu %s)") % returns if returns else ""), False
            return "success", _("Đã kiểm đạt toàn bộ và cất vào kho."), False

        problems = self._dlm_qc_problems()
        if problems:
            return "danger", _(
                "Chưa xác nhận kiểm được:<ul>%s</ul>"
            ) % "".join("<li>%s</li>" % p for p in problems), True

        if self.dlm_qty_rejected_total > 0:
            return "warning", _(
                "Xác nhận kiểm sẽ chuyển <b>%s</b> đơn vị hàng loại sang khu "
                "<b>Chờ trả NCC</b> và tạo <b>phiếu trả hàng (nháp)</b> để Mua "
                "hàng thoả thuận với %s. Phần đạt được cất vào kho."
            ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                 self.partner_id.display_name or _("nhà cung cấp")), False

        return "info", _(
            "Nhập số <b>Đạt</b> và số <b>Loại</b> cho từng dòng. Chưa kiểm hết "
            "cũng xác nhận được — phần còn lại tự tách sang một phiếu kiểm mới."
        ), False

    def _dlm_banner_receipt(self):
        """Dải cho phiếu [1] Nhận hàng NCC."""
        if self.state == "done":
            return "success", _(
                "Đã nhận hàng vào khu <b>Chờ kiểm hàng</b>. Bước tiếp theo là "
                "<b>kiểm & cất hàng</b>."), False

        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))

        # SM-07: mặt hàng NCC này chưa có bảng giá ĐANG ÁP DỤNG ⇒ giá vốn có thể
        # trống/sai. Chỉ CẢNH BÁO (không chặn — hàng đã về, vẫn phải nhập); nêu
        # ở mọi bước trước khi xong để còn kịp báo Mua hàng chốt giá.
        unpriced = self._dlm_receipt_unpriced_names()
        price_block = _(
            "<b>Chưa có bảng giá đang áp dụng</b> từ NCC này cho:<ul>%s</ul>"
            "Giá vốn có thể chưa cập nhật — báo <b>Mua hàng</b> chốt giá. "
            "Vẫn nhận hàng bình thường."
        ) % "".join("<li>%s</li>" % n for n in unpriced) if unpriced else ""

        if self.state == "draft":
            if price_block:
                return "warning", price_block, False
            return False, False, False

        short = []
        for move in self.move_ids:
            rounding = move.product_uom.rounding or 0.01
            if float_compare(move.quantity, move.product_uom_qty,
                             precision_rounding=rounding) < 0:
                short.append(_("%s: thiếu %s %s") % (
                    move.product_id.display_name,
                    _dlm_fmt(move.product_uom_qty - move.quantity),
                    move.product_uom.name))
        if short:
            message = _(
                "NCC giao thiếu so với dự kiến:<ul>%s</ul>Xác nhận sẽ tạo "
                "<b>phiếu chờ giao tiếp</b> cho phần còn thiếu — không phải "
                "hàng lỗi, đừng ghi vào mục Loại ở bước kiểm."
            ) % "".join("<li>%s</li>" % s for s in short)
            return "warning", message + price_block, False
        if price_block:
            return "warning", price_block, False
        return "info", _(
            "Nhập số thực nhận rồi xác nhận. Số lô do hệ thống tự sinh "
            "(LO/năm/số) — sửa được nếu cần."), False

    def _dlm_receipt_unpriced_names(self):
        """SM-07: tên mặt hàng trên phiếu mà NCC này CHƯA có bảng giá đang áp dụng.

        SM-01 đã lọc domain theo `seller_ids` (link tồn tại), nhưng link tồn tại
        khác với bảng giá ĐÃ DUYỆT & ĐANG ÁP DỤNG (`is_applied` — xem
        product_supplierinfo.py). Nhận mặt hàng chưa có giá đang áp dụng ⇒ giá vốn
        tham chiếu có thể trống/sai.

        sudo: thủ kho không được xem giá NCC (§8.3 doc gốc). Ta chỉ đọc CÓ/KHÔNG
        bảng giá đang áp dụng — không đưa số tiền lên UI Kho.
        """
        self.ensure_one()
        if not self.partner_id:
            return []
        Supplierinfo = self.env["product.supplierinfo"].sudo()
        names = []
        for product in self.move_ids.product_id:
            if not Supplierinfo.search_count([
                ("partner_id", "=", self.partner_id.id),
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("is_applied", "=", True),
            ]):
                names.append(product.display_name)
        return names

    def _dlm_banner_delivery(self):
        """Dải cho phiếu [5] Giao hàng khách."""
        if self.state == "done":
            return "success", _("Đã giao hàng cho khách."), False
        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        if self.state == "draft":
            return "info", _(
                "Xác nhận phiếu để hệ thống <b>giữ chỗ</b> hàng trong kho. Chưa "
                "xác nhận thì hàng vẫn có thể bị đơn khác lấy mất."), False

        short = self.move_ids.filtered(
            lambda move: move.state in (
                "waiting", "confirmed", "partially_available"))
        if short:
            items = "".join(
                "<li>%s</li>" % move.product_id.display_name for move in short)
            # RS-11 — đọc theo `location_id` THẬT: ô "Lấy hàng từ" đổi được, mà
            # dải viết cứng "Kho thành phẩm" thì báo sai ngay khi người dùng đổi.
            # (Trước 2026-08-12 còn một nhánh "hàng đang ở Kho vật tư, chuyển
            # sang trước" — đã gỡ cùng `_dlm_stock_elsewhere`: hàng thương mại
            # nay vào thẳng Kho thành phẩm ở bước kiểm, không còn nằm sai chỗ.)
            message = _(
                "%s chưa đủ hàng để giữ chỗ:<ul>%s</ul>Xác nhận giao ngay bây "
                "giờ sẽ chỉ giao được phần đang có, phần còn lại tách sang một "
                "phiếu giao mới.") % (
                self.location_id.display_name or _("Vị trí lấy hàng"), items)
            return "warning", message, False

        return "info", _(
            "Đã giữ chỗ đủ hàng. Xác nhận giao sẽ trừ tồn kho thành phẩm."), False

    def _dlm_banner_return(self):
        """Dải cho phiếu [3] Trả hàng NCC — chủ sở hữu là Mua hàng."""
        if self.state == "done":
            return "success", _(
                "Đã trả hàng cho nhà cung cấp và trừ khỏi khu Chờ trả NCC."), False
        if self.state == "draft":
            return "info", _(
                "Phiếu này do bước <b>kiểm hàng</b> sinh ra và cố ý để "
                "<b>nháp</b>: thoả thuận với %s trước (đổi hàng, giảm trừ công "
                "nợ, hay NCC tự đến lấy), rồi mới xác nhận. Xác nhận sẽ trừ hàng "
                "khỏi khu <b>Chờ trả NCC</b>."
            ) % (self.partner_id.display_name or _("nhà cung cấp")), False
        return "info", _(
            "Đã chốt trả hàng. Xác nhận phiếu khi hàng thực sự rời kho."), False

    def _dlm_qc_problems(self):
        """Danh sách lỗi CỤ THỂ chặn xác nhận kiểm (QC-02/03/04 + thiếu lô).

        Nêu đích danh từng dòng: "thiếu lý do loại" chung chung thì thủ kho phải
        tự dò 20 dòng để tìm chỗ sai.
        """
        self.ensure_one()
        problems = []
        for move in self.move_ids:
            name = move.product_id.display_name
            if move.dlm_qty_rejected < 0:                                # QC-01
                problems.append(_("%s: số loại không được âm.") % name)
            if move.dlm_qc_over:                                         # QC-02
                problems.append(_(
                    "%s: Đạt + Loại = %s, vượt quá %s đang chờ kiểm."
                ) % (name, _dlm_fmt(move.quantity + move.dlm_qty_rejected),
                     _dlm_fmt(move.product_uom_qty)))
            if move.dlm_qty_rejected > 0 and not move.dlm_reject_reason:  # QC-03
                problems.append(_("%s: có hàng loại nhưng chưa chọn lý do.") % name)
            if (move.dlm_reject_reason == "other"
                    and not (move.dlm_reject_note or "").strip()):        # QC-04
                problems.append(_("%s: lý do \"Khác\" phải ghi rõ ở ô ghi chú.") % name)
        problems.extend(
            _("%s: chưa có số lô.") % n for n in self._dlm_lot_missing_names())
        # RS-11 — xác nhận khi MỌI dòng đều Đạt 0 và Loại 0. Không bắt ở đây thì
        # rơi xuống lỗi native tiếng Anh dạng modal ("You cannot validate a
        # transfer if no quantities are reserved nor done"), thứ phá vỡ "chuẩn
        # Đại Linh" rõ nhất. Kiểm SAU CÙNG: đây là ca "chưa làm gì", nêu trước
        # các lỗi cụ thể sẽ che mất chúng.
        if not problems and self.move_ids and not any(
                move.quantity or move.dlm_qty_rejected
                for move in self.move_ids):
            problems.append(_(
                "Chưa nhập kết quả kiểm cho dòng nào — điền số Đạt (và số Loại "
                "nếu có hàng lỗi), hoặc bấm \"Đạt tất cả\"."))
        return problems

    def _dlm_lot_missing_names(self):
        """Tên các mặt hàng theo lô mà dòng đã nhập số nhưng chưa gán lô.

        Không có lô thì chuỗi truy vết đứt ngay tại đây: khách báo nứt mối hàn
        sẽ không tra ngược ra được thép của NCC nào.
        """
        self.ensure_one()
        names = set()
        for line in self.move_line_ids:
            if (line.product_id.tracking == "lot"
                    and not float_is_zero(line.quantity, precision_digits=3)
                    and not line.lot_id and not line.lot_name):
                names.add(line.product_id.display_name)
        return sorted(names)

    # ── RS-03 — Quyết định trả hàng là của Mua hàng, không của Thủ kho ───────
    def action_confirm(self):
        self._dlm_check_return_decision(_("chốt phiếu trả hàng NCC"))
        # RS-11 — lưới chặn cuối. Đường chính vẫn là dải đỏ INLINE + nút Xác
        # nhận tự ẩn; cái này chỉ bắt đường RPC / smart button không qua form.
        for picking in self:
            problems = picking._dlm_confirm_problems()
            if problems:
                raise UserError(_("Chưa xác nhận phiếu %s được:\n%s") % (
                    picking.name, "\n".join("• %s" % p for p in problems)))
        return super().action_confirm()

    def action_cancel(self):
        self._dlm_check_return_decision(_("huỷ phiếu trả hàng NCC"))
        return super().action_cancel()

    def _dlm_check_return_decision(self, viec):
        """Chặn ở SERVER, không tin `groups` trên nút.

        Nút ẩn chỉ giấu khỏi mắt; smart button, RPC hay một action khác vẫn gọi
        thẳng được method. Bài học chính RS-03: ẩn menu "Trả hàng NCC" khỏi thủ
        kho rồi vẫn để họ chốt được phiếu qua đường khác.
        """
        returns = self.filtered(
            lambda p: p.picking_type_id.sequence_code == _DLM_RETURN_CODE)
        if not returns or self.env.su:
            return True
        if any(self.env.user.has_group(role) for role in _DLM_RETURN_DECIDERS):
            return True
        raise UserError(_(
            "Bạn không có quyền %s. Trả hàng cho nhà cung cấp là quyết định của "
            "bộ phận Mua hàng — họ còn phải thoả thuận đổi hàng hay giảm trừ "
            "công nợ. Thủ kho chỉ bấm \"Xác nhận đã trả\" khi xe NCC tới lấy "
            "hàng.") % viec)

    # ── K5 — Mỗi phiếu nhận sinh ĐÚNG MỘT phiếu kiểm ─────────────────────────
    def _dlm_group_receipt_moves(self):
        """Gắn mỗi phiếu nhận một nhóm cung ứng riêng.

        🔴 Không có bước này, `stock.move._assign_picking` gom MỌI dòng đang chờ
        ở khu Chờ kiểm vào CÙNG MỘT phiếu kiểm (nó khớp theo vị trí + loại hoạt
        động + `group_id`, không khớp theo đối tác). Hậu quả không lỗi nào nổ:
        phiếu kiểm trộn hàng của nhiều NCC, "Từ phiếu"/"Nhà cung cấp" trên form
        chỉ ra một trong số đó, và phiếu trả hàng sinh ra sẽ ghi **SAI NCC** —
        trả nhầm 8 cây thép gỉ cho nhà cung cấp không giao lô đó.

        Người gọi là `stock.move._action_confirm` — KHÔNG phải `action_confirm`
        của phiếu. Nhóm phải có mặt trước khi `_push_apply` copy sang dòng kiểm,
        mà push chỉ chạy trong `_action_confirm` của move; đóng dấu ở tầng phiếu
        thì mọi đường xác nhận khác đều lọt (xem RS-01 trong `stock_move.py`).
        """
        Group = self.env["procurement.group"]
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            moves = picking.move_ids.filtered(lambda move: not move.group_id)
            if not moves:
                continue
            moves.group_id = Group.create({
                "name": picking.name,
                "partner_id": picking.partner_id.id,
            })
        return True

    # ── K3 — Lô tự sinh & đóng dấu nguồn gốc ─────────────────────────────────
    def button_validate(self):
        # K12 — lưới chặn server cho phiếu [9]. Đặt ở `button_validate` chứ KHÔNG
        # ở `action_confirm`: phiếu vừa dựng xong đã confirm ngay để giữ chỗ,
        # lúc đó số kg và lý do đương nhiên còn trống — chặn ở đó là tự khoá
        # chính đường sinh phiếu. Điểm không đảo ngược được là lúc VALIDATE.
        for picking in self.filtered(
                lambda p: p.dlm_picking_kind == "to_scrap"):
            problems = picking._dlm_to_scrap_problems()
            if problems:
                raise UserError(_("Chưa xác nhận phiếu %s được:\n%s") % (
                    picking.name, "\n".join("• %s" % p for p in problems)))
            picking._dlm_sync_to_scrap_qty()
        # 🔴 K15 — chốt chặn cứng của luồng hai chữ ký. Đặt ở đây, KHÔNG chỉ ở
        # tầng view: đường duy nhất hợp lệ để phiếu ra xưởng hoàn tất là
        # `action_dlm_confirm_receipt` (nó ghi chữ ký rồi mới gọi xuống đây).
        # Mọi đường khác — nút native, RPC, một action tương lai — dừng ở đây.
        # KHÔNG miễn trừ cho `env.su`: chính lối ký nhận cũng chạy dưới sudo, và
        # nó đã ghi `dlm_received_uid` nên đi qua được bằng dữ liệu THẬT.
        # 🔴 K16 — lưới chặn server cho phiếu [8], cùng khuôn phiếu [9]: dải đỏ
        # trên form và lỗi khi bấm phải nói cùng một câu.
        for picking in self.filtered(
                lambda p: p.dlm_picking_kind == "fg_receipt"):
            problems = picking._dlm_fg_receipt_problems()
            if problems:
                raise UserError(_("Chưa xác nhận phiếu %s được:\n%s") % (
                    picking.name, "\n".join("• %s" % p for p in problems)))
        for picking in self.filtered(
                lambda p: p.dlm_needs_receipt and not p.dlm_received_uid):
            raise UserError(_(
                "Phiếu %s phải có chữ ký nhận hàng của %s.\n\n%s"
            ) % (picking.name, picking.dlm_receiver_label, _(
                "%s mở phiếu và bấm \"Xác nhận đã nhận\".")
                % picking.dlm_receiver_label
                if picking.dlm_handover_uid else _(
                "Người lập bấm \"Bàn giao\" trước, rồi %s mở phiếu và bấm "
                "\"Xác nhận đã nhận\".") % picking.dlm_receiver_label))
        self._dlm_autofill_lot_names()
        return super().button_validate()

    def _action_done(self):
        """K4 — Đóng dấu nguồn gốc lô ngay khi phiếu nhập hoàn tất.

        Đặt ở `_action_done` chứ không ở `button_validate` vì button_validate có
        thể trả về wizard (hỏi tạo phiếu chờ giao tiếp) và phiếu chưa xong thật.
        """
        res = super()._action_done()
        self._dlm_stamp_lot_origin()
        return res

    def _dlm_stamp_lot_origin(self):
        """Ghi NCC + ngày nhập + phiếu nguồn lên các lô vừa nhận.

        Chỉ phiếu NHẬP mới đóng dấu, và chỉ đóng dấu lô CHƯA có nguồn: lô sinh
        ra từ lần nhập đầu tiên, những lần luân chuyển sau không được ghi đè
        (nếu không, truy vết sẽ trỏ về phiếu chuyển kho nội bộ thay vì NCC).
        """
        for picking in self:
            if picking.picking_type_id.code != "incoming":
                continue
            lots = picking.move_line_ids.lot_id.filtered(
                lambda lot: not lot.dlm_receipt_picking_id)
            if lots:
                lots.sudo().write({
                    "dlm_supplier_id": picking.partner_id.id,
                    "dlm_receipt_date": picking.date_done or fields.Date.context_today(picking),
                    "dlm_receipt_picking_id": picking.id,
                })
        return True

    def _dlm_autofill_lot_names(self):
        """Điền số lô tự sinh cho dòng lô được SINH RA còn trống.

        Hai chỗ lô ra đời: hàng NCC giao (phiếu nhập), và — từ K13 — hàng chính
        xưởng làm xong (phiếu [8] Nhập thành phẩm, bán thành phẩm theo lô). Cả
        hai đều là "lô mới vào sổ" nên số do Đại Linh tự sinh, đúng chốt K3.
        Phiếu xuất / chuyển kho thì tiêu thụ lô đã có — tự sinh ở đó sẽ đẻ lô ma
        không có nguồn.

        🔴 Không nới cho [8] thì BTP theo lô rơi vào ngõ cụt: Odoo bắt buộc số
        lô lúc validate, mà màn này không có đường nào tra ra lô "đang có" (hàng
        chưa từng tồn tại trước phiếu này) — người dùng bị chặn và không có gì
        để điền.

        Chỉ điền khi người dùng để trống: thủ kho vẫn có thể gõ đè số riêng.
        """
        sequence = self.env["ir.sequence"].sudo()
        for line in self.move_line_ids:
            picking_type = line.picking_id.picking_type_id
            sinh_lo_moi = (
                picking_type.code == "incoming"
                or picking_type.sequence_code == _DLM_FG_RECEIPT_CODE)
            if (sinh_lo_moi and line.product_id.tracking == "lot"
                    and not line.lot_id and not line.lot_name):
                line.lot_name = sequence.next_by_code("stock.lot.serial")
        return True

    # ── K5 — Hành động trên màn Kiểm & cất hàng ──────────────────────────────
    def action_dlm_pass_all(self):
        """Nút phụ "Đạt tất cả": điền Đạt = số NCC giao cho mọi dòng.

        Ca phổ biến nhất (hàng về đủ và tốt) — tiết kiệm hàng chục lần gõ.
        """
        self.ensure_one()
        for move in self.move_ids:
            move.write({
                "quantity": move.product_uom_qty,
                "dlm_qty_rejected": 0.0,
                "dlm_reject_reason": False,
                "dlm_reject_note": False,
                "picked": True,
            })
        return True

    def action_dlm_validate_qc(self):
        """Xác nhận kiểm: hàng đạt vào kho, hàng loại sang khu Chờ trả NCC.

        Trình tự (§6.4). Điểm tinh nhưng quan trọng là bước 2: phải THU HẸP nhu
        cầu dòng gốc về đúng số đạt trước khi tách dòng loại. Không làm vậy thì
        tổng nhu cầu (100) vượt tổng thực hiện (92) và Odoo đẻ ra một phiếu kiểm
        chờ tiếp 8 đơn vị — trong khi 8 đơn vị đó đã sang khu trả hàng rồi.
        """
        self.ensure_one()
        problems = self._dlm_qc_problems()
        if problems:
            # UI đã chặn nút; đây là lưới an toàn cho gọi qua RPC/test.
            raise UserError(_("Chưa xác nhận kiểm được:\n- %s")
                            % "\n- ".join(problems))

        rejected_moves = self.move_ids.filtered(
            lambda m: m.dlm_qty_rejected > 0)
        if rejected_moves:
            self._dlm_split_rejected_moves(rejected_moves)
        self._dlm_route_accepted_trading_moves()

        # skip_backorder: KHÔNG mở modal hỏi phiếu chờ tiếp (quy ước dự án).
        # Cố ý KHÔNG kèm picking_ids_not_to_backorder — phần CHƯA KIỂM (nếu thủ
        # kho kiểm dở) vẫn phải tách sang phiếu kiểm mới, không được biến mất.
        result = self.with_context(skip_backorder=True).button_validate()

        if rejected_moves:
            self._dlm_create_vendor_return(rejected_moves)
        self._dlm_post_qc_summary()
        return result

    def _dlm_split_rejected_moves(self, rejected_moves):
        """Tách phần hàng loại của mỗi dòng sang một dòng đích Chờ trả NCC."""
        self.ensure_one()
        reject_location = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_nhan_tra")
        Move = self.env["stock.move"]
        new_moves = Move.browse()
        reject_moves = Move.browse()

        for move in rejected_moves:
            rounding = move.product_uom.rounding or 0.01
            con_lai = move.product_uom_qty - move.dlm_qty_rejected
            if float_is_zero(con_lai, precision_rounding=rounding):
                # Loại SẠCH cả dòng: đổi thẳng đích của dòng gốc. Tách ra dòng
                # mới thì dòng gốc còn nhu cầu 0 — Odoo huỷ nó và mất luôn kết
                # quả kiểm đã ghi trên dòng.
                # sudo: xem lý do ở nhánh dưới.
                move.sudo().write({
                    "location_dest_id": reject_location.id,
                    "product_uom_qty": move.dlm_qty_rejected,
                })
                move.move_line_ids.location_dest_id = reject_location
                reject_moves |= move
                continue
            new_moves |= Move.create({
                "name": move.name,
                "picking_id": self.id,
                "picking_type_id": move.picking_type_id.id,
                "product_id": move.product_id.id,
                "product_uom": move.product_uom.id,
                "product_uom_qty": move.dlm_qty_rejected,
                "location_id": move.location_id.id,
                "location_dest_id": reject_location.id,
                "company_id": move.company_id.id,
                # Kết quả kiểm ở lại dòng GỐC (một dòng = một lần kiểm). Dòng
                # tách chỉ chở hàng đi, mang theo lý do để phiếu trả đọc được.
                "dlm_reject_reason": move.dlm_reject_reason,
                "dlm_reject_note": move.dlm_reject_note,
            })
            # Nhu cầu dòng gốc BỚT ĐI đúng phần loại — KHÔNG đặt bằng số đạt.
            # Đặt bằng số đạt thì phần CHƯA KIỂM (giao 100, kiểm 90 đạt + 8 loại
            # ⇒ còn 2) biến mất khỏi nhu cầu: hàng thật nằm lại khu Chờ kiểm mà
            # không phiếu nào nhắc tới nữa.
            #
            # sudo: stock.move.write ghi log chatter mỗi lần đổi nhu cầu, mà
            # message_post nổ UserError nếu người dùng chưa khai email. Đây là
            # bút toán nội bộ của hệ thống, không phải người dùng sửa tay —
            # không được để hồ sơ thiếu email chặn cả việc nhập kho.
            move.sudo().product_uom_qty = move.product_uom_qty - move.dlm_qty_rejected

        if new_moves:
            new_moves._action_confirm()
        reject_moves |= new_moves
        if not reject_moves:
            return
        reject_moves._action_assign()
        for move in reject_moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        self._dlm_force_lot_on(reject_moves)

    def _dlm_route_accepted_trading_moves(self):
        """Đạt + hàng thương mại → Kho thành phẩm THẲNG (§5.1, §5.3).

        Hàng thương mại mua về là để bán lại, không qua sản xuất — kiểm đạt xong
        là sẵn sàng giao. Đưa thẳng vào Kho thành phẩm (nơi phiếu Giao hàng lấy
        hàng) ngay trong bước kiểm, thay vì cất vào Kho nguyên vật liệu rồi bắt
        làm thêm một phiếu chuyển kho mà người ta hay quên. Vật tư vẫn về Kho
        nguyên vật liệu.

        Không phải cơ chế mới: đây là ngả thứ ba của cùng cái máy đã đặt
        `location_dest_id` khác nhau cho từng dòng ở `_dlm_split_rejected_moves`
        (ngả Loại → Chờ trả NCC). Chạy SAU nó nên dòng nào còn trỏ về Kho nguyên
        vật liệu chính là phần ĐẠT — chỉ đổi đúng những dòng đó, và chỉ khi là
        hàng TM.
        """
        self.ensure_one()
        Location = self.env["stock.location"]
        kho = Location._dlm_location("dl_inventory.stock_location_nhan_kho")
        tp = Location._dlm_location("dl_inventory.stock_location_tp")
        moves = self.move_ids.filtered(
            lambda m: m.product_id.product_kind == "trading"
            and m.location_dest_id == kho
            and m.state not in ("done", "cancel"))
        if not moves:
            return
        # sudo: cùng lý do như _dlm_split_rejected_moves — stock.move.write ghi
        # log chatter, message_post nổ UserError nếu hồ sơ người dùng thiếu email.
        moves.sudo().write({"location_dest_id": tp.id})
        moves.move_line_ids.location_dest_id = tp

    def _dlm_force_lot_on(self, moves):
        """Gán lô cho dòng hàng loại nếu bước giữ chỗ không tự gán được.

        Hàng loại vẫn thuộc lô đã nhận — mất lô ở đây là mất luôn bằng chứng
        "lô LO/2026/00002 của NCC X có 8 cây gỉ", đúng thứ khiến khiếu nại NCC
        thành lời nói suông. Xác nhận phiếu cũng sẽ nổ ("cần cung cấp số lô")
        nhưng lỗi đó không nói được phải điền lô nào.

        Hai nguồn suy ra lô, theo thứ tự tin cậy: dòng khác của chính phiếu này,
        rồi tồn đang nằm ở khu Chờ kiểm.
        """
        Quant = self.env["stock.quant"]
        for move in moves:
            if move.product_id.tracking != "lot":
                continue
            lines = move.move_line_ids.filtered(lambda line: not line.lot_id)
            if not lines:
                continue
            lot = move.picking_id.move_line_ids.filtered(
                lambda line: line.product_id == move.product_id and line.lot_id
            )[:1].lot_id
            if not lot:
                lot = Quant.search([
                    ("location_id", "=", move.location_id.id),
                    ("product_id", "=", move.product_id.id),
                    ("lot_id", "!=", False),
                ], order="quantity desc", limit=1).lot_id
            if lot:
                lines.lot_id = lot

    def _dlm_create_vendor_return(self, rejected_moves):
        """Phiếu [3] Trả hàng NCC — để NHÁP, giao việc cho Mua hàng.

        Vì sao không tự xác nhận: trả hàng là việc ĐỐI NGOẠI, phải thoả thuận
        với NCC trước (đổi hàng? giảm trừ công nợ? NCC tự đến lấy?). Thủ kho ghi
        nhận, Mua hàng quyết định — đúng ranh giới kiểm soát chéo đã có.
        """
        self.ensure_one()
        return_type = self.env.ref(
            "dl_inventory.picking_type_vendor_return", raise_if_not_found=False)
        if not return_type:
            return self.env["stock.picking"]
        reject_location = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_nhan_tra")
        receipt = self._dlm_source_receipt()
        partner = receipt.partner_id or self.partner_id

        # sudo: RS-03 chặn Thủ kho TẠO phiếu trả NCC (quyết định đối ngoại là
        # của Mua hàng). Phiếu này không phải thủ kho tạo — nó là HỆ QUẢ máy móc
        # của kết quả kiểm: có hàng loại thì phải có chỗ ghi nợ NCC. Không sudo
        # thì lá chắn RS-03 chặn luôn chính bước kiểm hàng.
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": return_type.id,
            "partner_id": partner.id,
            "location_id": reject_location.id,
            "location_dest_id": return_type.default_location_dest_id.id,
            "origin": receipt.name or self.name,
            # RS-08 — trỏ về phiếu NHẬN gốc, KHÔNG rơi về `self` (chính phiếu
            # kiểm): field mang tên "Phiếu nhận gốc", để trống còn đúng hơn là
            # chỉ vào một phiếu kiểm không có trên chứng từ nào của NCC.
            "dlm_origin_picking_id": receipt.id,
            "move_ids": [(0, 0, {
                "name": move.product_id.display_name,
                "product_id": move.product_id.id,
                "product_uom": move.product_uom.id,
                "product_uom_qty": move.dlm_qty_rejected,
                "location_id": reject_location.id,
                "location_dest_id": return_type.default_location_dest_id.id,
                "dlm_reject_reason": move.dlm_reject_reason,
                "dlm_reject_note": move.dlm_reject_note,
            }) for move in rejected_moves],
        })
        # sudo: ghi chatter là DẤU VẾT, không phải nghiệp vụ. Người dùng chưa
        # khai email làm message_post nổ UserError (mail_thread._message_compute
        # _author) — để nguyên thì cả phiếu kiểm rollback chỉ vì thiếu email
        # trong hồ sơ thủ kho. sudo() đặt env.su ⇒ Odoo bỏ qua kiểm tra đó.
        picking.sudo().message_post(body=_(
            "Sinh tự động từ kết quả kiểm phiếu %s. Phiếu để <b>nháp</b>: Mua "
            "hàng thoả thuận với NCC rồi mới xác nhận trả."
        ) % self.name)
        self._dlm_notify_purchasing(picking)
        return picking

    def _dlm_notify_purchasing(self, return_picking):
        """Giao việc cho nhóm Mua hàng — phiếu trả nháp không ai biết là nằm im."""
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        if not group:
            return
        summary = _("Xử lý trả hàng NCC — %s") % return_picking.name
        for user in group.users:
            return_picking.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=_("Kiểm hàng phiếu %s phát hiện hàng không đạt. Thoả "
                       "thuận với %s rồi xác nhận (hoặc huỷ) phiếu trả này.")
                % (self.name, return_picking.partner_id.display_name),
                user_id=user.id)

    def _dlm_post_qc_summary(self):
        """Ghi kết quả kiểm theo từng dòng lên chatter — dấu vết cho khiếu nại."""
        self.ensure_one()
        reasons = dict(
            self.env["stock.move"]._fields["dlm_reject_reason"].selection)
        rows = []
        for move in self.move_ids:
            if move.dlm_qty_rejected <= 0:
                continue
            rows.append(_("<li>%s — loại <b>%s</b> %s (%s)%s</li>") % (
                move.product_id.display_name,
                _dlm_fmt(move.dlm_qty_rejected),
                move.product_uom.name,
                reasons.get(move.dlm_reject_reason, _("chưa rõ")),
                _(": %s") % move.dlm_reject_note if move.dlm_reject_note else ""))
        # sudo: xem lý do ở _dlm_create_vendor_return.
        if rows:
            self.sudo().message_post(
                body=_("Kết quả kiểm:<ul>%s</ul>") % "".join(rows))
        else:
            self.sudo().message_post(body=_("Kiểm đạt toàn bộ, đã cất vào kho."))

    # ── K5 — Điều hướng giữa các chặng chứng từ ──────────────────────────────
    def _dlm_source_receipt(self):
        """Phiếu nhận [1] đứng trước phiếu này (rỗng nếu tạo tay).

        Hai đường truy ngược, vì hai loại phiếu nối vào phiếu nhận theo hai cách
        khác nhau: phiếu KIỂM nối bằng chuỗi move (tuyến 2 bước tự sinh), còn
        phiếu TRẢ nối bằng `dlm_origin_picking_id` (dòng của nó được tạo mới nên
        không có `move_orig_ids`).
        """
        self.ensure_one()
        origins = self.move_ids.move_orig_ids.picking_id.filtered(
            lambda p: p.picking_type_id.code == "incoming")
        if origins:
            return origins[:1]
        if self.dlm_origin_picking_id.picking_type_id.code == "incoming":
            return self.dlm_origin_picking_id
        return self.browse()

    def action_dlm_open_source_receipt(self):
        """Phiếu kiểm → phiếu nhận gốc."""
        self.ensure_one()
        receipt = self._dlm_source_receipt()
        if not receipt:
            raise UserError(_("Phiếu kiểm này không đi từ phiếu nhận nào."))
        return self._dlm_open_picking(receipt, _("Phiếu nhận %s") % receipt.name)

    def action_dlm_open_qc_picking(self):
        """Phiếu nhận → phiếu kiểm sinh ra từ nó."""
        self.ensure_one()
        qc = self.move_ids.move_dest_ids.picking_id.filtered(
            lambda p: p.picking_type_id.sequence_code == _DLM_QC_CODE)[:1]
        if not qc:
            raise UserError(_(
                "Chưa có phiếu kiểm. Phiếu kiểm chỉ sinh ra sau khi xác nhận "
                "nhận hàng."))
        return self._dlm_open_picking(qc, _("Phiếu kiểm %s") % qc.name)

    def _dlm_vendor_returns(self):
        """Phiếu trả NCC của cả chặng nhận hàng này.

        Neo vào phiếu NHẬN (Mua hàng cần biết trả hàng thuộc lần giao nào để đối
        chiếu hoá đơn NCC), nhưng tra được từ cả phiếu nhận lẫn phiếu kiểm —
        người bấm ra phiếu trả đang đứng ở phiếu kiểm.
        """
        self.ensure_one()
        anchor = self._dlm_source_receipt() | self
        return self.search([("dlm_origin_picking_id", "in", anchor.ids)])

    def action_dlm_open_returns(self):
        """Phiếu nhận / phiếu kiểm → các phiếu trả NCC của chặng này."""
        self.ensure_one()
        returns = self._dlm_vendor_returns()
        if not returns:
            raise UserError(_("Chặng nhận hàng này chưa có phiếu trả NCC nào."))
        name = (_("Phiếu trả NCC %s") % returns.name if len(returns) == 1
                else _("Phiếu trả NCC của %s") % self.name)
        return returns._dlm_open_pickings(name)

    def action_dlm_open_sale_order(self):
        """Phiếu giao → đơn bán hàng nguồn."""
        self.ensure_one()
        if not self.dlm_sale_order_id:
            raise UserError(_("Phiếu giao này không gắn với đơn bán hàng nào."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "dl.sale.order",
            "res_id": self.dlm_sale_order_id.id,
            "view_mode": "form",
            "name": _("Đơn %s") % self.dlm_sale_order_id.name,
        }

    # ── K6 — Preset chuyển kho ───────────────────────────────────────────────
    # Là NÚT chứ không phải field lựa chọn: field sẽ nói dối ngay khi người dùng
    # sửa tay vị trí, còn nút chỉ điền một lần rồi thôi — hai ô vị trí vẫn là
    # nguồn sự thật.
    #
    # 🔴 K16 — preset "Gom phế liệu" (Xưởng → Phế liệu chờ bán) ĐÃ GỠ. Phế liệu
    # nay khai ngay trên phiếu [8] cùng mẻ sinh ra nó, nên giữ thêm một đường
    # thứ hai là mở chỗ cho hai con số cùng nói về một đống vụn. Ca "quét sàn
    # cuối tháng, không thuộc mẻ nào" dùng màn Kiểm kê — đúng ngữ nghĩa "phát
    # hiện hàng chưa có trong sổ", và đã có sẵn từ K8.
    def action_dlm_preset_to_workshop(self):
        """Vật tư ra xưởng: Kho nguyên vật liệu → Xưởng sản xuất."""
        return self._dlm_set_transfer_route(
            "dl_inventory.stock_location_nhan_kho",
            "dl_inventory.stock_location_xuong")

    # ── K15 — Bàn giao ra xưởng: hai chữ ký, hai người ───────────────────────
    def action_dlm_handover(self):
        """Bước 1 — Thủ kho bàn giao. Đóng dấu người giao, hàng CHƯA rời sổ."""
        self.ensure_one()
        if not self.dlm_needs_receipt:
            raise UserError(_(
                "Phiếu này không cần bàn giao hai bước — bấm nút xác nhận."))
        if self.dlm_handover_uid:
            raise UserError(_(
                "%s đã bàn giao phiếu này rồi. Đang chờ %s ký nhận."
            ) % (self.dlm_handover_uid.name, self.dlm_receiver_label))
        if self.state not in ("waiting", "confirmed", "assigned"):
            raise UserError(_(
                "Phải xác nhận phiếu (để giữ chỗ hàng) trước khi bàn giao."))
        # Cùng bộ lỗi với dải đỏ trên form: bàn giao là điểm không quay lại
        # được về mặt trách nhiệm, không được dễ dãi hơn nút xác nhận.
        problems = self._dlm_confirm_problems()
        if problems:
            raise UserError(_("Chưa bàn giao được:\n%s") % "\n".join(
                "• %s" % p for p in problems))
        self.write({
            "dlm_handover_uid": self.env.user.id,
            "dlm_handover_date": fields.Datetime.now(),
        })
        # sudo: message_post nổ UserError khi hồ sơ người dùng thiếu email
        # (mail_thread._message_compute_author) — đã vấp thật ở K5. Vết chữ ký
        # phải ghi được kể cả khi hồ sơ nhân sự chưa khai đủ.
        self.sudo().message_post(body=_(
            "Đã bàn giao. Chờ %s ký nhận.") % self.dlm_receiver_label)
        return True

    def action_dlm_confirm_receipt(self):
        """Bước 2 — Bên Xưởng ký nhận ⇒ phiếu hoàn tất, hàng rời sổ kho."""
        self.ensure_one()
        if not self.dlm_needs_receipt:
            raise UserError(_("Phiếu này không cần chữ ký nhận hàng."))
        if not self.dlm_handover_uid:
            raise UserError(_(
                "Thủ kho chưa bàn giao phiếu này — chưa có gì để ký nhận."))
        if self.dlm_received_uid:
            raise UserError(_("%s đã ký nhận phiếu này rồi.")
                            % self.dlm_received_uid.name)
        # Thứ tự QUAN TRỌNG: kiểm vai trò TRƯỚC. Người sai vai phải nghe câu
        # "chữ ký này là của bên nhận", không phải câu "bạn vừa bàn giao" — hai
        # câu dẫn tới hai hành động sửa sai khác nhau.
        self._dlm_check_receipt_signer()
        # 🔴 K16 — Admin và CEO nằm trong CẢ HAI bộ ký (lối thoát khi người phụ
        # trách nghỉ). Không có dòng này thì đúng những vai đó bàn giao rồi tự ký
        # nhận được, và phiếu mang hai chữ ký của cùng một người — tệ hơn không
        # có chữ ký nào, vì nó trông như đã đối chiếu.
        if not self.env.su and self.dlm_handover_uid == self.env.user:
            raise UserError(_(
                "Bạn vừa là người bàn giao phiếu này. Người giao không ký nhận "
                "thay bên nhận được — nhờ %s mở phiếu và ký."
            ) % self.dlm_receiver_label)
        # sudo vì bên Kỹ thuật chỉ có quyền ĐỌC phiếu kho (ir.model.access.csv
        # `1,0,0,0`) — khuôn "kiểm vai trò tường minh rồi nâng quyền" đã dùng ở
        # K6/K8. Nới ACL ghi cho cả nhóm Kỹ thuật thì họ sửa được mọi phiếu kho,
        # đắt hơn nhiều so với việc mở đúng một hành động này.
        #
        # sudo() chứ không with_user(SUPERUSER_ID) như K8: ở đây không có cổng
        # `user_has_groups` nào của native phải vượt, chỉ có ACL — mà `su` là đủ.
        picking = self.sudo()
        # Ghi chữ ký TRƯỚC khi validate: guard ở `button_validate` đọc chính
        # field này. Nếu validate nổ giữa chừng thì transaction cuốn lại cả hai
        # ⇒ không có ca "đã ký mà phiếu vẫn treo".
        picking.write({
            "dlm_received_uid": self.env.user.id,
            "dlm_received_date": fields.Datetime.now(),
        })
        picking.move_ids.picked = True
        picking.message_post(body=_(
            "%s (%s) đã ký nhận hàng."
        ) % (self.env.user.name, self.dlm_receiver_label))
        return picking.button_validate()

    def _dlm_check_receipt_signer(self):
        """Chặn ở SERVER, không tin `groups` trên nút (bài học RS-03).

        Nút ẩn chỉ giấu khỏi mắt; RPC hay một action khác vẫn gọi thẳng được.

        🔴 K16 — bộ ký phụ thuộc CHIỀU bàn giao. Dùng một bộ chung cho cả hai
        chiều là mở đúng cái lỗ mà chữ ký sinh ra để bịt: bên Kỹ thuật vừa lập
        phiếu [8] sẽ tự ký nhận được chính nó.
        """
        self.ensure_one()
        if self.env.su:
            return True
        flow = self.dlm_receipt_flow
        signers, receiver = _DLM_RECEIPT_FLOWS.get(flow, ((), ""))
        if signers and any(
                self.env.user.has_group(role) for role in signers):
            return True
        raise UserError(_(
            "Bạn không ký nhận phiếu này được. Chữ ký phải là của bên NHẬN "
            "(%s): người lập phiếu ký cả hai đầu thì lần truy cứu sau không "
            "phân biệt nổi ai giao với ai nhận — đúng thứ chữ ký này sinh ra "
            "để trả lời.") % (receiver or _("bên nhận")))

    # ── K12 — Hoá phế liệu: lối ra cho hàng lỗi không trả nữa (§6.4.1, §11.14) ─
    def _dlm_stuck_quants(self):
        """Tồn còn kẹt ở khu nguồn của phiếu trả này — nguồn để hoá phế liệu.

        Đọc QUANT chứ không đọc số trên dòng phiếu, vì hàng ở khu Chờ trả không
        mang dấu "của phiếu nào". Hệ quả CÓ CHỦ Ý: hoá phế liệu xong thì quant
        biến mất ⇒ nút tự tắt, và phiếu trả thứ hai cùng mặt hàng cũng không
        hoá lại được lô đã hoá. Đọc số trên dòng thì cả hai đều làm được — và
        cái thứ hai đẩy tồn xuống âm.
        """
        self.ensure_one()
        if not self.location_id:
            return self.env["stock.quant"]
        return self.env["stock.quant"].sudo().search([
            ("location_id", "child_of", self.location_id.id),
            ("product_id", "in", self.move_ids.product_id.ids),
            ("quantity", ">", 0),
        ])

    def action_dlm_to_scrap(self):
        """Phiếu trả đã huỷ ⇒ dựng phiếu [9] cho hàng còn kẹt ở khu Chờ trả.

        Kết cục THƯỜNG GẶP NHẤT của một phiếu trả, không phải ngoại lệ: NCC giảm
        trừ công nợ, mình giữ luôn 8 cây thép gỉ. Trước bản này đó là ngõ cụt
        tuyệt đối — khu Chờ trả cấm kiểm kê tay VÀ cấm làm nguồn phiếu chuyển
        kho, nên không chứng từ nào rút hàng ra được.
        """
        self.ensure_one()
        quants = self._dlm_stuck_quants()
        if not quants:
            raise UserError(_(
                "Không còn hàng nào của phiếu %s nằm ở %s — có thể đã hoá phế "
                "liệu hoặc đã trả cho nhà cung cấp rồi.")
                % (self.name, self.location_id.display_name))
        picking = self._dlm_build_to_scrap(quants, origin_picking=self)
        return picking._dlm_open_picking(
            picking, _("Hoá phế liệu %s") % picking.name)

    @api.model
    def _dlm_build_to_scrap(self, quants, origin_picking=None):
        """Dựng phiếu [9] HAI DÒNG: hàng gốc rời sổ, phế liệu vào khu chờ bán.

        🔴 Hai nửa phải nằm trong MỘT chứng từ. Tách thành hai thao tác (xuất bỏ
        rồi cân nhập) đúng là kiểu "bước rời" mà §5.3 vừa gỡ khỏi luồng thương
        mại — bước rời là bước sẽ bị quên, và quên nửa sau nghĩa là hàng biến
        mất khỏi sổ mà không thành gì cả.
        """
        quants = quants.filtered(lambda q: q.quantity > 0)
        if not quants:
            raise UserError(_("Không có dòng tồn nào để hoá phế liệu."))
        da_la_phe = quants.product_id.filtered("dlm_is_scrap")
        if da_la_phe:
            raise UserError(_(
                "%s vốn đã là mặt hàng phế liệu — không hoá phế liệu lần nữa. "
                "Muốn dời nó về khu chờ bán thì dùng phiếu Chuyển kho."
            ) % ", ".join(da_la_phe.mapped("display_name")))

        scrap_product = self.env["product.product"].search(
            [("dlm_is_scrap", "=", True)], order="id", limit=1)
        if not scrap_product:
            raise UserError(_(
                "Chưa khai mặt hàng phế liệu nào. Bật ô <b>Là mặt hàng phế "
                "liệu</b> trên sản phẩm phế liệu (ví dụ SCRAP-STEEL) rồi làm "
                "lại — không có nó thì hàng hoá ra không biết đổ vào đâu."))

        picking_type = self.env.ref(
            "dl_inventory.picking_type_to_scrap", raise_if_not_found=False)
        if not picking_type:
            raise UserError(_(
                "Chưa cấu hình loại hoạt động Chuyển thành phế liệu. "
                "Chạy lại: -u dl_inventory"))
        Location = self.env["stock.location"]
        adj = picking_type.default_location_src_id
        pl = Location._dlm_location("dl_inventory.stock_location_xuong_pl")
        source = quants[0].location_id

        # Số kg GỢI Ý, không phải số chốt: cân thật luôn thắng. Chênh lệch giữa
        # hai số chính là dữ liệu của màn đối chiếu thu hồi (§7.4).
        goi_y = sum(q.quantity * q.product_id.dlm_mass_per_unit for q in quants)

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": pl.id,
            "origin": origin_picking.name if origin_picking else False,
            "dlm_origin_picking_id": (
                origin_picking.id if origin_picking else False),
            "move_ids": [(0, 0, {
                "name": q.product_id.display_name,
                "product_id": q.product_id.id,
                "product_uom": q.product_id.uom_id.id,
                "product_uom_qty": q.quantity,
                "location_id": q.location_id.id,
                "location_dest_id": adj.id,
            }) for q in quants] + [(0, 0, {
                "name": scrap_product.display_name,
                "product_id": scrap_product.id,
                "product_uom": scrap_product.uom_id.id,
                "product_uom_qty": goi_y,
                "location_id": adj.id,
                "location_dest_id": pl.id,
            })],
        })
        picking.action_confirm()
        # Giữ chỗ ĐÚNG LÔ đang bỏ, không để chiến lược lấy hàng chọn hộ: tạo
        # move line kèm lot_id thì `stock.move.line.create` gọi thẳng
        # `_update_reserved_quantity` cho đúng quant đó.
        for move, quant in zip(picking.move_ids[:len(quants)], quants):
            move.move_line_ids.unlink()
            self.env["stock.move.line"].create({
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": quant.product_id.id,
                "product_uom_id": quant.product_id.uom_id.id,
                "quantity": quant.quantity,
                "lot_id": quant.lot_id.id or False,
                "location_id": quant.location_id.id,
                "location_dest_id": adj.id,
            })
        return picking

    def _dlm_sync_to_scrap_qty(self):
        """Khoá NHU CẦU về đúng SỐ CÂN ĐƯỢC, và đánh dấu đã làm xong.

        🔴 Không có bước này thì Odoo thấy "đòi 48 kg, làm được 47" và bật wizard
        hỏi tạo phiếu chờ giao tiếp — vô nghĩa ở đây: 48 chỉ là số GỢI Ý theo quy
        đổi, không phải một cam kết với ai. Cân thật là con số duy nhất đúng
        (§7.3), nên nó ghi đè luôn nhu cầu.
        """
        self.ensure_one()
        for move in self.move_ids:
            if move.product_id.dlm_is_scrap:
                move.product_uom_qty = move.quantity
            move.picked = True
        return True

    def _dlm_to_scrap_problems(self):
        """Lỗi CHẶN riêng của phiếu [9] — báo INLINE, không modal."""
        self.ensure_one()
        problems = []
        vao = self.move_ids.filtered(lambda m: m.product_id.dlm_is_scrap)
        if not vao:
            problems.append(_(
                "Phiếu thiếu dòng phế liệu thu về — mỗi phiếu hoá phế liệu phải "
                "có đủ hai nửa: hàng gốc rời sổ VÀ phế liệu vào khu chờ bán."))
        # Đọc `quantity` (số THỰC làm được) chứ không đọc `product_uom_qty` (nhu
        # cầu): ô người dùng gõ trên form là số cân được, và nó mới là thứ đi vào
        # kho. Kiểm nhu cầu là kiểm con số gợi ý — luôn > 0, chặn chẳng bao giờ nổ.
        elif float_compare(sum(vao.mapped("quantity")), 0.0,
                           precision_rounding=0.001) <= 0:
            problems.append(_(
                "Chưa nhập số <b>cân được</b>. Cân lô hàng rồi gõ số kg thực "
                "tế — số gợi ý theo quy đổi chỉ là ước lượng."))
        if not (self.dlm_scrap_reason or "").strip():
            problems.append(_(
                "Chưa ghi <b>lý do</b>. Đây là bút toán làm hàng biến mất khỏi "
                "sổ — không có lý do thì sau này không ai giải thích được."))
        return problems

    def _dlm_banner_to_scrap(self):
        """Dải cho phiếu [9] Chuyển thành phế liệu."""
        if self.state == "done":
            return "success", _(
                "Đã đổi hình thái: hàng gốc rời sổ, phế liệu vào khu chờ bán. "
                "Bán được thì làm phiếu <b>Bán phế liệu</b>."), False
        problems = self._dlm_to_scrap_problems() + self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        return "warning", _(
            "Phiếu này <b>đổi mặt hàng</b>, không phải chuyển kho: hàng gốc "
            "rời sổ hẳn, đổi lấy số kg phế liệu bạn cân được. <b>Không đảo "
            "ngược được</b> sau khi xác nhận — kiểm lại số kg và lý do."), False

    # ── K16 — Đối chiếu "BOM tính bao nhiêu / đã cấp bao nhiêu" ──────────────
    def _dlm_bom_required_qty(self):
        """{vật tư: số theo định mức} của đơn gắn với phiếu này.

        sudo: Thủ kho không có quyền đọc `dl.bom` (định mức là tài sản của Kỹ
        thuật) nhưng vẫn phải thấy con số để biết mình đang cấp vượt. Chỉ đọc số
        lượng — không field tiền nào bị chạm.
        """
        self.ensure_one()
        required = {}
        order = self.dlm_sale_order_id.sudo()
        if not order:
            return required
        for line in order.line_ids:
            bom = line.bom_id
            if not bom or not bom.product_qty:
                continue
            for bom_line in bom.line_ids:
                material = bom_line.material_id
                if not material:
                    continue
                required[material] = required.get(material, 0.0) + (
                    bom_line.effective_qty / bom.product_qty * line.qty)
        return required

    def _dlm_issued_qty(self):
        """{vật tư: số ĐÃ cấp ra xưởng cho đơn này} — trừ phần chính phiếu này.

        Đếm move `done` đi vào Xưởng của mọi phiếu gắn cùng đơn. Phiếu đang mở
        không tính vào "đã cấp" vì nó chính là thứ đang được cân nhắc.
        """
        self.ensure_one()
        issued = {}
        order = self.dlm_sale_order_id
        xuong = self.env.ref(
            "dl_inventory.stock_location_xuong", raise_if_not_found=False)
        if not order or not xuong:
            return issued
        moves = self.env["stock.move"].sudo().search([
            ("state", "=", "done"),
            ("location_dest_id", "=", xuong.id),
            ("picking_id.dlm_sale_order_id", "=", order.id),
            ("picking_id", "!=", self.id),
        ])
        for move in moves:
            issued[move.product_id] = (
                issued.get(move.product_id, 0.0) + move.quantity)
        return issued

    def _dlm_build_bom_hint(self):
        """Bảng HTML "định mức / đã cấp / phiếu này" cho phiếu cấp vật tư.

        Đây là mối nối duy nhất giữa phân hệ Kho và định mức của Kỹ thuật. Không
        có nó thì "cấp bổ sung" chỉ là một ô tick không ai đối chiếu được với gì.
        """
        self.ensure_one()
        if self.dlm_picking_kind != "transfer" or not self.dlm_sale_order_id:
            return False
        required = self._dlm_bom_required_qty()
        if not required:
            return False
        issued = self._dlm_issued_qty()
        this = {}
        for move in self.move_ids.filtered(lambda m: m.state != "cancel"):
            this[move.product_id] = (
                this.get(move.product_id, 0.0) + move.product_uom_qty)
        rows = []
        for product in dict.fromkeys(list(required) + list(this)):
            dinh_muc = required.get(product, 0.0)
            da_cap = issued.get(product, 0.0)
            phieu_nay = this.get(product, 0.0)
            tong = da_cap + phieu_nay
            rounding = product.uom_id.rounding or 0.01
            vuot = float_compare(
                tong, dinh_muc, precision_rounding=rounding) > 0
            # Không chỉ tô màu: dòng vượt phải NÓI ra bằng chữ. Người đọc bảng
            # in ra giấy hoặc mù màu vẫn phải phân biệt được.
            danh_gia = _("vượt %s") % _dlm_fmt(tong - dinh_muc) if vuot else ""
            rows.append(
                "<tr class='%s'><td>%s</td><td class='text-end'>%s</td>"
                "<td class='text-end'>%s</td><td class='text-end'>%s</td>"
                "<td class='text-end'>%s</td><td>%s</td></tr>" % (
                    "table-warning" if vuot else "",
                    product.display_name, _dlm_fmt(dinh_muc),
                    _dlm_fmt(da_cap), _dlm_fmt(phieu_nay), _dlm_fmt(tong),
                    danh_gia))
        return (
            "<table class='table table-sm mb-0'><thead><tr>"
            "<th>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th><th>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>" % (
                _("Vật tư"), _("Định mức BOM"), _("Đã cấp"),
                _("Phiếu này"), _("Cộng dồn"), _("Đánh giá"),
                "".join(rows)))

    # ── K16 — Lưới chặn riêng của phiếu [8] Nhập kho từ xưởng ────────────────
    def _dlm_fg_receipt_problems(self):
        """Lỗi chặn của phiếu mẻ. Một nguồn cho cả dải đỏ lẫn guard server."""
        self.ensure_one()
        problems = []
        moves = self._dlm_moves().filtered(lambda m: m.state != "cancel")
        if not moves:
            problems.append(_(
                "Phiếu chưa có dòng nào. Khai ít nhất một thứ xưởng nộp về "
                "hoặc một dòng vật tư."))
        thieu_vai_tro = moves.filtered(lambda m: not m.dlm_move_kind)
        if thieu_vai_tro:
            problems.append(_(
                "Chưa khai vai trò cho dòng: %s. Mỗi dòng phải nói rõ là hàng "
                "xưởng nộp về hay vật tư ra khỏi xưởng — vị trí lấy/nhận suy "
                "từ đó."
            ) % ", ".join(dict.fromkeys(
                thieu_vai_tro.mapped("product_id.display_name"))))

        # 🔴 Vật tư rời xưởng KHÔNG được vượt tồn thực ở Xưởng. Khác hẳn chính
        # sách SM-03 ("hết tồn thì vẫn hiện, chỉ nói ra"): ở đó hệ quả là phiếu
        # treo chờ hàng, còn ở đây là TỒN ÂM — Odoo không chặn tồn âm ở vị trí
        # nội bộ nên nó hỏng im lặng, và chỉ lộ ra ở kỳ kiểm kê nào đó.
        vat_tu = moves.filtered(
            lambda m: m.dlm_move_kind in ("consume", "return"))
        if vat_tu:
            Quant = self.env["stock.quant"]
            xuong = self.env["stock.location"]._dlm_location(
                "dl_inventory.stock_location_xuong")
            can = {}
            for move in vat_tu:
                can.setdefault(move.product_id, [0.0, move.move_line_ids])
                can[move.product_id][0] += move.product_uom_qty
                can[move.product_id][1] |= move.move_line_ids
            for product, (qty, own_lines) in can.items():
                con = Quant._dlm_available_qty(
                    product, xuong, own_move_lines=own_lines)
                rounding = product.uom_id.rounding or 0.01
                if float_compare(qty, con, precision_rounding=rounding) <= 0:
                    continue
                problems.append(_(
                    "%s: khai %s ra khỏi xưởng nhưng sổ chỉ ghi nhận %s %s "
                    "đang ở Xưởng sản xuất. Vật tư chưa bàn giao ra xưởng thì "
                    "chưa rời kho được — kiểm lại phiếu cấp vật tư."
                ) % (product.display_name, _dlm_fmt(qty), _dlm_fmt(con),
                     product.uom_id.name))

        # §11.13 — hàng Hạng A không vào tồn, nên ĐƠN là danh tính duy nhất của
        # nó. Ghi nhận mà không gắn đơn là ghi vào hư không: không tra ngược
        # được từ tồn kho (không có dòng nào), cũng không từ chứng từ.
        if not self.dlm_sale_order_id:
            khong_ton = moves.filtered(
                lambda m: m.dlm_move_kind == "output"
                and m.product_id.detailed_type != "product").product_id
            if khong_ton:
                problems.append(_(
                    "%s là hàng cấu hình làm theo đơn (không vào tồn kho) nên "
                    "phiếu phải gắn Đơn bán hàng — không có đơn thì sau này "
                    "không truy được lô hàng này làm cho ai."
                ) % ", ".join(khong_ton.mapped("display_name")))
        return problems

    # ── K13 — Nhập thành phẩm (phiếu [8] NTP) ────────────────────────────────
    def _dlm_banner_fg_receipt(self):
        """Dải cho phiếu [8] Nhập thành phẩm.

        Dải "phiếu này không trừ vật tư" KHÔNG nằm ở đây — nó là dải CỐ ĐỊNH
        viết thẳng trong view, luôn hiện và không đóng được (§11.13, cùng khuôn
        với dải phế liệu §11.8). Chỗ này chỉ lo phần thay đổi theo phiếu.
        """
        if self.state == "done":
            return "success", _(
                "Đã ghi nhận mẻ hàng. Hàng làm xong đã vào kho, vật tư khai "
                "dùng đã rời sổ Xưởng."), False
        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        # K16 — nói rõ đang chờ AI, không để phiếu đứng im không lý do.
        if self.dlm_receipt_state == "waiting":
            return "info", _(
                "Xưởng đã bàn giao (%s). Đang chờ <b>Thủ kho</b> đếm thực tế "
                "và bấm \"Xác nhận đã nhận\" — hàng chưa vào sổ kho."
            ) % self.dlm_handover_uid.name, False
        # §11.13 — Hạng A ghi nhận được nhưng KHÔNG sinh tồn. Phải nói ra ngay
        # trên phiếu: người dùng xác nhận xong, sang màn Tồn kho tìm không thấy
        # dòng nào, và kết luận phiếu vừa rồi không ăn thua gì.
        khong_ton = self.move_ids.filtered(
            lambda m: m.dlm_move_kind == "output"
            and m.product_id.detailed_type != "product").product_id
        if khong_ton:
            return "info", _(
                "%s là <b>hàng cấu hình làm theo đơn</b> (Hạng A) — ghi nhận "
                "trên chứng từ, <b>không vào tồn kho</b>. Xác nhận xong sẽ "
                "không thấy dòng nào ở màn Tồn kho, và đó là đúng."
            ) % ", ".join(khong_ton.mapped("display_name")), False
        return False, False, False

    def _dlm_set_transfer_route(self, source_xmlid, dest_xmlid):
        self.ensure_one()
        Location = self.env["stock.location"]
        source = Location._dlm_location(source_xmlid)
        destination = Location._dlm_location(dest_xmlid)
        self.write({
            "location_id": source.id,
            "location_dest_id": destination.id,
        })
        # Dòng hàng đã nhập trước khi bấm preset phải đi theo — nếu không, phiếu
        # nói một đằng mà hàng chạy một nẻo.
        self.move_ids.write({
            "location_id": source.id,
            "location_dest_id": destination.id,
        })
        return True

    def _dlm_open_picking(self, picking, name):
        """RS-02 — Mở phiếu kho bằng ĐÚNG form của Đại Linh.

        🔴 Thiếu `views` là Odoo rơi về `stock.view_picking_form` — form gốc,
        kèm nguyên bộ nút native: "Trả hàng" (đi tắt qua luồng kiểm → trả NCC,
        sinh phiếu loại lung tung), "Hoạt động chi tiết" (sửa lô/vị trí không
        dấu vết), "In"/"In nhãn" (cần wkhtmltopdf mà dự án cố ý không dùng).
        App Inventory gốc đã bị ẩn, nên 6 nút điều hướng của phân hệ là lối vào
        native DUY NHẤT còn lại — bịt ở đây là bịt hết, không phải ẩn từng nút.
        """
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "views": [(picking._dlm_form_view().id, "form")],
            "name": name,
        }

    def _dlm_open_pickings(self, name, context=None):
        """Mở tập phiếu trong `self` bằng cặp tree,form của Đại Linh.

        Một phiếu thì đi thẳng vào form — danh sách một dòng là một cú bấm thừa.
        """
        if len(self) == 1:
            action = self._dlm_open_picking(self, name)
        else:
            kind = self[:1].dlm_picking_kind
            action = {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "name": name,
                "view_mode": "tree,form",
                "views": [
                    (self.env.ref(_DLM_TREE_BY_KIND[kind]).id, "tree"),
                    (self.env.ref(_DLM_FORM_BY_KIND[kind]).id, "form"),
                ],
            }
        action["domain"] = [("id", "in", self.ids)]
        if context:
            action["context"] = context
        return action

    def _dlm_form_view(self):
        """Form Đại Linh ứng với loại việc của phiếu này."""
        self.ensure_one()
        return self.env.ref(_DLM_FORM_BY_KIND[self.dlm_picking_kind])
