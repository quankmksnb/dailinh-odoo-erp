# -*- coding: utf-8 -*-
"""Mối nối đơn bán hàng ↔ phiếu giao hàng (phiếu giao bấm nút mới sinh, không tự sinh khi chốt đơn)."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero

# Vai trò được phép bấm Tạo phiếu giao: Thủ kho + Sales/Trưởng KD/CEO/Admin.
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
    # Có dòng nào cần giao qua kho không — để ẩn/hiện nút Tạo phiếu giao.
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
        """Dòng đơn phải lên phiếu giao (gồm cả `consu` Hạng A, chỉ loại dịch vụ)."""
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
        """Chỉ phiếu Giao hàng (loại "GH") của đơn — loại phiếu Nhập thành phẩm/Trả NCC/Bán phế liệu."""
        self.ensure_one()
        return self.dlm_picking_ids.filtered(
            lambda p: p.picking_type_id.sequence_code == "GH")

    def _dlm_delivered_qty(self):
        """{product: số đã giao xong} — chỉ đếm move đã hoàn tất (done)."""
        self.ensure_one()
        delivered = {}
        for picking in self._dlm_delivery_pickings():
            for move in picking.move_ids.filtered(lambda m: m.state == "done"):
                delivered[move.product_id] = (
                    delivered.get(move.product_id, 0.0) + move.quantity)
        return delivered

    def _dlm_planned_qty(self, exclude_picking=None):
        """{product: số đang nằm trên phiếu chưa xong} — trừ khi tạo phiếu mới để không giao gấp đôi (`exclude_picking` = phiếu đang lập, không tự trừ mình)."""
        self.ensure_one()
        planned = {}
        open_pickings = self._dlm_delivery_pickings().filtered(
            lambda p: p.state not in ("done", "cancel"))
        if exclude_picking:
            open_pickings -= exclude_picking
        for picking in open_pickings:
            for move in picking.move_ids.filtered(
                    lambda m: m.state != "cancel"):
                planned[move.product_id] = (
                    planned.get(move.product_id, 0.0) + move.product_uom_qty)
        return planned

    def _dlm_remaining_qty(self, exclude_picking=None):
        """{product: số còn phải lên phiếu} = cần − đã giao − đang trên phiếu."""
        self.ensure_one()
        needed = self._dlm_needed_qty()
        delivered = self._dlm_delivered_qty()
        planned = self._dlm_planned_qty(exclude_picking)
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
        """Màn Đơn bán hàng: tạo phiếu giao cho phần chưa có phiếu (ghi bằng sudo sau khi kiểm vai trò)."""
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
        return pickings._dlm_open_pickings(
            _("Phiếu giao hàng của %s") % self.name,
            context={"default_dlm_sale_order_id": self.id})
