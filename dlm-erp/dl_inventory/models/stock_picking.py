# -*- coding: utf-8 -*-
"""Phiếu kho: lô tự sinh, truy vết nguồn gốc, kiểm hàng NCC (nhận 2 bước: NH → KC → TR)."""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import format_datetime
from odoo.tools.float_utils import float_compare, float_is_zero

# Mã trình tự loại hoạt động (không đổi khi user sửa tên hiển thị).
_DLM_QC_CODE = "KC"
_DLM_RETURN_CODE = "TR"
_DLM_TO_SCRAP_CODE = "HPL"
_DLM_FG_RECEIPT_CODE = "NTP"

# Form Đại Linh theo từng loại việc; tra thẳng để loại mới quên khai thì KeyError kêu ngay.
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
# Loại hàng được phép NẰM ở Kho thành phẩm (nơi phiếu Giao hàng lấy hàng).
_DLM_FG_KINDS = ("trading", "manufactured")
# Loại hàng được phép NẰM ở Khu nhập hàng — chỉ hàng NCC giao (vật tư + thương mại).
_DLM_INBOUND_KINDS = ("material", "trading")
# Loại hàng được phép NẰM ở Xưởng: vật tư đã bàn giao, BTP đang làm dở, hàng gia công quay lại sửa.
_DLM_WORKSHOP_KINDS = ("material", "material_processed", "manufactured")
# Loại hàng được phép NẰM ở Kho nguyên vật liệu: vật tư thô + BTP (đã gộp chung).
# Hàng thương mại KHÔNG vào đây — đạt kiểm là đi thẳng sang Kho thành phẩm.
_DLM_MATERIAL_STORE_KINDS = ("material", "material_processed")
# Loại hàng xưởng báo làm xong trên phiếu [8]: sản phẩm gia công + BTP.
_DLM_FG_RECEIPT_KINDS = ("manufactured", "material_processed")


def _dlm_kind_domain(kinds):
    return [("product_kind", "in", list(kinds))]


def _dlm_domain_kinds(domain):
    """Tuple loại hàng của một vị từ, hoặc None nếu vị từ không nói về loại hàng."""
    if (len(domain) == 1 and domain[0][0] == "product_kind"
            and domain[0][1] == "in"):
        return tuple(domain[0][2])
    return None


