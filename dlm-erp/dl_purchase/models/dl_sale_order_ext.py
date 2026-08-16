# -*- coding: utf-8 -*-
"""Đơn bán nối vào Mua hàng: thiếu hàng ⇒ đơn mua nháp, và giá vốn vật tư thực tế FIFO theo lô."""

from markupsafe import Markup

from odoo import _, fields, models
from odoo.tools import html_escape

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
        """Điều phối kho thiếu hàng ⇒ gom phần thiếu thành đơn mua nháp, một đơn mỗi NCC."""
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
            # Không chặn điều phối, nhưng phải báo vào hòm việc Mua hàng — ca này không sinh đơn mua nào.
            self._dlm_notify_missing_seller(khong_ncc)
            labels.append(_(
                "⚠ chưa có nhà cung cấp cho: %s (không lên được đơn mua)"
            ) % ", ".join(p.display_name for p in khong_ncc))
        return labels

    def _dlm_best_seller(self, product):
        """Chọn NCC cho nhu cầu này: bảng giá đang áp dụng, nhiều hơn một thì lấy giá thấp nhất."""
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
            # Không làm hỏng cả lượt điều phối vì một bảng giá sai; Mua hàng thấy giá 0 và phải gõ lại.
            return 0.0

    def _dlm_buyer_users(self):
        """User nhóm Mua hàng đang hoạt động — người nhận mọi lời báo mua hàng."""
        group = self.env.ref(
            "dl_base.dl_group_purchasing", raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        return group.users.filtered(lambda u: u.active and not u.share)

    def _dlm_notify_buyers(self, orders):
        """Giao việc mua hàng cho nhóm Mua hàng qua activity (chính là email tự động)."""
        self.ensure_one()
        users = self._dlm_buyer_users()
        for order in orders:
            note = self._dlm_buyer_note(order)
            for user in users:
                order.sudo().activity_schedule(
                    "mail.mail_activity_data_todo", user_id=user.id,
                    summary=_("Cần mua hàng cho đơn %s") % self.name,
                    note=note)
        return True

    def _dlm_buyer_note(self, order):
        """Thân thư/việc cho một đơn mua nháp — liệt kê vật tư + số lượng, CỐ Ý không có giá."""
        self.ensure_one()
        dong = "".join(
            "<li>%s — <strong>%s %s</strong></li>" % (
                html_escape(line.product_id.display_name),
                _num(line.qty),
                html_escape(line.product_id.uom_id.name or ""))
            for line in order.line_ids)
        return Markup(
            "<p>Điều phối kho đơn bán <strong>%(don)s</strong> (khách %(khach)s) "
            "phát hiện thiếu hàng. Đơn mua nháp <strong>%(po)s</strong> đã gom "
            "sẵn cho %(ncc)s:</p><ul>%(dong)s</ul>"
            "<p>Hỏi giá nhà cung cấp rồi chốt giá cho lô này.</p>" % {
                "don": html_escape(self.name),
                "khach": html_escape(self.partner_id.display_name),
                "po": html_escape(order.name),
                "ncc": html_escape(order.partner_id.display_name),
                "dong": dong,
            })

    def _dlm_notify_missing_seller(self, products):
        """Báo Mua hàng ca thiếu vật tư CHƯA có NCC (không sinh được đơn mua) — gắn lên đơn bán."""
        self.ensure_one()
        note = Markup(
            "<p>Điều phối kho đơn bán <strong>%(don)s</strong> thiếu những thứ "
            "sau, nhưng <strong>chưa vật tư nào có bảng giá nhà cung cấp đang "
            "áp dụng</strong> nên hệ thống KHÔNG lên được đơn mua:</p>"
            "<ul>%(dong)s</ul>"
            "<p>Khai nhà cung cấp và bảng giá cho các mặt hàng trên, rồi điều "
            "phối lại đơn để hệ thống gom đơn mua.</p>" % {
                "don": html_escape(self.name),
                "dong": "".join(
                    "<li>%s</li>" % html_escape(product.display_name)
                    for product in products),
            })
        for user in self._dlm_buyer_users():
            self.sudo().activity_schedule(
                "mail.mail_activity_data_todo", user_id=user.id,
                summary=_("Thiếu vật tư CHƯA CÓ nhà cung cấp — đơn %s")
                % self.name,
                note=note)
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
        """Vật tư đã tiêu thụ cho đơn (dòng consume của phiếu [8]), tính theo giá lô đã lấy."""
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
