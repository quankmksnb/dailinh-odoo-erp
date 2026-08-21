# -*- coding: utf-8 -*-
"""Đơn mua hàng — một chứng từ cho cả vòng đời (nháp = đề nghị mua)."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

# Ai được thấy GIÁ MUA. Khác `_COST_GROUPS` của dl_sale (đó là quyền xem giá vốn báo giá).
_DLM_BUY_PRICE_GROUPS = (
    "dl_base.dl_group_purchasing,"
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin"
)

# Vai trò được TẠO/SỬA đơn mua. Thủ kho không có — kiểm soát chéo đặt hàng vs nhận hàng.
_DLM_BUYER_ROLES = (
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)

# Ngưỡng duyệt mặc định (đ): trên mức này đơn mua phải trình Giám đốc.
_DLM_DEFAULT_THRESHOLD = 20000000.0
_DLM_THRESHOLD_PARAM = "dl_purchase.approval_threshold"


class DlPurchaseOrder(models.Model):
    _name = "dl.purchase.order"
    _description = "Đơn mua hàng"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_order desc, id desc"

    name = fields.Char(
        string="Số đơn", required=True, copy=False, readonly=True,
        default="New", index=True)
    partner_id = fields.Many2one(
        "res.partner", string="Nhà cung cấp", required=True, tracking=True,
        domain=[("partner_role", "in", ("supplier", "both"))])
    date_order = fields.Date(
        string="Ngày lập", required=True, default=fields.Date.context_today,
        tracking=True)
    date_sent = fields.Datetime(
        string="Đã gửi hỏi giá lúc", readonly=True, copy=False,
        help="Mốc để trả lời \"gửi ba ngày rồi nhà cung cấp chưa báo giá\".")
    date_expected = fields.Date(
        string="Ngày hàng về dự kiến", tracking=True,
        help="Nhà cung cấp cam kết. Thiếu ô này thì màn điều phối không tính được "
             "\"đang về\" và đơn bán sẽ bị mua chồng.")
    state = fields.Selection([
        ("draft", "Nháp"),
        ("sent", "Đã gửi hỏi giá"),
        ("to_approve", "Chờ duyệt"),
        ("confirmed", "Đã chốt"),
        ("cancelled", "Đã huỷ"),
    ], string="Trạng thái", default="draft", tracking=True, copy=False)
    line_ids = fields.One2many(
        "dl.purchase.order.line", "order_id", string="Chi tiết", copy=True)
    note = fields.Text(string="Ghi chú cho nhà cung cấp")
    cancel_reason = fields.Text(string="Lý do huỷ", readonly=True, copy=False)
    company_id = fields.Many2one(
        "res.company", string="Công ty", readonly=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency", string="Tiền tệ",
        default=lambda self: self.env.company.currency_id)

    amount_total = fields.Float(
        string="Tổng tiền", compute="_compute_amount_total", store=True,
        digits="Product Price", groups=_DLM_BUY_PRICE_GROUPS)

    # M2M: một lần đặt thép có thể gom nhu cầu của NHIỀU đơn bán.
    dlm_origin_order_ids = fields.Many2many(
        "dl.sale.order", "dl_purchase_sale_order_rel",
        "purchase_id", "sale_id", string="Đơn bán đang chờ", readonly=True,
        help="Nhu cầu của những đơn bán này đã sinh ra đơn mua. Chỉ để NHÌN "
             "THẤY ai đang chờ — hàng về KHÔNG tự phân bổ theo danh sách này.")
    dlm_picking_ids = fields.One2many(
        "stock.picking", "dlm_purchase_order_id", string="Phiếu nhận hàng")
    dlm_picking_count = fields.Integer(
        string="Số phiếu nhận", compute="_compute_dlm_picking_count")
    dlm_receipt_state = fields.Selection([
        ("nothing", "Chưa nhận"),
        ("partial", "Nhận một phần"),
        ("done", "Đã nhận đủ"),
    ], string="Tình trạng nhận", compute="_compute_dlm_receipt", store=True,
        default="nothing",
        help="Suy từ phiếu nhận, KHÔNG phải một ô tick: nhà cung cấp giao ba lần thì có "
             "ba phiếu, và sự thật nằm ở đó.")
    dlm_receipt_hint = fields.Char(
        string="Chi tiết nhận thiếu", compute="_compute_dlm_receipt_hint",
        help="Liệt kê mặt hàng còn thiếu khi nhận dở dang — để dải cảnh báo trên "
             "đơn nói được CÒN THIẾU BAO NHIÊU, không chỉ 'nhận một phần'.")

    # Đường chốt/duyệt của một đơn hỏi giá chỉ mở khi báo giá nguồn đã thành đơn
    # bán (xem `_dlm_check_customer_committed`). View phải BIẾT điều đó, nếu không
    # nút [Chốt đơn] vẫn sáng rực trên đơn hỏi giá và bấm phát nào lỗi phát ấy —
    # nút sáng nhất màn hình mà luôn thất bại còn tệ hơn thiếu hẳn nút.
    #
    # 🔴 `compute_sudo`: Mua hàng KHÔNG có quyền đọc `dl.quotation` (cố ý — giá
    # bán không thuộc về họ), đọc thẳng sẽ ném AccessError ngay lúc mở form.
    dlm_customer_committed = fields.Boolean(
        string="Khách đã chốt đơn", compute="_compute_dlm_customer_committed",
        compute_sudo=True,
        help="Đơn không sinh từ báo giá thì luôn đúng — mua chủ động không chờ ai.")

    @api.depends("dlm_quotation_id.state")
    def _compute_dlm_customer_committed(self):
        for order in self:
            quo = order.dlm_quotation_id
            order.dlm_customer_committed = not quo or quo.state == "ordered"

    dlm_needs_approval = fields.Boolean(
        string="Vượt ngưỡng duyệt", compute="_compute_dlm_needs_approval")
    dlm_threshold_hint = fields.Char(
        string="Ngưỡng cần Giám đốc duyệt",
        compute="_compute_dlm_needs_approval",
        groups=_DLM_BUY_PRICE_GROUPS)
    dlm_price_warning = fields.Char(
        string="Cảnh báo giá", compute="_compute_dlm_price_warning",
        groups=_DLM_BUY_PRICE_GROUPS)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Số đơn mua đã tồn tại."),
    ]

    # ------------------------------------------------------------------
    # Tạo & tính toán
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "dl.purchase.order") or "New"
        return super().create(vals_list)

    @api.onchange("partner_id")
    def _onchange_dlm_partner_refresh_price(self):
        """Đổi nhà cung cấp ⇒ tính lại mốc giá của mọi dòng.

        Người mua hay thêm dòng TRƯỚC rồi mới chọn nhà cung cấp. Không có chỗ
        này thì đơn gửi Phú Thịnh vẫn mang nguyên giá Hoà Phát — sai cả chục
        lần, im lặng, rồi chốt xong nó đóng lên LÔ thành giá vốn thật."""
        if self.state not in ("draft", "sent"):
            return
        self.line_ids._dlm_fill_reference_price(force=True)

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped("price_subtotal"))

    # Tách khỏi `_compute_dlm_receipt`: không trộn field stored và non-stored trong một compute.
    @api.depends("dlm_picking_ids.state")
    def _compute_dlm_picking_count(self):
        for order in self:
            order.dlm_picking_count = len(order.dlm_picking_ids.filtered(
                lambda p: p.state != "cancel"))

    @api.depends("dlm_picking_ids.state", "dlm_picking_ids.move_ids.state",
                 "dlm_picking_ids.move_ids.quantity", "line_ids.qty")
    def _compute_dlm_receipt(self):
        for order in self:
            received = order._dlm_received_qty()
            if not any(received.values()):
                order.dlm_receipt_state = "nothing"
                continue
            order.dlm_receipt_state = (
                "done" if order._dlm_is_fully_received(received) else "partial")

    # Non-stored: chỉ để dựng câu cho dải cảnh báo, không ai lọc/sắp theo nó.
    @api.depends("dlm_receipt_state", "dlm_picking_ids.move_ids.quantity",
                 "line_ids.qty")
    def _compute_dlm_receipt_hint(self):
        for order in self:
            if order.dlm_receipt_state != "partial":
                order.dlm_receipt_hint = False
                continue
            received = order._dlm_received_qty()
            parts = []
            for product, qty in order._dlm_ordered_qty().items():
                got = received.get(product, 0.0)
                rounding = product.uom_id.rounding or 0.01
                if float_compare(got, qty, precision_rounding=rounding) < 0:
                    parts.append(_("%(name)s: đã nhận %(got)s/%(qty)s %(uom)s") % {
                        "name": product.display_name,
                        "got": _dlm_qty(got),
                        "qty": _dlm_qty(qty),
                        "uom": product.uom_id.name})
            order.dlm_receipt_hint = "; ".join(parts) or False

    def _dlm_received_qty(self):
        """{mặt hàng: số NCC đã giao} — đếm move đã hoàn tất, KHÔNG trừ phần bị loại ở bước kiểm."""
        self.ensure_one()
        received = {}
        for picking in self.dlm_picking_ids.filtered(
                lambda p: p.state != "cancel"):
            for move in picking.move_ids.filtered(lambda m: m.state == "done"):
                received[move.product_id] = (
                    received.get(move.product_id, 0.0) + move.quantity)
        return received

    def _dlm_is_fully_received(self, received):
        self.ensure_one()
        for product, qty in self._dlm_ordered_qty().items():
            rounding = product.uom_id.rounding or 0.01
            if float_compare(received.get(product, 0.0), qty,
                             precision_rounding=rounding) < 0:
                return False
        return True

    def _dlm_ordered_qty(self):
        """{mặt hàng: số đã đặt} — gộp vì một mặt hàng có thể ở nhiều dòng."""
        self.ensure_one()
        ordered = {}
        for line in self.line_ids:
            if not line.product_id:
                continue
            ordered[line.product_id] = (
                ordered.get(line.product_id, 0.0) + line.qty)
        return ordered

    @api.depends("amount_total")
    def _compute_dlm_needs_approval(self):
        threshold = self._dlm_approval_threshold()
        for order in self:
            order.dlm_needs_approval = order.amount_total > threshold
            # Chỉ con số: nhãn của field đã nói "Ngưỡng cần Giám đốc duyệt",
            # nhắc lại trong giá trị thì form đọc thành "Ngưỡng duyệt — Ngưỡng
            # cần Giám đốc duyệt: 20.000.000 đ".
            order.dlm_threshold_hint = _("%s đ") % _dlm_money(threshold)

    @api.model
    def _dlm_approval_threshold(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            _DLM_THRESHOLD_PARAM)
        try:
            return float(raw) if raw else _DLM_DEFAULT_THRESHOLD
        except (TypeError, ValueError):
            # Cấu hình gõ sai không được làm sập màn — rơi về mặc định và nói ra.
            return _DLM_DEFAULT_THRESHOLD

    @api.depends("line_ids.price_unit", "line_ids.price_list_unit")
    def _compute_dlm_price_warning(self):
        """Cảnh báo khi giá chốt lệch bảng giá NCC quá ngưỡng — chỉ NÓI RA, không tự sửa bảng giá."""
        limit = self._dlm_price_gap_limit()
        for order in self:
            lech = []
            for line in order.line_ids:
                base = line.price_list_unit
                if not base or not line.price_unit:
                    continue
                gap = (line.price_unit - base) / base
                if abs(gap) >= limit:
                    lech.append(_("%(name)s %(sign)s%(pct)s%%") % {
                        "name": line.product_id.display_name,
                        "sign": "+" if gap > 0 else "",
                        "pct": round(gap * 100)})
            order.dlm_price_warning = _(
                "Giá chốt lệch bảng giá nhà cung cấp: %s. Bảng giá đang nuôi giá chào "
                "khách — cân nhắc cập nhật."
            ) % ", ".join(lech) if lech else False

    @api.model
    def _dlm_price_gap_limit(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "dl_purchase.price_gap_limit")
        try:
            return float(raw) if raw else 0.10
        except (TypeError, ValueError):
            return 0.10

    # ------------------------------------------------------------------
    # Vòng đời
    # ------------------------------------------------------------------
    def action_dlm_send(self):
        """Nút [Gửi hỏi giá] trên đơn mua — đánh dấu đã gửi NCC và ghi mốc thời gian."""
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state != "draft":
            raise UserError(_("Chỉ đơn ở trạng thái Nháp mới gửi hỏi giá được."))
        self._dlm_check_lines()
        self.write({"state": "sent", "date_sent": fields.Datetime.now()})
        self.message_post(body=_("Đã gửi yêu cầu báo giá cho %s.")
                          % self.partner_id.display_name)
        return True

    def action_dlm_confirm(self):
        """Chốt giá cho lô hàng này ⇒ sinh phiếu nhận cho thủ kho."""
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state not in ("draft", "sent"):
            raise UserError(_("Đơn %s không ở trạng thái chốt được.") % self.name)
        self._dlm_check_confirmable()
        if self.dlm_needs_approval:
            # Nút [Chốt đơn] đã ẩn ở view; đây là lá chắn tầng server cho đường ghi khác.
            raise UserError(_(
                "Đơn %(name)s vượt ngưỡng duyệt. Bấm [Trình duyệt] để gửi "
                "Giám đốc.") % {"name": self.name})
        return self._dlm_do_confirm()

    def _dlm_do_confirm(self):
        self.ensure_one()
        self.state = "confirmed"
        picking = self._dlm_create_receipt()
        self.message_post(body=_(
            "Đã chốt đơn mua. Phiếu nhận hàng %s đã vào hàng đợi của thủ kho."
        ) % picking.name)
        self._dlm_sync_price_list()
        return picking._dlm_open_picking(picking, _("Phiếu nhận %s") % picking.name)

    # ------------------------------------------------------------------
    # Đơn HỎI GIÁ — sinh từ báo giá thiếu vật tư
    # ------------------------------------------------------------------
    dlm_quotation_id = fields.Many2one(
        "dl.quotation", string="Báo giá cần hỏi giá", readonly=True,
        index=True, copy=False, ondelete="set null",
        help="Đơn này sinh ra để hỏi giá cho một báo giá đang thiếu vật tư. "
             "Ghi nhận giá xong thì báo giá đó mới gửi khách được.")

    # Cuộc hỏi giá KHÔNG có nấc trạng thái riêng để kết thúc — nó cố ý nằm lại
    # `sent` vì chưa cam kết mua. Nhưng thế thì hàng đợi "Hỏi giá chờ trả lời"
    # không bao giờ vơi: đơn đã có giá vẫn nằm đó lẫn với đơn đang thật sự chờ
    # nhà cung cấp. Dấu này tách hai thứ đó ra mà không phải đẻ thêm trạng thái.
    dlm_vendor_replied_date = fields.Datetime(
        string="NCC đã báo giá lúc", readonly=True, copy=False, index=True,
        help="Đóng khi Mua hàng bấm [Ghi nhận giá NCC báo]. Đơn có dấu này rời "
             "hàng đợi chờ trả lời — vẫn tra được bằng bộ lọc trên chính màn đó, "
             "hoặc smart button “Đơn hỏi giá” trên báo giá.")

    def _dlm_open_orders(self, ten):
        """Mở danh sách/form các đơn này — dùng sau khi sinh đơn hỏi giá."""
        act = {
            "type": "ir.actions.act_window",
            "name": ten,
            "res_model": "dl.purchase.order",
            "target": "current",
        }
        if len(self) == 1:
            act.update(res_id=self.id, views=[(False, "form")], view_mode="form")
        else:
            act.update(domain=[("id", "in", self.ids)],
                       views=[(False, "list"), (False, "form")],
                       view_mode="list,form")
        return act

    def action_dlm_open_quotation(self):
        """Smart button: từ đơn hỏi giá nhìn ngược về báo giá đã sinh ra nó."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Báo giá %s") % self.dlm_quotation_id.name,
            "res_model": "dl.quotation",
            "res_id": self.dlm_quotation_id.id,
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "current",
        }

    def action_dlm_record_vendor_price(self):
        """Nút [Ghi nhận giá NCC báo] — mở modal chốt giá vừa hỏi được, KHÔNG chốt mua.

        🔴 Không dùng [Chốt đơn] để ghi giá hỏi: chốt đơn sinh phiếu nhận, tức
        là cam kết MUA THẬT. Hỏi giá cho một báo giá chưa chắc thắng mà đã đặt
        hàng là mua cho một đơn chưa tồn tại. Hai việc khác nhau, hai nút khác
        nhau — đơn vẫn nằm ở nấc "Đã gửi hỏi giá" chờ khách chốt.

        🔴 Cố ý KHÔNG đi qua `_dlm_sync_price_list` (luật ngưỡng lệch của lúc
        chốt đơn). Ngưỡng đó đúng cho [Chốt đơn]: tiền đã cam kết rồi, hỏi thêm
        một modal là phiền. Nhưng ở đường HỎI GIÁ nó phản tác dụng — lệch càng
        lớn thì càng rơi vào nhánh "chỉ lưu Nháp", tức là đúng ca cần nhất thì
        giá KHÔNG vào bảng, báo giá vẫn tính theo giá cũ mà cổng gửi khách vẫn
        mở (`_dlm_buy_price_moved` chỉ soi dòng đang áp dụng). Người dùng không
        thấy gì đổi nên bấm lại, mỗi lần bấm đẻ thêm một dòng Nháp y hệt.

        Modal bày giá cũ / giá mới / chênh lệch rồi mới ghi: chênh 1.233% là
        đúng ca con người phải nhìn, không phải ca hệ thống tự quyết."""
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state != "sent":
            raise UserError(_(
                "Chỉ ghi nhận giá trên đơn đang ở nấc “Đã gửi hỏi giá”."))
        chua = self.line_ids.filtered(lambda l: l.price_unit <= 0)
        if chua:
            raise UserError(_(
                "Chưa nhập giá cho: %s. Nhà cung cấp báo bao nhiêu thì điền vào "
                "cột Đơn giá chốt.") % ", ".join(chua.mapped("product_id.display_name")))
        return self._dlm_open_price_wizard(_("Ghi nhận giá nhà cung cấp báo"))

    def _dlm_after_price_recorded(self):
        """Modal ghi giá xong trên ĐƠN HỎI GIÁ ⇒ tính lại báo giá nguồn, mở cổng.

        Gọi từ wizard chứ không gọi ngay trong nút, vì phải chạy SAU khi giá đã
        thật sự vào bảng — `_dlm_stamp_price_confirmed` tính lại báo giá theo
        giá đang áp dụng, chạy trước thì nó tính lại theo giá cũ."""
        self.ensure_one()
        if self.state != "sent" or not self.dlm_quotation_id:
            return False
        self.dlm_quotation_id.sudo()._dlm_stamp_price_confirmed(self)
        self.dlm_vendor_replied_date = fields.Datetime.now()
        self.message_post(body=_(
            "Đã ghi nhận giá nhà cung cấp báo. Đơn rời hàng đợi chờ trả lời "
            "nhưng vẫn ở nấc “Đã gửi hỏi giá” — chưa cam kết mua."))
        return True

    # ------------------------------------------------------------------
    # Vòng giá: chốt đơn xong bảng giá tự theo
    # ------------------------------------------------------------------
    def _dlm_sync_price_list(self, wizard_lines=None):
        """Đưa giá vừa chốt vào bảng giá nhà cung cấp, theo NGƯỠNG LỆCH.

        Vì sao tự động: chốt đơn ĐÃ LÀ quyết định — Mua hàng tự gõ giá rồi bấm
        chốt, tức là đã cam kết tiền ở mức đó. Bắt bấm thêm một modal nữa là hỏi
        đúng một người, đúng một thông tin, đúng một thời điểm, hai lần.

        Vì sao KHÔNG tự động hết: giá một chuyến có thể cá biệt (mua gấp, mua lẻ,
        số lượng dưới mức sỉ). Để nó thành giá chào khách là lấy một chuyến hàng
        định giá cho cả doanh nghiệp — đúng thứ §6.6 cảnh báo.

        Nên chia theo mức lệch, dùng lại đúng ngưỡng đã có (`price_gap_limit`,
        mặc định 10%) vốn đang nuôi dải cảnh báo lệch giá:
          • giá y hệt          → không làm gì (không đẻ dòng rác)
          • lệch ≤ ngưỡng      → TỰ áp dụng: trôi giá thị trường bình thường
          • lệch > ngưỡng      → chỉ lưu lịch sử + báo Mua hàng xem lại
        """
        self.ensure_one()
        Row = self.env["product.supplierinfo"].sudo()
        limit = self._dlm_price_gap_limit()
        ap_dung, cho_xem = [], []
        for line in self.line_ids:
            if line.price_unit <= 0 or not line.product_id:
                continue
            hien = Row.search([
                ("product_tmpl_id", "=", line.product_id.product_tmpl_id.id),
                ("is_applied", "=", True)], limit=1)
            cu = hien.price if hien else 0.0
            if cu and float_compare(line.price_unit, cu, precision_digits=2) == 0:
                continue                      # giá không đổi ⇒ không có gì để cập nhật
            lech = abs(line.price_unit - cu) / cu if cu else 0.0
            # Chưa có giá nào đang áp dụng thì cứ áp: có giá còn hơn không có.
            tu_ap = (not cu) or lech <= limit
            row = self._dlm_upsert_price_row(line.product_id, line.price_unit)
            if tu_ap:
                row.sudo().action_approve()
                if not row.is_applied:
                    row.sudo().action_set_applied()
                ap_dung.append((line.product_id, cu, line.price_unit))
            else:
                cho_xem.append((line.product_id, cu, line.price_unit, lech))
        if ap_dung or cho_xem:
            self.message_post(body=self._dlm_sync_note(ap_dung, cho_xem, limit))
        return True

    def _dlm_upsert_price_row(self, product, price):
        """Ghi giá vào bảng giá NCC theo khoá ĐƠN MUA × MẶT HÀNG — có rồi thì SỬA.

        Một đơn mua là MỘT cuộc hỏi giá: cùng đơn, cùng mặt hàng thì chỉ có một
        con số. Trước đây mỗi lần ghi nhận là một `create` vô điều kiện, nên bấm
        lại lần hai (giá vẫn lệch quá ngưỡng nên lần nào cũng chỉ nằm Nháp) đẻ
        thêm một dòng y hệt: bảng giá thành danh sách bản sao của cùng một nhà
        cung cấp và không ai biết dòng nào là thật.

        Dòng của ĐƠN KHÁC thì tuyệt đối không đụng — đó là lịch sử giá thật, mỗi
        chuyến hàng một mốc."""
        self.ensure_one()
        Row = self.env["product.supplierinfo"].sudo()
        nguon = self._dlm_price_source_note()
        vals = {
            "partner_id": self.partner_id.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_id": product.id,
            "price": price,
            "date_start": fields.Date.context_today(self),
            "dlm_source_note": nguon,
        }
        row = Row.search([
            ("dlm_source_note", "=", nguon),
            ("partner_id", "=", self.partner_id.id),
            ("product_id", "=", product.id),
        ], limit=1)
        if not row:
            return Row.create(dict(vals, approval_state="draft"))
        row.write(vals)
        if row.is_applied:
            # Sửa giá trên dòng ĐANG áp dụng thì giá vốn tham chiếu phải theo:
            # đường approve/set_applied phía dưới sẽ không chạm vào nữa vì dòng
            # đã ở đúng trạng thái, nên gọi thẳng ở đây.
            row._dlm_apply()
        return row

    def _dlm_sync_note(self, ap_dung, cho_xem, limit):
        def tien(v):
            return "{:,.0f}".format(v or 0.0).replace(",", ".")
        phan = []
        if ap_dung:
            phan.append("<p><b>Bảng giá đã cập nhật</b> theo giá vừa chốt:</p><ul>%s</ul>"
                        % "".join("<li>%s: %s → <b>%s</b></li>" % (
                            p.display_name, tien(c) if c else "(chưa có)", tien(m))
                            for p, c, m in ap_dung))
        if cho_xem:
            phan.append(
                "<p>⚠️ <b>Lệch quá %d%% — KHÔNG tự áp dụng</b>, chỉ lưu vào bảng "
                "giá làm lịch sử. Chuyến mua gấp/mua lẻ thì để nguyên; nếu đây là "
                "mặt bằng giá mới thì vào Bảng giá Vật tư áp dụng tay:</p><ul>%s</ul>"
                % (round(limit * 100), "".join(
                    "<li>%s: %s → <b>%s</b> (%+.0f%%)</li>" % (
                        p.display_name, tien(c), tien(m), (m - c) / c * 100.0)
                    for p, c, m, _l in cho_xem)))
        return "".join(phan)

    def action_dlm_submit_approval(self):
        """Nút [Trình duyệt] — gửi đơn vượt ngưỡng vào hòm duyệt chung của Giám đốc."""
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state not in ("draft", "sent"):
            raise UserError(_("Đơn %s không ở trạng thái trình duyệt được.")
                            % self.name)
        self._dlm_check_confirmable()
        if not self.dlm_needs_approval:
            raise UserError(_(
                "Đơn %(name)s dưới ngưỡng %(limit)s đ — bấm [Chốt đơn], không "
                "cần Giám đốc duyệt.") % {
                    "name": self.name,
                    "limit": _dlm_money(self._dlm_approval_threshold())})
        self.env["dl.pricing.approval.request"].sudo()._open_for(
            "purchase_over_threshold", self,
            old_value="",
            new_value=_("%s đ") % _dlm_money(self.amount_total),
            impact=_("Chi mua hàng cho %s") % self.partner_id.display_name,
            reason=_("Đơn mua %(name)s vượt ngưỡng %(limit)s đ.") % {
                "name": self.name,
                "limit": _dlm_money(self._dlm_approval_threshold())})
        self.state = "to_approve"
        return True

    def _on_approval_approved(self, request):
        """Giám đốc duyệt trong hòm duyệt ⇒ đơn tự chốt và sinh phiếu nhận."""
        self.ensure_one()
        if self.state != "to_approve":
            return True
        self.sudo()._dlm_do_confirm()
        return True

    def _on_approval_rejected(self, request):
        """Giám đốc từ chối ⇒ đơn về lại "Đã gửi hỏi giá" (không về Nháp, giữ mốc đã gửi)."""
        self.ensure_one()
        if self.state != "to_approve":
            return True
        self.sudo().state = "sent" if self.date_sent else "draft"
        return True

    def action_dlm_cancel(self):
        """Nút [Huỷ đơn] — chặn cứng nếu đã có phiếu nhận hoàn tất (hàng đã vào kho)."""
        self.ensure_one()
        self._dlm_check_buyer()
        done = self.dlm_picking_ids.filtered(lambda p: p.state == "done")
        if done:
            raise UserError(_(
                "Không huỷ được đơn %(name)s: đã có phiếu nhận hoàn tất "
                "(%(pickings)s). Hàng đã vào kho — muốn trả lại thì đi đường "
                "phiếu Trả hàng nhà cung cấp."
            ) % {"name": self.name,
                 "pickings": ", ".join(done.mapped("name"))})
        open_pickings = self.dlm_picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel"))
        open_pickings.action_cancel()
        self.state = "cancelled"
        self.message_post(body=_("Đã huỷ đơn mua.%s") % (
            _(" Đã huỷ kèm %s phiếu nhận chưa xác nhận.") % len(open_pickings)
            if open_pickings else ""))
        return True

    def action_dlm_reset_draft(self):
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state not in ("sent", "cancelled"):
            raise UserError(_(
                "Chỉ đưa về Nháp được từ \"Đã gửi hỏi giá\" hoặc \"Đã huỷ\"."))
        self.state = "draft"
        return True

    # ------------------------------------------------------------------
    # Lá chắn
    # ------------------------------------------------------------------
    def _dlm_check_buyer(self):
        self.ensure_one()
        if not self.env.su and not any(
                self.env.user.has_group(role) for role in _DLM_BUYER_ROLES):
            raise UserError(_(
                "Đơn mua hàng là việc của bộ phận Mua hàng. Thủ kho nhận hàng "
                "theo đơn nhưng không đặt hàng — đó là kiểm soát chéo, không "
                "phải hạn chế."))
        return True

    def _dlm_check_lines(self):
        """Kiểm dòng hợp lệ trước khi gửi NCC (có dòng, số lượng > 0, không phải phế liệu)."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_(
                "Đơn %s chưa có dòng nào — không gửi nhà cung cấp một tờ giấy trắng.")
                % self.name)
        zero = self.line_ids.filtered(lambda l: l.qty <= 0)
        if zero:
            raise UserError(_("Dòng có số lượng 0: %s.") % ", ".join(
                dict.fromkeys(zero.mapped("product_id.display_name"))))
        scrap = self.line_ids.filtered(lambda l: l.product_id.dlm_is_scrap)
        if scrap:
            raise UserError(_(
                "Không đặt mua phế liệu: %s. Phế liệu là thứ Đại Linh BÁN đi, "
                "không phải nguyên liệu đầu vào.") % ", ".join(
                    dict.fromkeys(scrap.mapped("product_id.display_name"))))
        return True

    def _dlm_check_customer_committed(self):
        """Đơn sinh từ báo giá chỉ được chốt mua khi báo giá đó đã thành đơn bán.

        Đơn hỏi giá là một CUỘC HỎI, không phải một cam kết. Chốt nó lúc báo giá
        còn Nháp là bỏ tiền mua vật tư cho một đơn hàng chưa tồn tại — khách quay
        xe thì thép nằm trong kho không ai trả tiền. Trước đây không có cổng nào:
        nút [Chốt đơn] hiện y hệt nút của đơn mua thật.

        Chỉ chặn đơn có `dlm_quotation_id`. Mua chủ động (nhập thép về sẵn) không
        đi qua đây, và không nên bị luật này ràng."""
        self.ensure_one()
        quo = self.dlm_quotation_id.sudo()
        if not quo or quo.state == "ordered":
            return True
        nhan = dict(
            quo._fields["state"]._description_selection(self.env)
        ).get(quo.state, quo.state)
        raise UserError(_(
            "Báo giá %(bg)s chưa thành đơn bán (đang ở “%(tt)s”), nên chưa "
            "được chốt mua cho nó — đây mới là một cuộc hỏi giá.\n\n"
            "Khách đồng ý và báo giá lên đơn xong, Thủ kho điều phối thấy kho "
            "thiếu hàng thì đơn mua sẽ tự vào hàng đợi của bạn."
        ) % {"bg": quo.name, "tt": nhan})

    def _dlm_check_confirmable(self):
        """Kiểm điều kiện chốt giá: đủ giá, có ngày hàng về, không trùng mặt hàng."""
        self.ensure_one()
        self._dlm_check_lines()
        self._dlm_check_customer_committed()
        no_price = self.line_ids.filtered(lambda l: l.price_unit <= 0)
        if no_price:
            raise UserError(_(
                "Chưa có giá cho: %s.\n\nChốt đơn mà dòng còn giá 0 thì lô hàng "
                "nhập về mang giá 0 — giá vốn thực tế của mọi đơn bán dùng lô "
                "đó sai vĩnh viễn."
            ) % ", ".join(dict.fromkeys(
                no_price.mapped("product_id.display_name"))))
        if not self.date_expected:
            raise UserError(_(
                "Chưa có Ngày hàng về dự kiến. Thiếu nó thì màn Điều phối không "
                "tính được \"đang về\" và đơn bán sẽ bị mua chồng."))
        seen, trung = set(), []
        for line in self.line_ids:
            if line.product_id.id in seen:
                trung.append(line.product_id.display_name)
            seen.add(line.product_id.id)
        if trung:
            raise UserError(_(
                "Mặt hàng bị khai hai dòng: %s.\n\nGộp lại thành một dòng — hai "
                "giá khác nhau cho cùng một mặt hàng thì lúc nhận không biết "
                "đóng giá nào lên lô."
            ) % ", ".join(dict.fromkeys(trung)))
        return True

    # ------------------------------------------------------------------
    # Nối vào Kho
    # ------------------------------------------------------------------
    def _dlm_create_receipt(self):
        """Sinh phiếu [1] Nhận hàng NCC cho thủ kho — từ đây luồng kiểm hàng chạy như cũ."""
        self.ensure_one()
        warehouse = self.env["stock.warehouse"]._dlm_main_warehouse()
        picking_type = warehouse.in_type_id
        source = self.env.ref("stock.stock_location_suppliers")
        destination = picking_type.default_location_dest_id
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": self.name,
            "dlm_purchase_order_id": self.id,
            "scheduled_date": self.date_expected or fields.Date.today(),
            "move_ids": [(0, 0, {
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom": line.product_id.uom_id.id,
                "product_uom_qty": line.qty,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }) for line in self.line_ids],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    # ------------------------------------------------------------------
    # Vòng giá: giá chốt THẬT quay về bảng giá nhà cung cấp
    # ------------------------------------------------------------------
    dlm_price_row_count = fields.Integer(
        string="Dòng bảng giá đã tạo", compute="_compute_dlm_price_row_count")

    def _compute_dlm_price_row_count(self):
        Row = self.env["product.supplierinfo"].sudo()
        for order in self:
            order.dlm_price_row_count = Row.search_count([
                ("dlm_source_note", "=", order._dlm_price_source_note()),
            ]) if order.id else 0

    def _dlm_price_source_note(self):
        self.ensure_one()
        return "PO:%s" % self.name

    def action_dlm_push_price_list(self):
        """Nút [Cập nhật bảng giá] — mở modal chốt giá vừa mua thành giá hiện hành.

        Đây là mối nối cuối cùng của vòng giá: trước đó Mua hàng chốt 275.000 với
        nhà cung cấp thì phải TỰ NHỚ sang màn Bảng giá gõ lại; quên thì mọi báo
        giá vẫn chạy giá cũ mãi mà không gì nổ ra.

        Một bước, không đẻ dòng nháp bắt sang màn khác duyệt: người duyệt bảng
        giá cũng chính là nhóm Mua hàng (`_check_price_manager`), nên tách ra chỉ
        là tự duyệt chính mình — thêm thao tác, không thêm kiểm soát. Modal bày
        giá cũ / giá mới / chênh lệch / số lượng chuyến trước khi ghi, nên vẫn là
        một quyết định có ý thức chứ không phải ghi ngược âm thầm (§6.6)."""
        self.ensure_one()
        self._dlm_check_buyer()
        if self.state != "confirmed":
            raise UserError(_(
                "Chỉ cập nhật giá từ đơn mua ĐÃ CHỐT — giá chưa chốt thì chưa "
                "phải giá thật."))
        return self._dlm_open_price_wizard(_("Cập nhật bảng giá nhà cung cấp"))

    def _dlm_open_price_wizard(self, ten):
        """Dựng modal đối chiếu giá cũ / giá mới cho đơn này rồi mở ra.

        Dùng chung cho hai cửa vào — [Cập nhật bảng giá] (đơn đã chốt) và
        [Ghi nhận giá NCC báo] (đơn hỏi giá). Cùng một câu hỏi đặt cho cùng một
        người: giá này có thành giá chào khách không."""
        self.ensure_one()
        Row = self.env["product.supplierinfo"].sudo()
        dong = []
        for line in self.line_ids:
            if line.price_unit <= 0 or not line.product_id:
                continue
            hien_hanh = Row.search([
                ("product_tmpl_id", "=", line.product_id.product_tmpl_id.id),
                ("is_applied", "=", True),
            ], limit=1)
            cu = hien_hanh.price if hien_hanh else 0.0
            dong.append((0, 0, {
                "product_id": line.product_id.id,
                "qty": line.qty,
                "old_price": cu,
                "new_price": line.price_unit,
                "gap_pct": ((line.price_unit - cu) / cu * 100.0) if cu else 0.0,
                # Giá y hệt giá đang áp dụng thì không có gì để cập nhật — bỏ
                # tick sẵn để người dùng khỏi phải tự nhìn ra.
                "selected": float_compare(line.price_unit, cu,
                                          precision_digits=2) != 0,
            }))
        if not dong:
            raise UserError(_(
                "Đơn này không có dòng nào có giá để cập nhật bảng giá."))
        wizard = self.env["dl.purchase.price.update.wizard"].create({
            "order_id": self.id, "line_ids": dong})
        return {
            "type": "ir.actions.act_window",
            "name": ten,
            "res_model": "dl.purchase.price.update.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_dlm_open_price_rows(self):
        """Smart button: mở các dòng bảng giá sinh từ đơn mua này."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bảng giá tạo từ %s") % self.name,
            "res_model": "product.supplierinfo",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "domain": [("dlm_source_note", "=", self._dlm_price_source_note())],
            "target": "current",
        }

    def action_dlm_open_pickings(self):
        self.ensure_one()
        if not self.dlm_picking_ids:
            raise UserError(_("Đơn %s chưa có phiếu nhận nào.") % self.name)
        return self.dlm_picking_ids._dlm_open_pickings(
            _("Phiếu nhận của %s") % self.name)


