# -*- coding: utf-8 -*-
"""K6 — Mối nối đơn bán hàng ↔ phiếu giao hàng.

Thiết kế: ``docs/Thiet_ke_phan_he_kho.md`` §9.1, §11.6.

Phiếu giao KHÔNG tự sinh khi chốt đơn. Hàng gia công chưa tồn tại lúc chốt đơn —
phiếu giao sinh ra sẽ treo mãi ở trạng thái chờ, và hàng đợi của thủ kho đầy
những việc chưa làm được. Để NÚT BẤM: ai đó phải quyết định "hàng đã sẵn sàng".

🔴 **K13 (2026-08-13) — ĐẢO quyết định của K6: dòng ``consu`` PHẢI lên phiếu
giao.** Bản K6 loại chúng ra vì _"không có tồn nên chỉ tạo dòng vĩnh viễn không
giữ chỗ được"_. Lý do đó **sai về kỹ thuật**: Odoo
``_should_bypass_reservation()`` trả True cho SP không storable, nên dòng
``consu`` nhảy thẳng sang ``assigned`` và validate bình thường — nó không bao
giờ treo. Còn cái giá thì rất thật: đơn Hạng A — loại đơn phổ biến NHẤT của Đại
Linh — không có chứng từ giao hàng nào, không có gì cho khách ký, và
``dlm_delivery_state`` đứng yên "Chưa giao" kể cả khi hàng đã lên xe.

Nay chỉ **dịch vụ** bị loại. Giữ chỗ và trừ tồn vẫn chỉ áp cho dòng storable —
đó là việc của Odoo, không phải của luật ở đây.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

# Vai trò được phép yêu cầu giao hàng. Thủ kho là người giao; Sales/Trưởng KD là
# người biết khách đã sẵn sàng nhận. Cả hai đều bấm được nút này.
_DLM_DELIVERY_ROLES = (
    "dl_base.dl_group_warehouse",
    "dl_base.dl_group_ba",
    "dl_base.dl_group_sales_manager",
    "dl_base.dl_group_ceo",
    "dl_base.dl_group_admin",
)


class DlSaleOrder(models.Model):
    _inherit = "dl.sale.order"

    dlm_picking_ids = fields.One2many(
        "stock.picking", "dlm_sale_order_id", string="Phiếu giao hàng")
    dlm_picking_count = fields.Integer(
        string="Số phiếu giao", compute="_compute_dlm_picking_count")
    dlm_delivery_state = fields.Selection([
        ("nothing", "Chưa giao"),
        ("partial", "Giao một phần"),
        ("done", "Đã giao đủ"),
    ], string="Tình trạng giao hàng", compute="_compute_dlm_delivery_state",
        store=True, default="nothing")
    # Không có dòng nào cần giao qua kho (đơn toàn SP dùng chung Hạng A) — nút
    # Tạo phiếu giao phải ẩn hẳn thay vì để người dùng bấm rồi ăn lỗi.
    dlm_has_deliverable = fields.Boolean(
        string="Có hàng cần giao qua kho",
        compute="_compute_dlm_delivery_state", store=True)

    @api.depends("dlm_picking_ids", "dlm_picking_ids.picking_type_id")
    def _compute_dlm_picking_count(self):
        for order in self:
            order.dlm_picking_count = len(order._dlm_delivery_pickings())

    @api.depends("line_ids.qty", "line_ids.product_id",
                 "line_ids.product_id.detailed_type",
                 "dlm_picking_ids.picking_type_id",
                 "dlm_picking_ids.state", "dlm_picking_ids.move_ids.state",
                 "dlm_picking_ids.move_ids.quantity")
    def _compute_dlm_delivery_state(self):
        for order in self:
            needed = order._dlm_needed_qty()
            order.dlm_has_deliverable = bool(needed)
            if not needed:
                order.dlm_delivery_state = "nothing"
                continue
            delivered = order._dlm_delivered_qty()
            if not any(delivered.values()):
                order.dlm_delivery_state = "nothing"
                continue
            order.dlm_delivery_state = (
                "done" if order._dlm_is_fully_delivered(needed, delivered)
                else "partial")

    # ── Số lượng: cần giao / đã giao / còn lại ───────────────────────────────
    def _dlm_deliverable_lines(self):
        """Dòng đơn phải có mặt trên phiếu giao.

        🔴 K13 — ``consu`` (SP dùng chung Hạng A) VÀO, chỉ dịch vụ bị loại. Dịch
        vụ không có gì để giao và không có gì để khách ký nhận; hàng Hạng A thì
        có — nó chỉ không đi qua tồn kho, mà đó là chuyện khác hẳn.
        """
        self.ensure_one()
        return self.line_ids.filtered(
            lambda line: line.product_id
            and line.product_id.detailed_type in ("product", "consu")
            and line.qty > 0)

    def _dlm_needed_qty(self):
        """{product: số phải giao} — gộp theo SP vì một SP có thể ở nhiều dòng."""
        self.ensure_one()
        needed = {}
        for line in self._dlm_deliverable_lines():
            needed[line.product_id] = needed.get(line.product_id, 0.0) + line.qty
        return needed

    def _dlm_delivery_pickings(self):
        """Phiếu GIAO HÀNG của đơn — KHÔNG phải mọi phiếu kho gắn vào đơn.

        🔴 K13 mở ra ca này: phiếu [8] Nhập thành phẩm cũng ghi
        ``dlm_sale_order_id`` (§11.13 — thủ kho phải biết lô hàng vừa làm xong là
        của đơn nào). Đếm nó chung với phiếu giao thì nhập 10 cái bàn vào kho bị
        tính là **đã giao 10 cái cho khách**: đơn tự nhảy sang "Đã giao đủ" khi
        hàng còn nằm nguyên trong Kho thành phẩm. Lọc theo loại hoạt động, không
        theo hướng phiếu (``outgoing`` còn có Trả NCC và Bán phế liệu).
        """
        self.ensure_one()
        return self.dlm_picking_ids.filtered(
            lambda p: p.picking_type_id.sequence_code == "GH")

    def _dlm_delivered_qty(self):
        """{product: số đã giao xong}. Chỉ đếm move ĐÃ hoàn tất — phiếu còn nháp
        hay đang chờ hàng chưa phải là hàng đã tới tay khách."""
        self.ensure_one()
        delivered = {}
        for picking in self._dlm_delivery_pickings():
            for move in picking.move_ids.filtered(lambda m: m.state == "done"):
                delivered[move.product_id] = (
                    delivered.get(move.product_id, 0.0) + move.quantity)
        return delivered

    def _dlm_planned_qty(self):
        """{product: số đang nằm trên phiếu chưa xong}.

        Trừ phần này khi tạo phiếu mới, nếu không bấm nút hai lần là ra hai phiếu
        giao cùng một lô hàng — kho sẽ giao gấp đôi mà không chứng từ nào cảnh báo.
        """
        self.ensure_one()
        planned = {}
        open_pickings = self._dlm_delivery_pickings().filtered(
            lambda p: p.state not in ("done", "cancel"))
        for picking in open_pickings:
            for move in picking.move_ids.filtered(
                    lambda m: m.state != "cancel"):
                planned[move.product_id] = (
                    planned.get(move.product_id, 0.0) + move.product_uom_qty)
        return planned

    def _dlm_remaining_qty(self):
        """{product: số còn phải lên phiếu} = cần − đã giao − đang trên phiếu."""
        self.ensure_one()
        needed = self._dlm_needed_qty()
        delivered = self._dlm_delivered_qty()
        planned = self._dlm_planned_qty()
        remaining = {}
        for product, qty in needed.items():
            rest = qty - delivered.get(product, 0.0) - planned.get(product, 0.0)
            if not float_is_zero(
                    rest, precision_rounding=product.uom_id.rounding or 0.01) \
                    and rest > 0:
                remaining[product] = rest
        return remaining

    def _dlm_is_fully_delivered(self, needed, delivered):
        self.ensure_one()
        for product, qty in needed.items():
            rounding = product.uom_id.rounding or 0.01
            if float_compare(delivered.get(product, 0.0), qty,
                             precision_rounding=rounding) < 0:
                return False
        return True

    # ── Hành động ────────────────────────────────────────────────────────────
    def action_dlm_create_delivery(self):
        """Tạo phiếu giao hàng cho phần chưa có phiếu.

        sudo khi ghi: Sales biết khách đã sẵn sàng nhận nhưng theo ma trận quyền
        (§8.4) họ chỉ ĐỌC phiếu kho — quyền tạo/sửa thuộc Thủ kho. Yêu cầu giao
        hàng không phải là thao tác kho, nên mở cho cả hai bên bằng cách kiểm vai
        trò tường minh ở đây rồi ghi bằng sudo, thay vì nới ACL cho Sales sửa
        được MỌI phiếu kho (kể cả phiếu nhận — mất kiểm soát chéo).
        """
        self.ensure_one()
        self._dlm_check_delivery_allowed()

        remaining = self._dlm_remaining_qty()
        if not remaining:
            raise UserError(_(
                "Mọi mặt hàng của đơn %s đã có phiếu giao hoặc đã giao xong.")
                % self.name)

        picking_type = self._dlm_delivery_picking_type()
        source = picking_type.default_location_src_id
        destination = (self.partner_id.property_stock_customer
                       or picking_type.default_location_dest_id)
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": self.name,
            "dlm_sale_order_id": self.id,
            "move_ids": [(0, 0, {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty,
                "location_id": source.id,
                "location_dest_id": destination.id,
            }) for product, qty in remaining.items()],
        })
        picking.action_confirm()
        picking.action_assign()
        # RS-02 — ép form Giao hàng của Đại Linh, không rơi về form gốc Odoo.
        return picking._dlm_open_picking(
            picking, _("Phiếu giao %s") % picking.name)

    def _dlm_check_delivery_allowed(self):
        self.ensure_one()
        if self.state == "draft":
            raise UserError(_(
                "Đơn %s còn ở trạng thái Nháp. Xác nhận đơn trước khi tạo phiếu "
                "giao — phiếu giao của đơn chưa chốt sẽ giữ chỗ hàng cho một "
                "cam kết chưa tồn tại.") % self.name)
        if self.state == "cancelled":
            raise UserError(
                _("Đơn %s đã huỷ, không tạo phiếu giao được.") % self.name)
        if not self._dlm_deliverable_lines():
            raise UserError(_(
                "Đơn %s không có mặt hàng nào để giao — mọi dòng đều là dịch "
                "vụ. Dịch vụ không có gì để khách ký nhận nên không lên phiếu "
                "giao.") % self.name)
        if not self.env.su and not any(
                self.env.user.has_group(role) for role in _DLM_DELIVERY_ROLES):
            raise UserError(_(
                "Bạn không có quyền tạo phiếu giao hàng. Việc này thuộc Thủ kho "
                "hoặc bộ phận Kinh doanh."))
        return True

    def _dlm_delivery_picking_type(self):
        """Loại hoạt động "Giao hàng khách" của kho DL."""
        warehouse = self.env["stock.warehouse"]._dlm_main_warehouse()
        picking_type = warehouse.out_type_id if warehouse else False
        if not picking_type:
            raise UserError(_(
                "Chưa cấu hình loại hoạt động Giao hàng khách. "
                "Chạy lại: -u dl_inventory"))
        return picking_type

    def action_dlm_open_pickings(self):
        """Smart button → phiếu giao hàng của đơn."""
        self.ensure_one()
        pickings = self._dlm_delivery_pickings()
        if not pickings:
            raise UserError(_("Đơn %s chưa có phiếu giao hàng nào.") % self.name)
        # RS-02 — helper ép view Đại Linh cho cả nhánh 1 phiếu lẫn nhiều phiếu.
        return pickings._dlm_open_pickings(
            _("Phiếu giao hàng của %s") % self.name,
            context={"default_dlm_sale_order_id": self.id})