# Bản đồ luật "khu nào chứa hàng gì" (khớp theo cây, con thừa hưởng luật cha).
# Mỗi luật là một DOMAIN (chạy được dưới SQL + giao bằng expression.AND) vì luật
# khu Phế liệu đọc cờ dlm_is_scrap, không đọc product_kind.
# Bốn cột: (XML ID khu, vị từ, nhãn đọc được, lý do).
_DLM_LOCATION_RULES = (
    ("dl_inventory.stock_location_tp", _dlm_kind_domain(_DLM_FG_KINDS),
     "hàng thương mại, sản phẩm gia công",
     "Kho thành phẩm là nơi phiếu Giao hàng lấy hàng — thứ lọt vào đây sớm "
     "muộn cũng bị giao cho khách."),
    # PHẢI đặt TRƯỚC luật khu cha khosx: _dlm_location_rule lấy match ĐẦU TIÊN theo cây.
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
    # Container thuần đã cấm chọn tay; luật này là lớp thứ 2 phòng khi có ô con thứ ba.
    ("dl_inventory.stock_location_khosx",
     _dlm_kind_domain(_DLM_MATERIAL_STORE_KINDS), "vật tư, bán thành phẩm",
     "Kho nhà máy sản xuất là khu gom nhóm — chọn ô con cụ thể (Kho nguyên vật "
     "liệu hoặc Phế liệu chờ bán)."),
    ("dl_inventory.stock_location_xuong",
     _dlm_kind_domain(_DLM_WORKSHOP_KINDS),
     "vật tư, bán thành phẩm, sản phẩm gia công",
     "Xưởng chỉ nhận thứ đưa vào sản xuất hoặc hàng gia công quay lại sửa."),
)
# Loại việc ĐƯỢC PHÉP đụng khu quá cảnh (nhận/kiểm/trả NCC/hoá phế liệu).
# Viết theo chiều "ai được phép" để loại việc mới mặc định bị chặn.
_DLM_TRANSIT_KINDS = ("receipt", "qc", "vendor_return", "to_scrap")
# Ai được QUYẾT ĐỊNH trả hàng NCC (chốt/huỷ). Thủ kho không nằm đây.
_DLM_RETURN_DECIDERS = (
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# Ai được KÝ NHẬN hàng về xưởng — Thủ kho cố ý không nằm đây (người giao không tự ký đã nhận). Admin/CEO dự phòng.
_DLM_RECEIPT_SIGNERS = (
    "dl_base.dl_group_tech",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# Chiều ngược: hàng từ xưởng về kho thì Thủ kho ký nhận, Kỹ thuật không nằm đây.
_DLM_STORE_SIGNERS = (
    "dl_base.dl_group_warehouse",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)
# Chiều bàn giao → (ai ký nhận, nhãn bên nhận). to_workshop = vật tư ra xưởng; from_workshop = xưởng nộp về.
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

    # ── Liên kết chứng từ ────────────────────────────────────────────────────
    dlm_origin_picking_id = fields.Many2one(
        "stock.picking", string="Phiếu nhận gốc", index=True, copy=False,
        help="Phiếu nhận hàng đã sinh ra phiếu trả nhà cung cấp này.")
    # Đếm (không o2m ngược): phiếu trả neo vào phiếu NHẬN nên o2m rỗng khi đứng ở phiếu KIỂM.
    dlm_return_count = fields.Integer(
        string="Số phiếu trả nhà cung cấp", compute="_compute_dlm_return_count")

    # ── Liên kết phiếu giao ↔ đơn bán hàng ───────────────────────────────────
    # Field này KÍCH HOẠT khoá reset-nháp của đơn (dl_sale dò mọi m2o trỏ dl.sale.order);
    # đổi tên/gỡ sẽ âm thầm mở lại đường đưa đơn đã giao về nháp.
    dlm_sale_order_id = fields.Many2one(
        "dl.sale.order", string="Đơn bán hàng", index=True, copy=False,
        ondelete="restrict",
        help="Đơn đã sinh ra phiếu giao này.")
    # Tổng số lượng phiếu (cột "Số lượng trả" màn Trả NCC); không store vì chỉ để đọc.
    dlm_qty_total = fields.Float(
        string="Tổng số lượng", digits="Product Unit of Measure",
        compute="_compute_dlm_qty_total")
    dlm_reject_summary = fields.Char(
        string="Lý do", compute="_compute_dlm_reject_summary")

    # ── Lọc mặt hàng theo ngữ cảnh phiếu ─────────────────────────────────────
    # Nuôi domain product_id trên dòng hàng: chỉ hiện mặt hàng hợp lệ theo ngữ cảnh.
    # Đặt invisible để web client evaluate được parent.<field>; non-store.
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

    # ── Loại việc cho "Hàng đợi phiếu" ───────────────────────────────────────
    # Cho JS biết mở phiếu bằng đúng action chuyên biệt của từng loại (form Nhận ≠ form Kiểm); non-store.
    dlm_picking_kind = fields.Selection([
        ("receipt", "Nhận hàng"),
        ("qc", "Kiểm hàng"),
        ("transfer", "Chuyển kho"),
        ("delivery", "Giao hàng"),
        ("vendor_return", "Trả hàng nhà cung cấp"),
        ("scrap_sale", "Bán phế liệu"),
        ("to_scrap", "Hoá phế liệu"),
        ("fg_receipt", "Nhập kho từ xưởng"),
        ("other", "Khác"),
    ], string="Loại việc", compute="_compute_dlm_picking_kind")

    # ── Mặt hàng được phép lên phiếu [8] Nhập thành phẩm ─────────────────────
    # Danh sách CHO PHÉP (tập nhỏ, đóng — đúng thứ xưởng làm ra).
    dlm_fg_product_ids = fields.Many2many(
        "product.product", string="Mặt hàng xưởng làm ra",
        compute="_compute_dlm_fg_product_ids",
        help="Sản phẩm gia công và bán thành phẩm; gắn đơn bán hàng thì thu hẹp "
             "tiếp về đúng những gì đơn đó đặt.")

    @api.depends("dlm_sale_order_id", "dlm_sale_order_id.line_ids.product_id")
    def _compute_dlm_fg_product_ids(self):
        """Lọc theo loại hàng + thu hẹp theo đơn khi phiếu gắn đơn (phế liệu không thuộc đơn nào)."""
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

    # ── Hai bảng của phiếu mẻ, cùng một move_ids ─────────────────────────────
    # Tách bằng DOMAIN (cùng dòng dịch chuyển, khác vai trò) vì hỏi hai câu khác nhau.
    dlm_fg_move_ids = fields.One2many(
        "stock.move", "picking_id", string="Xưởng nộp về",
        domain=[("dlm_move_kind", "=", "output")])
    dlm_material_move_ids = fields.One2many(
        "stock.move", "picking_id", string="Vật tư ra khỏi xưởng",
        domain=[("dlm_move_kind", "in", ("consume", "return"))])

    def _dlm_moves(self):
        """Dòng hàng của phiếu = HỢP cả ba ô o2m (client onchange gửi 3 field độc lập, move_ids rỗng tới khi Lưu)."""
        self.ensure_one()
        return self.move_ids | self.dlm_fg_move_ids | self.dlm_material_move_ids

    # ── Vật tư ĐANG NẰM ở Xưởng, cho bảng "Vật tư ra khỏi xưởng" ─────────────
    # Danh sách CHO PHÉP dựng từ TỒN THỰC (không cho chọn thứ chưa bàn giao ⇒ tránh tồn âm).
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
            # Dòng đã khai giữ nguyên kể cả khi tồn về 0 (không thì mở phiếu cũ thấy ô trống).
            picking.dlm_workshop_material_ids = (
                products | picking._dlm_moves().filtered(
                    lambda m: m.dlm_move_kind in ("consume", "return")
                ).product_id)

    # ── Cấp vật tư BỔ SUNG ngoài định mức (phiếu [3]) ────────────────────────
    # Ca thật: BOM 100 cây, đã cấp đủ, thợ cắt hỏng cần thêm 10 cây. B1 chưa có
    # tầng phê duyệt riêng — lá chắn là Thủ kho lập + 2 chữ ký + lý do ghi vết.
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

    # Đối chiếu định mức, chỉ hiện khi gắn đơn; non-store vì đọc tổng đã cấp của mọi phiếu khác.
    dlm_bom_hint = fields.Html(
        string="Đối chiếu định mức", compute="_compute_dlm_bom_hint",
        sanitize=False)

    @api.depends("dlm_sale_order_id", "move_ids.product_id",
                 "move_ids.product_uom_qty", "state")
    def _compute_dlm_bom_hint(self):
        for picking in self:
            picking.dlm_bom_hint = picking._dlm_build_bom_hint()

    # ── Hoá phế liệu ─────────────────────────────────────────────────────────
    # Lý do BẮT BUỘC: đây là bút toán làm một mặt hàng biến mất khỏi sổ, phải giải thích được về sau.
    dlm_scrap_reason = fields.Char(
        string="Lý do hoá phế liệu", copy=False,
        help="Vì sao lô hàng này thành phế liệu: Nhà cung cấp giảm trừ công nợ và mình "
             "giữ hàng lại, thép để lâu bị gỉ, cắt hỏng…")
    # Nuôi nút [Chuyển thành phế liệu] trên phiếu trả đã huỷ; non-store vì đọc tồn thật (đổi theo mọi phiếu).
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

    # ── Chữ ký nhận hàng khi bàn giao (2 bước, chặn cứng) ────────────────────
    # Chữ ký là bước HOÀN TẤT phiếu (không phải ô điền sau): chưa ký ⇒ hàng vẫn
    # thuộc kho, không có khoảng "đã xuất mà chưa ai nhận".
    # Hai chiều: ra xưởng thì Thủ kho giao/Kỹ thuật ký; về kho thì ngược lại.
    # Nhãn lấy từ _DLM_RECEIPT_FLOWS, không viết cứng "xưởng".
    dlm_receipt_flow = fields.Selection([
        ("none", "Không cần ký"),
        ("to_workshop", "Kho bàn giao ra xưởng"),
        ("from_workshop", "Xưởng nộp về kho"),
    ], string="Chiều bàn giao", compute="_compute_dlm_receipt_state", store=True)
    dlm_needs_receipt = fields.Boolean(
        string="Cần chữ ký nhận hàng", compute="_compute_dlm_receipt_state",
        store=True)
    # store=True: màn phiếu [8] lọc/nhóm theo field này (compute non-stored không dùng được trong domain/group_by).
    dlm_receipt_state = fields.Selection([
        ("none", "Không cần ký"),
        ("ready", "Chờ bàn giao"),
        ("waiting", "Chờ bên nhận xác nhận"),
        ("received", "Bên nhận đã ký"),
    ], string="Tình trạng bàn giao", compute="_compute_dlm_receipt_state",
        store=True)
    # store=True cho cả 4 field của compute này để Odoo không cảnh báo trộn field lưu/không lưu.
    dlm_receiver_label = fields.Char(
        string="Bên nhận", compute="_compute_dlm_receipt_state", store=True,
        help="Ai phải ký nhận phiếu này — đọc từ chiều bàn giao.")
    # copy=False: nhân bản phiếu mà kéo theo chữ ký cũ là chế ra bằng chứng nhận hàng chưa từng xảy ra.
    dlm_handover_uid = fields.Many2one(
        "res.users", string="Thủ kho bàn giao", readonly=True, copy=False)
    dlm_handover_date = fields.Datetime(
        string="Thời điểm bàn giao", readonly=True, copy=False)
    dlm_received_uid = fields.Many2one(
        "res.users", string="Người nhận (bên Xưởng)", readonly=True, copy=False)
    dlm_received_date = fields.Datetime(
        string="Thời điểm nhận", readonly=True, copy=False)

    # Depends picking_type_id chứ không dlm_picking_kind (field kia cũng non-stored, tránh xâu 2 lớp compute).
    @api.depends("picking_type_id", "location_dest_id",
                 "dlm_handover_uid", "dlm_received_uid")
    def _compute_dlm_receipt_state(self):
        # ĐÍCH DANH, không child_of: Xưởng sản xuất là ô LÁ.
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

    # ── Trạng thái kiểm hàng ─────────────────────────────────────────────────
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
    dlm_qc_has_over = fields.Boolean(
        string="Có dòng vượt số chờ kiểm", compute="_compute_dlm_qc_has_over",
        help="Bật khi Đạt + Loại của dòng nào đó vượt số đang chờ kiểm — xảy ra "
             "khi số chờ kiểm co lại (tách kiện) sau khi đã nhập số. Nút Khớp "
             "lại số hạ Đạt về cho vừa.")
    dlm_wait_receipt = fields.Boolean(
        string="Chờ nhận hàng xong", compute="_compute_dlm_wait_receipt",
        help="Phiếu kiểm của lô hàng mà thủ kho CHƯA đếm xong: chưa có gì để "
             "kiểm chất lượng.")

    # ── Chặn xác nhận + dải thông báo (INLINE, không modal) ──────────────────
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
        """Suy loại việc từ loại hoạt động — phải khớp sequence_code TRƯỚC code (KC/CK/HPL/NTP đều internal)."""
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
        """Gộp lý do loại của các dòng thành 1 dòng đọc được trên list (để Mua hàng xếp thứ tự gọi NCC)."""
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
        """Loại trừ mặt hàng mà nơi lấy/nơi nhận không được phép chứa (luật khu cố định); danh sách LOẠI TRỪ, rỗng = không cấm gì."""
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
        """Vị từ mặt hàng hợp lệ ở CẢ nơi lấy lẫn nơi nhận (GIAO bằng expression.AND); None = không hạn chế, khác với domain cấm sạch."""
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
        """(vị từ, nhãn, lý do) của một vị trí — khớp theo CÂY (con thừa hưởng luật cha); [] = không hạn chế."""
        if not location or not location.parent_path:
            return [], "", ""
        for xml_id, domain, label, reason in _DLM_LOCATION_RULES:
            area = self.env.ref(xml_id, raise_if_not_found=False)
            if (area and area.parent_path
                    and location.parent_path.startswith(area.parent_path)):
                return domain, label, reason
        return [], "", ""

    def _dlm_dest_rule(self):
        """Luật của vị trí ĐÍCH (vị từ + nhãn + lý do) — chỉ soi đầu đích, dùng chặn lúc xác nhận."""
        self.ensure_one()
        return self._dlm_location_rule(self.location_dest_id)

    @api.depends("dlm_sale_order_id", "dlm_sale_order_id.line_ids.product_id")
    def _compute_dlm_orderable_product_ids(self):
        """SP nằm trên đơn bán gắn với phiếu giao; rỗng khi chưa gắn đơn."""
        for picking in self:
            picking.dlm_orderable_product_ids = (
                picking.dlm_sale_order_id.line_ids.product_id)

    # ── Cửa tạo phiếu giao THỦ CÔNG bám theo đơn ─────────────────────────────
    # Phiếu giao có 2 cửa: nút [Tạo phiếu giao] trên đơn + nút New ở màn Kho.
    # Hai onchange dưới làm cửa thứ hai nói cùng thứ tiếng; CHỈ chạy cho phiếu
    # Giao hàng (dlm_sale_order_id còn có mặt trên phiếu cấp vật tư/nhập kho).
    @api.onchange("partner_id")
    def _onchange_dlm_partner_resets_order(self):
        """Đổi khách ⇒ bỏ đơn + dòng hàng của khách cũ (không thì đơn cũ nhảy 'đã giao' vì chuyến khách kia)."""
        for picking in self:
            if picking.dlm_picking_kind != "delivery" or picking.state != "draft":
                continue
            order = picking.dlm_sale_order_id
            if order and order.partner_id != picking.partner_id:
                picking.dlm_sale_order_id = False
                picking.move_ids = [(5, 0, 0)]

    @api.onchange("dlm_sale_order_id")
    def _onchange_dlm_sale_order_fills_moves(self):
        """Chọn đơn ⇒ tự điền phần còn lại của đơn vào bảng giao (đọc _dlm_remaining_qty để không giao gấp đôi; exclude_picking = phiếu đang lập)."""
        self.ensure_one()
        if self.dlm_picking_kind != "delivery" or self.state != "draft":
            return
        order = self.dlm_sale_order_id
        if not order:
            return

        # Tính TRƯỚC khi xoá: phép trừ đọc dòng từ DB, không treo vào cache Odoo.
        remaining = order._dlm_remaining_qty(exclude_picking=self._origin)
        if not remaining:
            # Không phải lỗi (đơn đã lên phiếu đủ), nhưng cảnh báo để user không tưởng hệ thống hỏng.
            self.move_ids = [(5, 0, 0)]
            return {"warning": {
                "title": _("Đơn này không còn hàng để lên phiếu"),
                "message": _(
                    "Mọi mặt hàng của đơn %s đã giao xong hoặc đang nằm trên "
                    "một phiếu giao khác. Kiểm lại các phiếu giao của đơn trước "
                    "khi lập thêm phiếu mới.") % order.name,
            }}

        source = self.location_id
        destination = self.location_dest_id
        # Xoá + điền trong CÙNG một lệnh (gán move_ids hai lần liên tiếp không chắc thấy nhau).
        self.move_ids = [(5, 0, 0)] + [(0, 0, {
            "name": product.display_name,
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": qty,
            "location_id": source.id,
            "location_dest_id": destination.id,
        }) for product, qty in remaining.items()]

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

    @api.depends("move_ids.dlm_qc_over", "picking_type_id")
    def _compute_dlm_qc_has_over(self):
        for picking in self:
            picking.dlm_qc_has_over = (
                picking.picking_type_id.sequence_code == _DLM_QC_CODE
                and any(picking.move_ids.mapped("dlm_qc_over")))

    @api.depends("picking_type_id", "state", "move_ids.move_orig_ids.state")
    def _compute_dlm_wait_receipt(self):
        """Phiếu kiểm chỉ tới lượt sau khi phiếu nhận gốc được xác nhận (số thực nhận đã đếm)."""
        for picking in self:
            if not picking.dlm_is_qc or picking.state in ("done", "cancel"):
                picking.dlm_wait_receipt = False
                continue
            receipt = picking._dlm_source_receipt()
            picking.dlm_wait_receipt = bool(
                receipt and receipt.state != "done")

    @api.depends(
        "state", "picking_type_id", "partner_id", "location_id",
        "location_dest_id", "dlm_qty_rejected_total",
        "move_ids.quantity", "move_ids.product_uom_qty", "move_ids.dlm_qc_over",
        "move_ids.dlm_qty_rejected", "move_ids.dlm_reject_reason",
        "move_ids.dlm_reject_note", "move_ids.product_id", "move_ids.state",
        "move_line_ids.lot_id", "move_line_ids.lot_name",
        "move_ids.move_orig_ids.state",
        "dlm_handover_uid", "dlm_received_uid",
        # Hai ô của phiếu [8] phải có trong depends, không thì dải không nổ lại khi gõ dòng vào chúng.
        "dlm_fg_move_ids.product_id", "dlm_fg_move_ids.product_uom_qty",
        "dlm_fg_move_ids.dlm_move_kind",
        "dlm_material_move_ids.product_id",
        "dlm_material_move_ids.product_uom_qty",
        "dlm_material_move_ids.dlm_move_kind")
    def _compute_dlm_banner(self):
        """MỘT dải thông báo theo ngữ cảnh cho cả phiếu nhận lẫn kiểm (mỗi trạng thái đúng 1 dải, nêu hệ quả)."""
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
        # PHẢI đứng trước nhánh internal chung: HPL cũng internal, rơi vào dải Chuyển kho thì nói sai bản chất (đây là ĐỔI MẶT HÀNG).
        if self.picking_type_id.sequence_code == _DLM_TO_SCRAP_CODE:
            return self._dlm_banner_to_scrap()
        # Cũng đứng trước nhánh internal: nguồn phiếu [8] là vị trí ảo Sản xuất (không bao giờ có tồn) ⇒ dải Chuyển kho sẽ bêu "không đủ hàng".
        if self.picking_type_id.sequence_code == _DLM_FG_RECEIPT_CODE:
            return self._dlm_banner_fg_receipt()
        if self.picking_type_id.code == "outgoing":
            return self._dlm_banner_delivery()
        if self.picking_type_id.code == "internal":
            return self._dlm_banner_transfer()
        return False, False, False

    # ── Ca ngoại lệ báo INLINE, không modal tiếng Anh ────────────────────────
    def _dlm_confirm_problems(self):
        """Lỗi CHẶN xác nhận, dùng chung cho dải đỏ và guard server (một nguồn để không lệch nhau)."""
        self.ensure_one()
        problems = []
        if (self.dlm_picking_kind == "transfer" and self.location_id
                and self.location_id == self.location_dest_id):
            problems.append(_(
                "Lấy hàng từ và Chuyển tới đang là cùng một chỗ (%s) — phiếu "
                "này không làm tồn kho thay đổi gì.")
                % self.location_id.display_name)
        # Lá chắn server: domain trên view chỉ lọc dropdown, import/RPC vẫn nhét khu quá cảnh vào phiếu.
        # Luật phát biểu theo VỊ TRÍ, không theo màn (neo vào loại việc thì loại việc mới sẽ lọt).
        # Phiếu hệ thống sinh (Nhận/Kiểm/Trả) vẫn đi qua khu đó — liệt kê ai ĐƯỢC phép.
        if self.dlm_picking_kind not in _DLM_TRANSIT_KINDS:
            cam = (self.location_id | self.location_dest_id).filtered(
                "dlm_no_inventory")
            if cam:
                problems.append(_(
                    "Không được chọn khu quá cảnh (%s) trên phiếu này — số ở đó "
                    "chỉ đổi qua phiếu Nhận hàng / Kiểm & cất / Trả nhà cung cấp. "
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
        # Lọc dropdown chỉ chặn dòng THÊM MỚI; ca lọt: thêm dòng vật tư hợp lệ rồi bấm lối tắt đổi đích cả dòng cũ.
        problems.extend(self._dlm_dest_rule_problems())
        if self.dlm_picking_kind == "fg_receipt":
            problems.extend(self._dlm_fg_receipt_problems())
        # Cấp bổ sung phải nói VÌ SAO ngay lúc cấp — dữ liệu duy nhất cho biết hao hụt thật lệch định mức.
        if self.dlm_is_extra_issue and not self.dlm_extra_reason:
            problems.append(_(
                "Phiếu đánh dấu \"Cấp bổ sung ngoài định mức\" thì phải chọn "
                "lý do — đây là chỗ duy nhất ghi lại vì sao xưởng cần thêm vật "
                "tư ngoài BOM."))
        return problems

    def _dlm_dest_rule_problems(self):
        """Luật "khu nào chứa hàng gì" áp theo ĐÍCH CỦA TỪNG DÒNG (phiếu Kiểm/Hoá phế liệu có đích khác nhau mỗi dòng)."""
        self.ensure_one()
        problems = []
        theo_dich = {}
        for move in self._dlm_moves():
            if not move.product_id:
                continue
            dest = move.location_dest_id or self.location_dest_id
            # filtered_domain: đánh giá vị từ trong Python (luật khu Phế liệu đọc dlm_is_scrap).
            domain, label, reason = self._dlm_location_rule(dest)
            if not domain or move.product_id.filtered_domain(domain):
                continue
            theo_dich.setdefault(
                (dest, label, reason), []).append(move.product_id.display_name)
        for (dest, label, reason), ten in theo_dich.items():
            # Câu chặn sinh từ chính bản đồ luật (nhãn nằm trong luật) để không nói sai khu.
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
        # Đứng TRƯỚC _dlm_confirm_problems: khi đã bàn giao thì dải phải nói ai đang cầm bóng.
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
        # Chuyển nhiều hơn tồn: domain chỉ lọc mặt hàng CÓ tồn, không nói SỐ LƯỢNG. Native để phiếu treo im lặng.
        thieu = self._dlm_shortage_lines()
        if thieu:
            return "warning", _(
                "%s không đủ hàng để chuyển:<ul>%s</ul>Xác nhận thì phiếu treo "
                "chờ hàng, không chuyển được ngay. Sửa lại số, hoặc chọn khu "
                "khác đang có hàng."
            ) % (self.location_id.display_name or _("Khu nguồn"),
                 "".join("<li>%s</li>" % t for t in thieu)), False
        if self.state == "draft":
            # Nói ra vì sao danh sách mặt hàng ngắn đi (không thì dropdown thiếu món thành bí ẩn).
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
        """Câu giải thích danh sách mặt hàng bị thu hẹp (rỗng nếu không hạn chế)."""
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
        """Nhãn KẾT QUẢ CUỐI (GIAO của hai đầu phiếu, không ghép hai luật); "" = không hạn chế."""
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
        """Dòng đang đòi chuyển nhiều hơn tồn khả dụng ở khu nguồn (tách 3 ca: hết sạch / bị giữ hết / thiếu một phần)."""
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
            # Khả dụng = 0 nhưng còn tồn thực: hàng có mặt nhưng đã có chủ (đừng đẩy đi mua).
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
        # Bán nhiều hơn tồn: native để phiếu treo im lặng. _dlm_qty_available cộng lại phần chính phiếu này giữ.
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
        """Số KHẢ DỤNG của product tại vị trí lấy của phiếu — vỏ mỏng quanh stock.quant._dlm_available_qty."""
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
                    "khu <b>Chờ trả nhà cung cấp</b>%s — Mua hàng xử lý tiếp với nhà "
                    "cung cấp."
                ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                     _(" (phiếu %s)") % returns if returns else ""), False
            return "success", _("Đã kiểm đạt toàn bộ và cất vào kho."), False

        if self.dlm_wait_receipt:
            # Không phải lỗi của thủ kho — chỉ là chưa tới lượt; dải đỏ ở đây đọc như bị mắng.
            return "info", _(
                "Hàng chưa nhận xong. Xác nhận phiếu nhận <b>%s</b> (đếm số "
                "thực nhận) thì lô hàng mới xuống đây để kiểm chất lượng."
            ) % self._dlm_source_receipt().name, True

        problems = self._dlm_qc_problems()
        if problems:
            return "danger", _(
                "Chưa xác nhận kiểm được:<ul>%s</ul>"
            ) % "".join("<li>%s</li>" % p for p in problems), True

        if self.dlm_qty_rejected_total > 0:
            message = _(
                "Xác nhận kiểm sẽ chuyển <b>%s</b> đơn vị hàng loại sang khu "
                "<b>Chờ trả nhà cung cấp</b> và tạo <b>phiếu trả hàng (nháp)</b> để Mua "
                "hàng thoả thuận với %s. Phần đạt được cất vào kho."
            ) % (_dlm_fmt(self.dlm_qty_rejected_total),
                 self.partner_id.display_name or _("nhà cung cấp"))
            missing = self._dlm_evidence_missing_names()
            if missing:
                message += _(
                    "<br/><br/>Chưa có <b>ảnh bằng chứng</b> cho:<ul>%s</ul>"
                    "Chụp lúc hàng còn trên tay — xác nhận xong là <b>khoá "
                    "lại</b>, không bổ sung được nữa."
                ) % "".join("<li>%s</li>" % n for n in missing)
            return "warning", message, False

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

        # Mặt hàng chưa có bảng giá đang áp dụng ⇒ giá vốn có thể sai. Chỉ cảnh báo (không chặn), để kịp báo Mua hàng chốt giá.
        unpriced = self._dlm_receipt_unpriced_names()
        price_block = _(
            "<b>Chưa có bảng giá đang áp dụng</b> từ nhà cung cấp này cho:<ul>%s</ul>"
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
                "Nhà cung cấp giao thiếu so với dự kiến:<ul>%s</ul>Xác nhận sẽ tạo "
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
        """Tên mặt hàng trên phiếu mà NCC này chưa có bảng giá đang áp dụng (sudo: chỉ đọc CÓ/KHÔNG, không đưa giá lên UI Kho)."""
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
            # Đọc theo location_id THẬT: ô "Lấy hàng từ" đổi được, dải viết cứng sẽ báo sai.
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
                "Đã trả hàng cho nhà cung cấp và trừ khỏi khu Chờ trả nhà cung cấp."), False
        if self.state == "draft":
            return "info", _(
                "Phiếu này do bước <b>kiểm hàng</b> sinh ra và cố ý để "
                "<b>nháp</b>: thoả thuận với %s trước (đổi hàng, giảm trừ công "
                "nợ, hay nhà cung cấp tự đến lấy), rồi mới xác nhận. Xác nhận sẽ trừ hàng "
                "khỏi khu <b>Chờ trả nhà cung cấp</b>."
            ) % (self.partner_id.display_name or _("nhà cung cấp")), False
        return "info", _(
            "Đã chốt trả hàng. Xác nhận phiếu khi hàng thực sự rời kho."), False

    def _dlm_qc_problems(self):
        """Danh sách lỗi cụ thể chặn xác nhận kiểm (nêu đích danh từng dòng)."""
        self.ensure_one()
        problems = []
        if self.dlm_wait_receipt:
            # Trả về NGAY: mọi lỗi dòng bên dưới đều vô nghĩa khi hàng chưa về,
            # và số trên dòng lúc này là số NCC hứa giao chứ không phải số đếm được.
            return [_(
                "Phiếu nhận %s chưa xác nhận — đếm số thực nhận ở đó trước, "
                "kiểm chất lượng làm sau."
            ) % (self._dlm_source_receipt().name or "")]
        for move in self.move_ids:
            name = move.product_id.display_name
            if move.dlm_qty_rejected < 0:                                # QC-01
                problems.append(_("%s: số loại không được âm.") % name)
            if move.dlm_qc_over:                                         # QC-02
                problems.append(_(
                    "%s: Đạt + Loại = %s, vượt quá %s đang chờ kiểm. Bấm "
                    "\"Khớp lại số\" để hạ Đạt về %s, hoặc sửa tay."
                ) % (name, _dlm_fmt(move.quantity + move.dlm_qty_rejected),
                     _dlm_fmt(move.product_uom_qty),
                     _dlm_fmt(max(move.product_uom_qty - move.dlm_qty_rejected,
                                  0.0))))
            if move.dlm_qty_rejected > 0 and not move.dlm_reject_reason:  # QC-03
                problems.append(_("%s: có hàng loại nhưng chưa chọn lý do.") % name)
            if (move.dlm_reject_reason == "other"
                    and not (move.dlm_reject_note or "").strip()):        # QC-04
                problems.append(_("%s: lý do \"Khác\" phải ghi rõ ở ô ghi chú.") % name)
        problems.extend(
            _("%s: chưa có số lô.") % n for n in self._dlm_lot_missing_names())
        # Xác nhận khi mọi dòng Đạt 0 + Loại 0 ⇒ tránh lỗi native modal tiếng Anh. Kiểm sau cùng để không che lỗi cụ thể.
        if not problems and self.move_ids and not any(
                move.quantity or move.dlm_qty_rejected
                for move in self.move_ids):
            problems.append(_(
                "Chưa nhập kết quả kiểm cho dòng nào — điền số Đạt (và số Loại "
                "nếu có hàng lỗi), hoặc bấm \"Đạt tất cả\"."))
        return problems

    def _dlm_evidence_missing_names(self):
        """Mặt hàng có hàng loại mà chưa đính ảnh (cố ý cảnh báo mềm, không chặn — ép chụp sẽ ra ảnh rác)."""
        self.ensure_one()
        return sorted({
            move.product_id.display_name for move in self.move_ids
            if move.dlm_qty_rejected > 0 and not move.dlm_evidence_ids})

    def _dlm_lot_missing_names(self):
        """Mặt hàng theo lô đã nhập số nhưng chưa gán lô (không có lô = đứt truy vết)."""
        self.ensure_one()
        names = set()
        for line in self.move_line_ids:
            if (line.product_id.tracking == "lot"
                    and not float_is_zero(line.quantity, precision_digits=3)
                    and not line.lot_id and not line.lot_name):
                names.add(line.product_id.display_name)
        return sorted(names)

    # ── Quyết định trả hàng là của Mua hàng, không của Thủ kho ───────────────
    def action_confirm(self):
        self._dlm_check_return_decision(_("chốt phiếu trả hàng nhà cung cấp"))
        # Lưới chặn cuối cho RPC/smart button; đường chính là dải đỏ inline + nút tự ẩn.
        for picking in self:
            problems = picking._dlm_confirm_problems()
            if problems:
                raise UserError(_("Chưa xác nhận phiếu %s được:\n%s") % (
                    picking.name, "\n".join("• %s" % p for p in problems)))
        return super().action_confirm()

    def action_cancel(self):
        self._dlm_check_return_decision(_("huỷ phiếu trả hàng nhà cung cấp"))
        return super().action_cancel()

    def _dlm_check_return_decision(self, viec):
        """Chặn quyết định trả hàng ở SERVER, không tin groups trên nút (RPC/smart button né được view)."""
        returns = self.filtered(
            lambda p: p.picking_type_id.sequence_code == _DLM_RETURN_CODE)
        if not returns or self.env.su:
            return True
        if any(self.env.user.has_group(role) for role in _DLM_RETURN_DECIDERS):
            return True
        raise UserError(_(
            "Bạn không có quyền %s. Trả hàng cho nhà cung cấp là quyết định của "
            "bộ phận Mua hàng — họ còn phải thoả thuận đổi hàng hay giảm trừ "
            "công nợ. Thủ kho chỉ bấm \"Xác nhận đã trả\" khi xe nhà cung cấp tới lấy "
            "hàng.") % viec)

    # ── Mỗi phiếu nhận sinh ĐÚNG MỘT phiếu kiểm ──────────────────────────────
    def _dlm_group_receipt_moves(self):
        """Gắn mỗi phiếu nhận một nhóm cung ứng riêng để _assign_picking không trộn hàng nhiều NCC vào 1 phiếu kiểm (gọi từ move._action_confirm)."""
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

    # ── Lô tự sinh & đóng dấu nguồn gốc ──────────────────────────────────────
    def button_validate(self):
        # Lưới chặn server cho phiếu [9] Hoá phế liệu — đặt ở button_validate (điểm không đảo ngược), không ở action_confirm.
        for picking in self.filtered(
                lambda p: p.dlm_picking_kind == "to_scrap"):
            problems = picking._dlm_to_scrap_problems()
            if problems:
                raise UserError(_("Chưa xác nhận phiếu %s được:\n%s") % (
                    picking.name, "\n".join("• %s" % p for p in problems)))
            picking._dlm_sync_to_scrap_qty()
        # Chốt chặn cứng luồng hai chữ ký: đường hợp lệ duy nhất là action_dlm_confirm_receipt.
        # Không miễn trừ env.su (lối ký cũng chạy sudo nhưng đã ghi dlm_received_uid).
        # Lưới chặn server cho phiếu [8], cùng khuôn phiếu [9].
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


    def _check_warn_sms(self):
        """Không bao giờ mở hộp thoại hỏi SMS (không gọi super vì stock_sms có thể không cài)."""
        return self.browse()

    def _send_confirmation_email(self):
        """Không gửi SMS (dùng cửa thoát skip_sms của stock_sms), phiếu vẫn gửi email xác nhận như thường."""
        return super(
            StockPicking, self.with_context(skip_sms=True)
        )._send_confirmation_email()

    def _action_done(self):
        """Đóng dấu nguồn gốc lô khi phiếu nhập hoàn tất (ở _action_done vì button_validate có thể trả wizard)."""
        res = super()._action_done()
        self._dlm_stamp_lot_origin()
        return res

    def _dlm_stamp_lot_origin(self):
        """Ghi NCC + ngày nhập + phiếu nguồn lên lô vừa nhận (chỉ phiếu NHẬP, chỉ lô chưa có nguồn — để truy vết trỏ về NCC)."""
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
        """Điền số lô tự sinh cho dòng lô SINH RA còn trống (hàng NCC giao + hàng xưởng làm xong); phiếu xuất/chuyển thì tiêu thụ lô có sẵn."""
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

    # ── Hành động trên màn Kiểm & cất hàng ───────────────────────────────────
    def action_dlm_pass_all(self):
        """Nút "Đạt tất cả": điền Đạt = số NCC giao cho mọi dòng (ca phổ biến nhất)."""
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

    def action_dlm_fix_qc_counts(self):
        """Nút "Khớp lại số": hạ Đạt về (số chờ kiểm − Loại) cho dòng đang vượt.

        Gỡ ca kẹt câm: số chờ kiểm co lại (tách kiện/backorder) SAU khi đã nhập
        Đạt + Loại ⇒ tổng vượt mà onchange (chỉ chạy lúc gõ Loại) không bắt được,
        phiếu không xác nhận nổi. Giữ nguyên số Loại vì đó là số đếm thật."""
        self.ensure_one()
        for move in self.move_ids.filtered("dlm_qc_over"):
            move.quantity = max(
                move.product_uom_qty - move.dlm_qty_rejected, 0.0)
            move.picked = True
        return True

    def action_dlm_validate_qc(self):
        """Xác nhận kiểm: hàng đạt vào kho, hàng loại sang khu Chờ trả NCC (thu hẹp nhu cầu dòng gốc về số đạt trước khi tách)."""
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

        # skip_backorder: không mở modal hỏi phiếu chờ tiếp; phần chưa kiểm vẫn tách sang phiếu kiểm mới.
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
                # Loại SẠCH cả dòng: đổi thẳng đích dòng gốc (tách ra thì dòng gốc nhu cầu 0, Odoo huỷ, mất kết quả kiểm).
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
                # Kết quả kiểm ở lại dòng GỐC; dòng tách chỉ chở hàng đi, mang theo lý do.
                "dlm_reject_reason": move.dlm_reject_reason,
                "dlm_reject_note": move.dlm_reject_note,
                # Ảnh dùng CHUNG bản ghi ir.attachment, không nhân bản file.
                "dlm_evidence_ids": [(6, 0, move.dlm_evidence_ids.ids)],
            })
            # Nhu cầu dòng gốc bớt đúng phần loại (không đặt bằng số đạt, không thì phần chưa kiểm biến mất).
            # sudo: stock.move.write ghi chatter, message_post nổ nếu user chưa khai email.
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
        """Đạt + hàng thương mại → Kho thành phẩm THẲNG (mua về bán lại, không qua sản xuất); vật tư vẫn về Kho nguyên vật liệu."""
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
        # sudo: stock.move.write ghi chatter, message_post nổ nếu user thiếu email.
        moves.sudo().write({"location_dest_id": tp.id})
        moves.move_line_ids.location_dest_id = tp

    def _dlm_force_lot_on(self, moves):
        """Gán lô cho dòng hàng loại nếu giữ chỗ không tự gán (mất lô = mất bằng chứng khiếu nại NCC); suy từ dòng khác của phiếu rồi tồn ở khu Chờ kiểm."""
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
        """Phiếu [3] Trả hàng NCC — để NHÁP giao Mua hàng (trả hàng là việc đối ngoại, phải thoả thuận với NCC trước)."""
        self.ensure_one()
        return_type = self.env.ref(
            "dl_inventory.picking_type_vendor_return", raise_if_not_found=False)
        if not return_type:
            return self.env["stock.picking"]
        reject_location = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_nhan_tra")
        receipt = self._dlm_source_receipt()
        partner = receipt.partner_id or self.partner_id

        # sudo: RS-03 chặn Thủ kho tạo phiếu trả, nhưng phiếu này là hệ quả máy móc của kết quả kiểm.
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": return_type.id,
            "partner_id": partner.id,
            "location_id": reject_location.id,
            "location_dest_id": return_type.default_location_dest_id.id,
            "origin": receipt.name or self.name,
            # Trỏ về phiếu NHẬN gốc, không rơi về self (phiếu kiểm không có trên chứng từ NCC nào).
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
                # Bằng chứng để Mua hàng đàm phán với NCC (chỉ dropdown lý do thì không cãi được).
                "dlm_evidence_ids": [(6, 0, move.dlm_evidence_ids.ids)],
            }) for move in rejected_moves],
        })
        # sudo: ghi chatter là dấu vết; message_post nổ nếu user thiếu email, không được rollback cả phiếu kiểm.
        picking.sudo().message_post(body=_(
            "Sinh tự động từ kết quả kiểm phiếu %s. Phiếu để <b>nháp</b>: Mua "
            "hàng thoả thuận với nhà cung cấp rồi mới xác nhận trả."
        ) % self.name)
        self._dlm_notify_purchasing(picking)
        return picking

    def _dlm_notify_purchasing(self, return_picking):
        """Giao việc cho nhóm Mua hàng — phiếu trả nháp không ai biết là nằm im."""
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        if not group:
            return
        summary = _("Xử lý trả hàng nhà cung cấp — %s") % return_picking.name
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
            note = (Markup(_(": %s")) % move.dlm_reject_note
                    if move.dlm_reject_note else Markup(""))
            # Ghi rõ có/không ảnh vào chatter để đọc biết ngay có bằng chứng hay không.
            anh = (Markup(_(" — kèm <b>%s</b> ảnh")) % move.dlm_evidence_count
                   if move.dlm_evidence_count
                   else Markup(_(" — <b>không có ảnh</b>")))
            # Markup, không phải str: message_post escape chuỗi thường (chatter hiện "&lt;li&gt;"); tên/ghi chú user vẫn được escape đúng.
            rows.append(Markup(_("<li>%s — loại <b>%s</b> %s (%s)%s%s</li>")) % (
                move.product_id.display_name,
                _dlm_fmt(move.dlm_qty_rejected),
                move.product_uom.name,
                reasons.get(move.dlm_reject_reason, _("chưa rõ")),
                note, anh))
        # sudo: xem lý do ở _dlm_create_vendor_return.
        if rows:
            self.sudo().message_post(
                body=Markup(_("Kết quả kiểm:<ul>%s</ul>"))
                % Markup("").join(rows))
        else:
            self.sudo().message_post(body=_("Kiểm đạt toàn bộ, đã cất vào kho."))

    # ── Điều hướng giữa các chặng chứng từ ───────────────────────────────────
    def _dlm_source_receipt(self):
        """Phiếu nhận [1] đứng trước phiếu này (phiếu kiểm nối bằng chuỗi move, phiếu trả bằng dlm_origin_picking_id); rỗng nếu tạo tay."""
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
        """Phiếu trả NCC của cả chặng nhận (neo vào phiếu NHẬN; tra được từ cả phiếu nhận lẫn kiểm)."""
        self.ensure_one()
        anchor = self._dlm_source_receipt() | self
        return self.search([("dlm_origin_picking_id", "in", anchor.ids)])

    def action_dlm_open_returns(self):
        """Phiếu nhận / phiếu kiểm → các phiếu trả NCC của chặng này."""
        self.ensure_one()
        returns = self._dlm_vendor_returns()
        if not returns:
            raise UserError(_("Chặng nhận hàng này chưa có phiếu trả nhà cung cấp nào."))
        name = (_("Phiếu trả nhà cung cấp %s") % returns.name if len(returns) == 1
                else _("Phiếu trả nhà cung cấp của %s") % self.name)
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

    # ── Preset chuyển kho ────────────────────────────────────────────────────
    # Là NÚT chứ không field lựa chọn: field nói dối ngay khi user sửa tay vị trí; nút chỉ điền một lần.
    # Preset "Gom phế liệu" đã gỡ — phế liệu nay khai ngay trên phiếu [8].
    def action_dlm_preset_to_workshop(self):
        """Vật tư ra xưởng: Kho nguyên vật liệu → Xưởng sản xuất."""
        return self._dlm_set_transfer_route(
            "dl_inventory.stock_location_nhan_kho",
            "dl_inventory.stock_location_xuong")

    # ── Bàn giao ra xưởng: hai chữ ký, hai người ─────────────────────────────
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
        # Cùng bộ lỗi với dải đỏ: bàn giao là điểm không quay lại về trách nhiệm.
        problems = self._dlm_confirm_problems()
        if problems:
            raise UserError(_("Chưa bàn giao được:\n%s") % "\n".join(
                "• %s" % p for p in problems))
        self.write({
            "dlm_handover_uid": self.env.user.id,
            "dlm_handover_date": fields.Datetime.now(),
        })
        # sudo: message_post nổ nếu hồ sơ user thiếu email; vết chữ ký vẫn phải ghi được.
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
        # Kiểm vai trò TRƯỚC: người sai vai phải nghe "chữ ký này của bên nhận", không phải "bạn vừa bàn giao".
        self._dlm_check_receipt_signer()
        # Admin/CEO nằm trong CẢ HAI bộ ký; chặn để họ không vừa bàn giao vừa tự ký nhận.
        if not self.env.su and self.dlm_handover_uid == self.env.user:
            raise UserError(_(
                "Bạn vừa là người bàn giao phiếu này. Người giao không ký nhận "
                "thay bên nhận được — nhờ %s mở phiếu và ký."
            ) % self.dlm_receiver_label)
        # sudo: Kỹ thuật chỉ ĐỌC phiếu kho; kiểm vai trò tường minh rồi nâng quyền (su đủ, không cần SUPERUSER).
        picking = self.sudo()
        # Ghi chữ ký TRƯỚC validate: guard button_validate đọc field này; validate nổ thì cuốn lại cả hai.
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
        """Chặn ký nhận ở SERVER, không tin groups trên nút; bộ ký phụ thuộc CHIỀU bàn giao (không thì người lập tự ký nhận được)."""
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

    # ── Hoá phế liệu: lối ra cho hàng lỗi không trả nữa ──────────────────────
    def _dlm_stuck_quants(self):
        """Tồn còn kẹt ở khu nguồn của phiếu trả — đọc QUANT (không đọc số dòng phiếu) để không hoá lại lô đã hoá ⇒ tồn âm."""
        self.ensure_one()
        if not self.location_id:
            return self.env["stock.quant"]
        return self.env["stock.quant"].sudo().search([
            ("location_id", "child_of", self.location_id.id),
            ("product_id", "in", self.move_ids.product_id.ids),
            ("quantity", ">", 0),
        ])

    def action_dlm_to_scrap(self):
        """Phiếu trả đã huỷ ⇒ dựng phiếu [9] cho hàng còn kẹt ở khu Chờ trả (kết cục thường gặp: NCC giảm trừ, mình giữ hàng lỗi)."""
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
        """Dựng phiếu [9] HAI DÒNG: hàng gốc rời sổ, phế liệu vào khu chờ bán (hai nửa trong 1 chứng từ để không quên nửa sau)."""
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

        # Số kg GỢI Ý, không phải số chốt: cân thật luôn thắng (chênh lệch là dữ liệu đối chiếu thu hồi).
        goi_y = sum(q.quantity * q.product_id.dlm_mass_per_unit for q in quants)

        # Bằng chứng kéo theo từ phiếu nguồn (nếu có); ghép theo MẶT HÀNG vì phiếu [9] dựng từ quant, không có mắt xích move→move.
        evidence_by_product = {}
        for move in (origin_picking or self.browse()).move_ids:
            if move.dlm_evidence_ids:
                evidence_by_product.setdefault(
                    move.product_id.id, set()).update(move.dlm_evidence_ids.ids)

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
                "dlm_evidence_ids": [(6, 0, sorted(
                    evidence_by_product.get(q.product_id.id, ())))],
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
        # Giữ chỗ ĐÚNG LÔ đang bỏ (tạo move line kèm lot_id thay vì để chiến lược chọn hộ).
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
        """Khoá nhu cầu về đúng SỐ CÂN ĐƯỢC + đánh dấu xong (không thì Odoo hỏi tạo phiếu bù vì '48 gợi ý ≠ 47 cân thật')."""
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
        # Đọc quantity (số THỰC làm được), không product_uom_qty (nhu cầu): số cân được mới là thứ vào kho.
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

    # ── Đối chiếu "BOM tính bao nhiêu / đã cấp bao nhiêu" ────────────────────
    def _dlm_bom_required_qty(self):
        """{vật tư: số theo định mức} của đơn gắn với phiếu (sudo đọc dl.bom, chỉ số lượng); nổ BOM location=None nên không bù trừ tồn BTP."""
        self.ensure_one()
        required = {}
        order = self.dlm_sale_order_id.sudo()
        if not order:
            return required
        for line in order.line_ids:
            bom = line.bom_id
            if not bom or not bom.product_qty:
                continue
            for material, qty in bom._dlm_explode_requirements(line.qty).items():
                required[material] = required.get(material, 0.0) + qty
        return required

    def _dlm_issued_qty(self):
        """{vật tư: số đã cấp ra xưởng cho đơn} — đếm move done vào Xưởng của phiếu cùng đơn, trừ chính phiếu này."""
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
        """Bảng HTML "định mức / đã cấp / phiếu này" — mối nối giữa Kho và định mức Kỹ thuật cho phiếu cấp vật tư."""
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
            # Dòng vượt nói bằng chữ (in giấy/mù màu vẫn đọc được).
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

    # ── Lưới chặn riêng của phiếu [8] Nhập kho từ xưởng ──────────────────────
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

        # Vật tư rời xưởng KHÔNG được vượt tồn thực ở Xưởng ⇒ tồn âm (Odoo không chặn tồn âm nội bộ, hỏng im lặng).
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

        # Hàng Hạng A không vào tồn nên ĐƠN là danh tính duy nhất; ghi mà không gắn đơn là ghi vào hư không.
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

    # ── Nhập thành phẩm (phiếu [8] NTP) ──────────────────────────────────────
    def _dlm_banner_fg_receipt(self):
        """Dải cho phiếu [8] Nhập thành phẩm (chỉ lo phần thay đổi; dải "không trừ vật tư" viết cố định trong view)."""
        if self.state == "done":
            return "success", _(
                "Đã ghi nhận mẻ hàng. Hàng làm xong đã vào kho, vật tư khai "
                "dùng đã rời sổ Xưởng."), False
        problems = self._dlm_confirm_problems()
        if problems:
            return self._dlm_banner_problems(
                problems, _("Chưa xác nhận phiếu được:"))
        # Nói rõ đang chờ AI, không để phiếu đứng im không lý do.
        if self.dlm_receipt_state == "waiting":
            return "info", _(
                "Xưởng đã bàn giao (%s). Đang chờ <b>Thủ kho</b> đếm thực tế "
                "và bấm \"Xác nhận đã nhận\" — hàng chưa vào sổ kho."
            ) % self.dlm_handover_uid.name, False
        # Hạng A ghi nhận được nhưng KHÔNG sinh tồn — nói ra để user không tưởng phiếu vô dụng.
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
        # Dòng hàng đã nhập trước khi bấm preset phải đi theo, không thì phiếu nói một đằng hàng chạy một nẻo.
        self.move_ids.write({
            "location_id": source.id,
            "location_dest_id": destination.id,
        })
        return True

    def _dlm_open_picking(self, picking, name):
        """Mở phiếu kho bằng ĐÚNG form Đại Linh (thiếu views là rơi về form gốc Odoo với nguyên bộ nút native)."""
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "views": [(picking._dlm_form_view().id, "form")],
            "name": name,
        }

    def _dlm_open_pickings(self, name, context=None):
        """Mở tập phiếu bằng cặp tree/form Đại Linh (một phiếu thì đi thẳng vào form)."""
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