class DlPurchaseOrderLine(models.Model):
    _name = "dl.purchase.order.line"
    _description = "Dòng đơn mua hàng"

    order_id = fields.Many2one(
        "dl.purchase.order", string="Đơn mua", required=True,
        ondelete="cascade", index=True)
    product_id = fields.Many2one(
        "product.product", string="Mặt hàng", required=True,
        # Chỉ hai loại Đại Linh MUA (vật tư, hàng thương mại) — BTP/hàng gia công là tự làm.
        domain=[("product_kind", "in", ("material", "trading")),
                ("dlm_is_scrap", "=", False),
                ("dlm_lifecycle_state", "!=", "obsolete")])
    qty = fields.Float(
        string="Số lượng", default=1.0, digits="Product Unit of Measure")
    # ĐVT related readonly: đơn vị tính tiền = đơn vị mua của vật tư (Cây/Tấm/Cái/kg).
    uom_id = fields.Many2one(
        "uom.uom", string="Đơn vị tính", related="product_id.uom_id", readonly=True)
    price_unit = fields.Float(
        string="Đơn giá chốt", digits="Product Price",
        groups=_DLM_BUY_PRICE_GROUPS,
        help="Giá của CHUYẾN HÀNG NÀY. Không tự ghi ngược vào Bảng giá nhà cung cấp.")
    price_list_unit = fields.Float(
        string="Giá bảng nhà cung cấp", digits="Product Price", readonly=True,
        groups=_DLM_BUY_PRICE_GROUPS,
        help="Giá đang áp dụng lúc lập đơn — để so lệch, không dùng để tính tiền.")
    price_subtotal = fields.Float(
        string="Thành tiền", compute="_compute_price_subtotal", store=True,
        digits="Product Price", groups=_DLM_BUY_PRICE_GROUPS)
    qty_received = fields.Float(
        string="Đã nhận", compute="_compute_qty_received",
        digits="Product Unit of Measure")

    @api.depends("qty", "price_unit")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit

    @api.depends("order_id.dlm_picking_ids.move_ids.state",
                 "order_id.dlm_picking_ids.move_ids.quantity")
    def _compute_qty_received(self):
        for line in self:
            received = line.order_id._dlm_received_qty()
            line.qty_received = received.get(line.product_id, 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        """Điền mốc giá ngay lúc tạo dòng — onchange KHÔNG đủ, xem
        `_dlm_fill_reference_price`."""
        lines = super().create(vals_list)
        lines._dlm_fill_reference_price()
        return lines

    @api.onchange("product_id")
    def _onchange_product_id(self):
        """Chọn mặt hàng ⇒ điền sẵn giá gợi ý từ bảng giá NCC (không phải giá chốt)."""
        self._dlm_fill_reference_price(force=True)

    def _dlm_fill_reference_price(self, force=False):
        """Điền "Giá bảng nhà cung cấp", và cả giá chốt nếu người mua chưa gõ tay.

        🔴 Phải làm ở TẦNG SERVER chứ không chỉ trong onchange: `price_list_unit`
        khai `readonly` nên client KHÔNG gửi nó lên lúc lưu — con số onchange vừa
        điền biến mất sạch, cột hiện 0 đ. Và vì `_compute_dlm_price_warning` lấy
        đúng ô đó làm mốc, mốc bằng 0 làm cả dải cảnh báo lệch giá im lặng: đơn
        chốt lệch bao nhiêu cũng không có gì nổ ra."""
        for line in self:
            if not line.product_id or (line.price_list_unit and not force):
                continue
            cu = line.price_list_unit
            moc = line._dlm_reference_price()
            line.price_list_unit = moc
            # 🔴 Đơn HỎI GIÁ thì DỪNG ở đây: chỉ điền mốc để so, tuyệt đối
            # không điền giá chốt. Điền vào là Mua hàng mở đơn ra đã thấy sẵn
            # một con số, bấm [Ghi nhận giá NCC báo] là đóng dấu GIÁ CŨ như thể
            # nhà cung cấp vừa báo — đúng thứ cả luồng hỏi giá sinh ra để chống.
            # Giá trên đơn hỏi giá phải là chữ người mua gõ vào sau khi hỏi thật.
            if line.order_id.dlm_quotation_id:
                continue
            # Chỉ đè giá chốt khi người mua CHƯA gõ tay — dấu hiệu nhận biết là
            # nó vẫn đúng bằng mốc cũ (hoặc chưa có gì). Gõ tay rồi mà bị đè là
            # mất con số họ vừa thoả thuận với nhà cung cấp.
            if not line.price_unit or line.price_unit == cu:
                line.price_unit = moc

    def _dlm_reference_price(self):
        self.ensure_one()
        seller = self._dlm_reference_seller()
        if not seller:
            return self.product_id.standard_price
        try:
            return seller._dlm_reference_unit_cost(self.product_id)
        except UserError:
            # Bảng giá lệch ĐVT/tiền tệ thì raise; ở đây chỉ là gợi ý nên rơi về
            # giá vốn tham chiếu thay vì làm hỏng cả form.
            return self.product_id.standard_price

    def _dlm_reference_seller(self):
        """Bảng giá làm mốc cho dòng này — giá của CHÍNH nhà cung cấp trên đơn.

        🔴 Trước đây chỉ soi dòng ĐANG ÁP DỤNG. Mà mỗi vật tư chỉ có đúng MỘT
        dòng như thế, thường là của nhà cung cấp khác — nên đặt hàng Phú Thịnh
        lại lấy mốc là giá Hoà Phát, lệch mấy lần mà không cảnh báo nào nổ.

        Cột này tên là "Giá bảng nhà cung cấp" và sinh ra để SO LỆCH, nên nó phải
        là giá của người mình đang đặt: đang áp dụng trước, không thì bản mới
        nhất họ đã báo. Họ chưa có giá nào thì mới rơi về giá đang áp dụng —
        mặt bằng chung còn hơn không có mốc nào."""
        self.ensure_one()
        rows = self.product_id.sudo().seller_ids
        today = fields.Date.context_today(self)
        cua_ho = rows.filtered(
            lambda s: s.partner_id == self.order_id.partner_id
            and s.approval_state == "approved"
            and not s.dlm_superseded
            and s._is_valid_on(today))
        if cua_ho:
            return (cua_ho.filtered("is_applied")
                    or cua_ho.sorted("date_start", reverse=True))[:1]
        return rows.filtered("is_applied")[:1]


def _dlm_money(value):
    """Tiền cho câu thông báo: nhóm hàng nghìn bằng dấu chấm, không lẻ."""
    return "{:,.0f}".format(value or 0.0).replace(",", ".")


def _dlm_qty(value):
    """Số lượng cho câu thông báo: bỏ đuôi 0 thừa (30 chứ không 30,000)."""
    return ("%.3f" % (value or 0.0)).rstrip("0").rstrip(".") or "0"
