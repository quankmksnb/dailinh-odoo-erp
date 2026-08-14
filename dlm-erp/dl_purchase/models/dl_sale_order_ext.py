# -*- coding: utf-8 -*-
"""K20/K22 — Đơn bán hàng nối vào Mua hàng.

Hai việc, cùng một mối nối:

  • **Thiếu hàng ⇒ đơn mua nháp** — ghi đè móc ``_dlm_dispatch_shortage`` mà
    ``dl_inventory`` để sẵn. Đặt ở đây chứ không ở ``dl_inventory`` vì phân hệ
    Kho không được biết gì về mua hàng: gỡ ``dl_purchase`` ra thì Kho vẫn phải
    chạy nguyên.
  • **Giá vốn vật tư THỰC TẾ theo FIFO** — đọc giá của chính những lô đã dùng.

Thiết kế: ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §4, §6.4.
"""

from odoo import _, fields, models

from .dl_purchase_order import _DLM_BUY_PRICE_GROUPS


class DlSaleOrderPurchase(models.Model):
    _inherit = "dl.sale.order"

    dlm_purchase_order_ids = fields.Many2many(
        "dl.purchase.order", "dl_purchase_sale_order_rel",
        "sale_id", "purchase_id", string="Đơn mua phát sinh", readonly=True)
    dlm_purchase_count = fields.Integer(
        string="Số đơn mua", compute="_compute_dlm_purchase_count")

    dlm_actual_material_cost = fields.Float(
        string="Giá vốn vật tư thực tế", compute="_compute_dlm_actual_cost",
        digits="Product Price", groups=_DLM_BUY_PRICE_GROUPS)
    dlm_cost_detail_html = fields.Html(
        string="Chi tiết giá vốn", compute="_compute_dlm_actual_cost",
        sanitize=False, groups=_DLM_BUY_PRICE_GROUPS)
    dlm_cost_is_estimated = fields.Boolean(
        string="Có lô dùng giá ước tính", compute="_compute_dlm_actual_cost",
        groups=_DLM_BUY_PRICE_GROUPS)

    def _compute_dlm_purchase_count(self):
        for order in self:
            order.dlm_purchase_count = len(order.dlm_purchase_order_ids)

    # ------------------------------------------------------------------
    # Điều phối: phần THIẾU đi sang Mua hàng
    # ------------------------------------------------------------------
    def _dlm_dispatch_shortage(self, shortages):
        """Gom phần thiếu thành đơn mua NHÁP, MỘT đơn cho MỖI nhà cung cấp.

        Không đẻ model "đề nghị mua" (D-08, người dùng xác nhận U-2): đơn mua ở
        trạng thái Nháp CHÍNH LÀ đề nghị mua.

        Mặt hàng không có NCC nào ⇒ **không lên đơn** (MH-14) và phải nêu đích
        danh: im lặng bỏ qua là Mua hàng không bao giờ biết cần mua món đó.
        """
        self.ensure_one()
        if not shortages:
            return []
        by_supplier = {}
        khong_ncc = []
        for row in shortages:
            product = row["product"]
            seller = self._dlm_best_seller(product)
            if not seller:
                khong_ncc.append(product)
                continue
            by_supplier.setdefault(seller.partner_id, []).append(
                (product, row["missing"], seller))

        labels = []
        orders = self.env["dl.purchase.order"].sudo()
        for partner, rows in by_supplier.items():
            order = orders.create({
                "partner_id": partner.id,
                "dlm_origin_order_ids": [(4, self.id)],
                "note": _("Nhu cầu phát sinh từ đơn bán %s.") % self.name,
                "line_ids": [(0, 0, {
                    "product_id": product.id,
                    "qty": qty,
                    "price_unit": self._dlm_seller_price(seller, product),
                    "price_list_unit": self._dlm_seller_price(seller, product),
                }) for product, qty, seller in rows],
            })
            orders |= order
            labels.append(_("đơn mua nháp %s") % order.name)
        if orders:
            self._dlm_notify_buyers(orders)
        if khong_ncc:
            # Không chặn điều phối — phần còn lại vẫn phải chạy. Nhưng phải NÓI.
            labels.append(_(
                "⚠ chưa có nhà cung cấp cho: %s (không lên được đơn mua)"
            ) % ", ".join(p.display_name for p in khong_ncc))
        return labels

    def _dlm_best_seller(self, product):
        """NCC dùng cho nhu cầu này — DP-17.

        Chỉ lấy bảng giá ĐANG ÁP DỤNG (`is_applied`, kéo theo đã duyệt). Nhiều
        hơn một thì lấy giá thấp nhất — chọn bừa là Mua hàng phải sửa tay mọi
        đơn, mà sửa tay thì họ sẽ thôi dùng nút này.
        """
        self.ensure_one()
        sellers = product.sudo().seller_ids.filtered(
            lambda s: s.is_applied and s.partner_id)
        if not sellers:
            return sellers
        return sellers.sorted(
            key=lambda s: self._dlm_seller_price(s, product) or float("inf"))[0]

    def _dlm_seller_price(self, seller, product):
        try:
            return seller._dlm_reference_unit_cost(product)
        except Exception:  # noqa: BLE001 — bảng giá lệch ĐVT/tiền tệ
            # Không được làm hỏng cả lượt điều phối vì một bảng giá khai sai;
            # Mua hàng sẽ thấy dòng giá 0 và phải gõ giá trước khi chốt (MH-05).
            return 0.0

    def _dlm_notify_buyers(self, orders):
        """Giao việc cho Mua hàng — không để đơn nháp nằm chờ ai đó tình cờ mở màn."""
        self.ensure_one()
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        users = group.users.filtered(lambda u: u.active and not u.share) \
            if group else self.env["res.users"]
        for order in orders:
            for user in users:
                order.sudo().activity_schedule(
                    "mail.mail_activity_data_todo", user_id=user.id,
                    summary=_("Cần mua hàng cho đơn %s") % self.name,
                    note=_("Điều phối kho phát hiện thiếu hàng. Đơn mua nháp "
                           "%(po)s đã được gom sẵn theo nhà cung cấp — hỏi giá "
                           "rồi chốt giá cho lô này.") % {"po": order.name})
        return True

    # ------------------------------------------------------------------
    # Giá vốn vật tư thực tế (FIFO theo lô)
    # ------------------------------------------------------------------
    def _compute_dlm_actual_cost(self):
        for order in self:
            rows = order._dlm_actual_cost_rows()
            order.dlm_actual_material_cost = sum(
                row["amount"] for row in rows)
            order.dlm_cost_is_estimated = any(
                row["estimated"] for row in rows)
            order.dlm_cost_detail_html = order._dlm_cost_table(rows)

    def _dlm_actual_cost_rows(self):
        """Vật tư ĐÃ TIÊU THỤ cho đơn này, tính theo giá của chính lô đã lấy.

        🔴 Đọc dòng ``consume`` của phiếu [8] Nhập kho từ xưởng — đó là nơi vật
        tư THẬT SỰ rời sổ. Phiếu cấp vật tư ra xưởng chỉ là **bàn giao**: thép
        bàn giao thừa vẫn trả lại kho được, nên tính tiền ở đó là tính cả phần
        chưa dùng.
        """
        self.ensure_one()
        rows = []
        moves = self.env["stock.move"].sudo().search([
            ("picking_id.dlm_sale_order_id", "=", self.id),
            ("state", "=", "done"),
            ("dlm_move_kind", "in", ("consume", "return")),
        ])
        for move in moves:
            dau = -1.0 if move.dlm_move_kind == "return" else 1.0
            for line in move.move_line_ids:
                lot = line.lot_id
                unit = lot.dlm_unit_cost if lot else 0.0
                estimated = bool(
                    not lot or lot.dlm_cost_is_estimated or not unit)
                if not unit:
                    unit = line.product_id.standard_price or 0.0
                rows.append({
                    "product": line.product_id,
                    "lot": lot,
                    "qty": dau * line.quantity,
                    "unit": unit,
                    "amount": dau * line.quantity * unit,
                    "estimated": estimated,
                })
        return rows

    def _dlm_cost_table(self, rows):
        if not rows:
            return False
        body = []
        for row in rows:
            body.append(
                "<tr class='%s'><td>%s</td><td>%s</td>"
                "<td class='text-end'>%s</td><td class='text-end'>%s</td>"
                "<td class='text-end'>%s</td><td>%s</td></tr>" % (
                    "table-warning" if row["estimated"] else "",
                    row["product"].display_name,
                    row["lot"].name if row["lot"] else _("(không theo lô)"),
                    _num(row["qty"]), _money(row["unit"]),
                    _money(row["amount"]),
                    _("ước tính") if row["estimated"] else _("theo đơn mua")))
        return (
            "<table class='table table-sm mb-0'><thead><tr>"
            "<th>%s</th><th>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th>"
            "<th>%s</th></tr></thead><tbody>%s</tbody></table>" % (
                _("Vật tư"), _("Lô"), _("Số lượng"), _("Đơn giá lô"),
                _("Thành tiền"), _("Nguồn giá"), "".join(body)))

    def action_dlm_open_purchase_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Đơn mua phát sinh từ %s") % self.name,
            "res_model": "dl.purchase.order",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.dlm_purchase_order_ids.ids)],
        }


def _num(value):
    text = "%.3f" % (value or 0.0)
    text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") if text else "0"


def _money(value):
    return "{:,.0f}".format(value or 0.0).replace(",", ".")
