# -*- coding: utf-8 -*-
"""K19/K21 — Đơn mua hàng.

Thiết kế: ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §5, §7.

MỘT chứng từ cho cả vòng đời (người dùng chốt 2026-08-14, U-2). Nháp chính là
"đề nghị mua" — thêm một model nữa là thêm một bước bấm và một màn để quên, cho
một doanh nghiệp mà Mua hàng ngồi cách Kho mười mét.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

# Ai được thấy GIÁ MUA. 🔴 Cố ý KHÁC `_COST_GROUPS` của dl_sale (ceo/admin/
# accountant/sales_manager): đó là quyền xem GIÁ VỐN trong báo giá. Ở đây là giá
# ta trả cho NCC — Mua hàng sở hữu nó, còn Trưởng KD không có việc gì với nó.
# Đây là hai khái niệm khác nhau tình cờ cùng hình dạng; gộp lại là mở quyền cho
# một vai mà không ai định mở.
_DLM_BUY_PRICE_GROUPS = (
    "dl_base.dl_group_purchasing,"
    "dl_base.dl_group_ceo,"
    "dl_base.dl_group_admin,"
    "dl_base.dl_group_accountant"
)

# Vai trò được TẠO/SỬA đơn mua. Thủ kho cố ý không có: kiểm soát chéo giữa người
# đặt hàng và người nhận hàng là lý do tồn tại của hai vai trò tách nhau
# (cùng nguyên tắc RS-03 — thủ kho không xác nhận được phiếu trả NCC).
_DLM_BUYER_ROLES = (
    "dl_base.dl_group_purchasing",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)

# Ngưỡng duyệt mặc định (đ). Người dùng chốt "duyệt theo ngưỡng tiền" (U-3);
# con số cụ thể còn để ngỏ — xem §15 câu 1 của doc.
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

    # 🔴 M2M chứ không M2O: một lần đặt thép hay gom nhu cầu của NHIỀU đơn bán.
    # Ép về một đơn là mất dấu các đơn còn lại, và khi hàng về không ai trả lời
    # được "đang có những đơn nào chờ cái này".
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

    dlm_needs_approval = fields.Boolean(
        string="Vượt ngưỡng duyệt", compute="_compute_dlm_needs_approval")
    dlm_threshold_hint = fields.Char(
        string="Ngưỡng duyệt", compute="_compute_dlm_needs_approval",
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

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(order.line_ids.mapped("price_subtotal"))

    # ⚠️ Tách khỏi `_compute_dlm_receipt`: Odoo cảnh báo (đúng) khi một hàm
    # compute vừa tính field STORED vừa tính field non-stored — đọc field không
    # lưu sẽ âm thầm ghi lại field lưu.
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

    def _dlm_received_qty(self):
        """{mặt hàng: số NCC đã giao}.

        Đếm move ĐÃ hoàn tất trên phiếu nhận. Cố ý KHÔNG trừ phần bị loại ở bước
        kiểm: câu hỏi của đơn mua là "NCC đã giao đủ chưa", còn "hàng có đạt
        không" là câu hỏi của phiếu Trả hàng NCC — trộn hai câu vào một con số
        thì không trả lời được câu nào.
        """
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
            order.dlm_threshold_hint = _(
                "Ngưỡng cần Giám đốc duyệt: %s đ") % _dlm_money(threshold)

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
        """MH-13 — giá chốt lệch bảng giá NCC quá ngưỡng thì NÓI RA.

        Không tự sửa bảng giá: bảng giá đang nuôi giá chào khách, đổi nó là một
        quyết định kinh doanh chứ không phải một `write()`.
        """
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
        """Đánh dấu ĐÃ gửi yêu cầu báo giá cho NCC — ghi MỐC THỜI GIAN.

        Tách khỏi việc gửi: gửi bằng [Gửi mail cho NCC] (``action_dlm_email``,
        có từ khi SMTP được khai trong ``odoo.conf``) hay bằng Zalo/mail tay thì
        mốc vẫn phải nằm trong hệ thống, không thì không ai trả lời được "gửi
        lâu chưa". Nút mail CỐ Ý không tự bật mốc này: trình soạn thư gửi ở một
        bước sau, đóng cửa sổ là thư không đi.
        """
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
            # MH-07 — nút [Chốt đơn] đã ẩn ở view; đây là lá chắn tầng server
            # cho mọi đường ghi khác (RPC, import, test).
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
        return picking._dlm_open_picking(picking, _("Phiếu nhận %s") % picking.name)

    def action_dlm_submit_approval(self):
        """MH-07 — trình Giám đốc. Dùng lại HÒM DUYỆT sẵn có.

        `dl.pricing.approval.request` vốn đã generic (`res_model`/`res_id` +
        hook `_on_approval_approved`), nên CEO có MỘT hòm cho cả báo giá lẫn đơn
        mua. Dựng hòm thứ hai là bắt người duyệt nhớ có hai chỗ phải xem.
        """
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
        """Bị từ chối ⇒ về lại "Đã gửi hỏi giá" để Mua hàng thương lượng lại.

        KHÔNG về Nháp: đơn đã gửi NCC rồi, quay về Nháp là xoá mất mốc đó.
        """
        self.ensure_one()
        if self.state != "to_approve":
            return True
        self.sudo().state = "sent" if self.date_sent else "draft"
        return True

    def action_dlm_cancel(self):
        """MH-10/11 — huỷ đơn.

        Đã có phiếu nhận ĐÃ xác nhận ⇒ chặn cứng: hàng nằm trong kho mà chứng từ
        mua biến mất là một lỗ hổng đối soát, không phải một thao tác.
        """
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
        """MH-01→04 — những thứ phải đúng trước khi tờ giấy đi ra khỏi công ty."""
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

    def _dlm_check_confirmable(self):
        """MH-05/06/12 — điều kiện chốt giá."""
        self.ensure_one()
        self._dlm_check_lines()
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
        """Phiếu [1] Nhận hàng NCC — từ đây LUỒNG CŨ chạy nguyên.

        Không sửa gì trong luồng QC: hàng vẫn phải qua kiểm, vẫn tách Đạt/Loại,
        vẫn sinh phiếu trả NCC nháp khi có hàng loại.
        """
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
        # Chỉ hai loại Đại Linh MUA. Bán thành phẩm và hàng gia công là do mình
        # làm ra — đặt NCC làm hộ là một nghiệp vụ khác (thầu phụ), chưa có.
        domain=[("product_kind", "in", ("material", "trading")),
                ("dlm_is_scrap", "=", False),
                ("dlm_lifecycle_state", "!=", "obsolete")])
    qty = fields.Float(
        string="Số lượng", default=1.0, digits="Product Unit of Measure")
    # 🔴 ĐVT là RELATED READONLY: quyết định Q1 của doc dữ liệu doanh nghiệp —
    # đơn vị tính tiền = đơn vị mua của chính vật tư (Cây/Tấm/Cái/kg). NCC báo
    # đ/kg cho thép khai theo Cây thì quy đổi MỘT LẦN lúc nhập giá, không phải
    # đổi ĐVT của dòng.
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

    @api.onchange("product_id")
    def _onchange_product_id(self):
        """Điền sẵn giá từ bảng giá NCC đang áp dụng — GỢI Ý, không phải giá chốt.

        Lấy đúng NCC của đơn nếu họ có bảng giá; không thì lấy bảng giá đang áp
        dụng của mặt hàng để Mua hàng có mốc so.
        """
        for line in self:
            if not line.product_id:
                continue
            seller = line._dlm_reference_seller()
            try:
                base = seller._dlm_reference_unit_cost(line.product_id) \
                    if seller else line.product_id.standard_price
            except UserError:
                # Bảng giá khai lệch tiền tệ/ĐVT thì `_dlm_reference_unit_cost`
                # raise (đúng — nó là cổng chặn ÁP DỤNG giá). Nhưng ở đây nó chỉ
                # là GỢI Ý: nổ lỗi là chặn Mua hàng thêm dòng vì một bản ghi
                # không liên quan. Rơi về giá vốn tham chiếu và để họ tự gõ.
                base = line.product_id.standard_price
            line.price_list_unit = base
            if not line.price_unit:
                line.price_unit = base

    def _dlm_reference_seller(self):
        """Bảng giá NCC dùng làm mốc — ưu tiên chính NCC của đơn."""
        self.ensure_one()
        sellers = self.product_id.sudo().seller_ids.filtered(
            lambda s: s.is_applied)
        own = sellers.filtered(
            lambda s: s.partner_id == self.order_id.partner_id)
        return (own or sellers)[:1]


def _dlm_money(value):
    """Tiền cho câu thông báo: nhóm hàng nghìn bằng dấu chấm, không lẻ."""
    return "{:,.0f}".format(value or 0.0).replace(",", ".")
