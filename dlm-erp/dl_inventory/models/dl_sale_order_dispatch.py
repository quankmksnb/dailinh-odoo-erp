# -*- coding: utf-8 -*-
"""Kiểm tra kho & Điều phối đơn bán hàng: tính sống nhu cầu hàng/vật tư rồi sinh chứng từ trong 1 lần bấm."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

# Thủ kho là CHỦ điều phối (biết hàng thật); Sales/Trưởng KD chỉ XEM. CEO/Admin dự phòng.
_DLM_DISPATCH_ROLES = (
    "dl_base.dl_group_warehouse",
    "dl_base.dl_group_admin",
    "dl_base.dl_group_ceo",
)


class DlSaleOrderDispatch(models.Model):
    _inherit = "dl.sale.order"

    dlm_dispatch_state = fields.Selection([
        ("none", "—"),
        ("to_dispatch", "Chờ điều phối"),
        ("dispatching", "Đang điều phối"),
        ("dispatched", "Đã điều phối"),
    ], string="Điều phối", compute="_compute_dlm_dispatch_state",
        store=True, default="none",
        help="Suy từ CHỨNG TỪ đã sinh ra, không phải từ tồn kho — nên lọc và "
             "sắp xếp được trên danh sách mà không phải đọc tồn của từng đơn.")

    dlm_supply_html = fields.Html(
        string="Kiểm tra kho", compute="_compute_dlm_supply",
        sanitize=False, readonly=True,
        help="Tính SỐNG mỗi lần mở form. Không lưu: số tồn đúng lúc lưu là số "
             "sai lúc đọc.")
    dlm_supply_summary = fields.Char(
        string="Tóm tắt cung ứng", compute="_compute_dlm_supply")
    dlm_supply_level = fields.Selection([
        ("ok", "Đủ"),
        ("warning", "Thiếu"),
        ("danger", "Chặn"),
        ("none", "Không có gì để điều phối"),
    ], string="Mức cảnh báo cung ứng", compute="_compute_dlm_supply")

    # ------------------------------------------------------------------
    # Trạng thái điều phối — CHỈ depends vào chứng từ
    # ------------------------------------------------------------------
    # Tuyệt đối không depends stock.quant: mỗi phiếu validate là recompute mọi đơn ⇒ hệ thống bò.
    @api.depends("state", "line_ids.qty", "line_ids.product_id",
                 "dlm_picking_ids.state",
                 "dlm_picking_ids.picking_type_id",
                 "dlm_picking_ids.move_ids.state",
                 "dlm_picking_ids.move_ids.product_uom_qty",
                 "dlm_picking_ids.move_ids.quantity")
    def _compute_dlm_dispatch_state(self):
        for order in self:
            if order.state != "confirmed":
                order.dlm_dispatch_state = "none"
                continue
            live = order.dlm_picking_ids.filtered(
                lambda p: p.state != "cancel")
            if not live:
                order.dlm_dispatch_state = "to_dispatch"
            elif order._dlm_remaining_qty():
                order.dlm_dispatch_state = "dispatching"
            else:
                order.dlm_dispatch_state = "dispatched"

    # ------------------------------------------------------------------
    # Bước 1 — KIỂM TRA KHO (tính sống, không ghi gì)
    # ------------------------------------------------------------------
    def _dlm_supply_check(self):
        """Bảng cung ứng của đơn (hàng bán + vật tư + câu chặn/cảnh báo); khả dụng đọc tại đúng khu phiếu sẽ lấy."""
        self.ensure_one()
        Quant = self.env["stock.quant"]
        Location = self.env["stock.location"]
        loc_tp = Location._dlm_location("dl_inventory.stock_location_tp")
        loc_kho = Location._dlm_location(
            "dl_inventory.stock_location_nhan_kho")

        result = {"goods": [], "materials": [], "blocking": [], "warnings": [],
                  "actionable": False}
        remaining = self._dlm_remaining_qty()
        material_need = {}
        # Sổ hàng đã hứa trong lần kiểm này: 2 dòng cùng mặt hàng không cùng thấy 1 lô rồi cùng báo "đủ".
        taken = {}

        for product, qty in remaining.items():
            line = self._dlm_line_for(product)
            made_to_order = product.detailed_type == "consu"
            if made_to_order:
                # Hàng đặt riêng (Hạng A) không có tồn và không hỏi tồn — ghi "không tính", không ghi "Tồn 0".
                ready = 0.0
            else:
                free = Quant._dlm_available_qty(product, loc_tp)
                ready = min(qty, max(0.0, free - taken.get(product.id, 0.0)))
                taken[product.id] = taken.get(product.id, 0.0) + ready
            to_make = qty - ready
            result["goods"].append({
                "product": product,
                "need": qty,
                "ready": ready,
                "to_make": to_make,
                "made_to_order": made_to_order,
                "kind": self._dlm_goods_kind(line, product),
            })
            if to_make <= 0:
                continue
            self._dlm_collect_needs(line, product, to_make, material_need,
                                    loc_kho, result)

        planned = self._dlm_material_planned_qty()
        for product, need in material_need.items():
            rounding = product.uom_id.rounding or 0.01
            outstanding = float_round(
                need - planned.get(product, 0.0), precision_rounding=rounding)
            if float_compare(outstanding, 0.0,
                             precision_rounding=rounding) <= 0:
                continue
            available = Quant._dlm_available_qty(product, loc_kho)
            result["materials"].append({
                "product": product,
                "need": outstanding,
                "available": min(outstanding, available),
                "missing": max(0.0, outstanding - available),
            })

        # "Còn việc để làm" ≠ "còn dòng chưa giao": đơn gia công đã cấp đủ vật tư vẫn còn dòng chưa giao.
        result["actionable"] = bool(
            any(row["ready"] > 0 for row in result["goods"])
            or result["materials"])
        return result

    def _dlm_collect_needs(self, line, product, qty, material_need, location,
                           result):
        """Phần phải làm của mặt hàng → nhu cầu vật tư (hàng thương mại không BOM ⇒ mua chính nó)."""
        self.ensure_one()
        # sudo ngay từ đây: Thủ kho không có quyền đọc dl.bom; chỉ số LƯỢNG đi ra, không chạm field tiền.
        bom = line.bom_id.sudo() if line else False
        if not bom:
            if line and line.line_type == "manufactured":
                # Dòng gia công thiếu BOM: không tính được nhu cầu ⇒ chặn cứng.
                result["blocking"].append(_(
                    "Dòng gia công \"%s\" chưa gắn định mức (BOM) — không tính "
                    "được cần bao nhiêu vật tư."
                ) % product.display_name)
                return
            # Hàng thương mại / hàng không định mức: mua chính nó.
            _add(material_need, product, qty)
            return

        if bom.status not in ("confirmed", "locked"):
            # Cảnh báo MỀM: chặn cứng là chặn cả ca hợp lệ.
            result["warnings"].append(_(
                "Định mức của \"%s\" chưa được khoá — nhu cầu vật tư có thể "
                "còn đổi."
            ) % product.display_name)

        report = bom._dlm_explode_report(qty, location=location)
        for material, need in report["requirements"].items():
            _add(material_need, material, need)
        for btp in report["btp_no_bom"]:
            result["blocking"].append(_(
                "Bán thành phẩm \"%s\" chưa có định mức chuẩn — nhánh vật tư "
                "của nó không được tính, sẽ mua thiếu."
            ) % btp.display_name)
        for scrap in report["scrap"]:
            result["blocking"].append(_(
                "Định mức của \"%(product)s\" có dòng phế liệu \"%(scrap)s\" — "
                "phế liệu không phải nguyên liệu đầu vào."
            ) % {"product": product.display_name,
                 "scrap": scrap.display_name})

    def _dlm_goods_kind(self, line, product):
        if product.detailed_type == "consu":
            return _("Hàng đặt riêng")
        if line and line.line_type == "trading":
            return _("Thương mại")
        return _("Gia công")

    def _dlm_line_for(self, product):
        """Dòng đơn đầu tiên bán mặt hàng này — dùng để phân loại nhánh."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.product_id == product)[:1]

    def _dlm_material_planned_qty(self):
        """{vật tư: số đã trên phiếu cấp chưa xong của đơn} — trừ để bấm điều phối lần 2 không giữ chỗ gấp đôi."""
        self.ensure_one()
        planned = {}
        for picking in self._dlm_material_pickings().filtered(
                lambda p: p.state not in ("done", "cancel")):
            for move in picking.move_ids.filtered(
                    lambda m: m.state != "cancel"):
                planned[move.product_id] = (
                    planned.get(move.product_id, 0.0) + move.product_uom_qty)
        return planned

    def _dlm_material_pickings(self):
        """Phiếu CẤP VẬT TƯ của đơn — chuyển kho ra Xưởng, không phải mọi phiếu."""
        self.ensure_one()
        xuong = self.env["stock.location"]._dlm_location(
            "dl_inventory.stock_location_xuong")
        return self.dlm_picking_ids.filtered(
            lambda p: p.picking_type_id.code == "internal"
            and p.location_dest_id == xuong)

    # ------------------------------------------------------------------
    # Dải cảnh báo & bảng trên form
    # ------------------------------------------------------------------
    def _compute_dlm_supply(self):
        for order in self:
            if order.state != "confirmed":
                order.dlm_supply_html = False
                order.dlm_supply_summary = False
                order.dlm_supply_level = "none"
                continue
            try:
                check = order._dlm_supply_check()
            except UserError as err:
                # BOM vòng lặp raise; trong computed field raise = chết cả form ⇒ biến thành dải đỏ đọc được.
                order.dlm_supply_html = False
                order.dlm_supply_summary = err.args[0] if err.args else _(
                    "Không tính được nhu cầu vật tư.")
                order.dlm_supply_level = "danger"
                continue
            order.dlm_supply_html = order._dlm_supply_table(check)
            order.dlm_supply_summary = order._dlm_supply_sentence(check)
            order.dlm_supply_level = (
                "danger" if check["blocking"]
                else "none" if not check["actionable"]
                else "warning" if any(
                    row["missing"] > 0 for row in check["materials"])
                else "ok")

    def _dlm_supply_sentence(self, check):
        """Một câu tóm tắt tình hình cung ứng (nêu số + tên) — dải trên cùng đọc câu này."""
        if check["blocking"]:
            return check["blocking"][0]
        if not check["actionable"]:
            # Phân biệt: đơn đã xong hẳn vs đơn đang nằm ở xưởng chờ làm.
            if check["goods"]:
                return _(
                    "Đã điều phối xong phần kho làm được — %s mặt hàng đang "
                    "chờ xưởng làm hoặc chờ hàng về."
                ) % len(check["goods"])
            return _("Không còn gì để điều phối — mọi mặt hàng đã có chứng từ.")
        ready = sum(1 for row in check["goods"] if row["to_make"] <= 0)
        missing = [row for row in check["materials"] if row["missing"] > 0]
        parts = []
        if check["goods"]:
            parts.append(_("Giao được ngay %(ready)s/%(total)s mặt hàng") % {
                "ready": ready, "total": len(check["goods"])})
        if missing:
            parts.append(_("thiếu %(count)s vật tư (%(names)s)") % {
                "count": len(missing),
                "names": ", ".join(
                    row["product"].display_name for row in missing[:3])})
        elif check["materials"]:
            parts.append(_("vật tư đủ cho %s mục") % len(check["materials"]))
        return " · ".join(parts)

    def _dlm_supply_table(self, check):
        """Bảng HTML hai phần (mặt hàng bán + vật tư) — dùng HTML computed thay component OWL."""
        self.ensure_one()
        if not check["goods"] and not check["materials"]:
            return False
        blocks = []
        if check["goods"]:
            rows = []
            for row in check["goods"]:
                if row["made_to_order"]:
                    # Hàng đặt riêng: ghi lý do (chữ mờ), không ghi "0" giữa cột số.
                    san_sang = "<span class='text-muted'>%s</span>" % _(
                        "hàng đặt riêng")
                else:
                    san_sang = _dlm_num(row["ready"])
                rows.append(("", [
                    row["product"].display_name, row["kind"],
                    _dlm_num(row["need"]), san_sang,
                    _dlm_num(row["to_make"])]))
            blocks.append(_dlm_table([
                (_("Mặt hàng"), ""),
                (_("Nhánh"), ""),
                (_("Cần giao"), "text-end"),
                (_("Giao được ngay"), "text-end"),
                (_("Phải làm/mua"), "text-end"),
            ], rows, "dl-supply-goods"))
        if check["materials"]:
            rows = []
            for row in check["materials"]:
                thieu = row["missing"]
                # Dòng thiếu nói bằng chữ (in giấy/mù màu vẫn đọc được); không chồng badge vàng lên nền vàng.
                danh_gia = (
                    "<span class='fw-semibold text-danger'>%s</span>" % (
                        _("thiếu %s") % _dlm_num(thieu)) if thieu > 0
                    else "<span class='text-muted'>%s</span>" % _("đủ"))
                rows.append(("table-warning" if thieu > 0 else "", [
                    row["product"].display_name, _dlm_num(row["need"]),
                    _dlm_num(row["available"]), danh_gia]))
            blocks.append(_dlm_table([
                (_("Vật tư / hàng phải mua"), ""),
                (_("Cần"), "text-end"),
                (_("Còn lấy được"), "text-end"),
                (_("Đánh giá"), "text-end"),
            ], rows, "dl-supply-materials"))
        return "<div class='dl-supply'>%s</div>" % "".join(blocks)

    # ------------------------------------------------------------------
    # Bước 2 — ĐIỀU PHỐI: một nút, N chứng từ, cùng một transaction
    # ------------------------------------------------------------------
    def action_dlm_dispatch(self):
        """Nút Điều phối: sinh mọi chứng từ đơn cần trong 1 lần bấm (có lỗi chặn ⇒ raise, không sinh gì)."""
        self.ensure_one()
        self._dlm_check_dispatch_allowed()
        check = self._dlm_supply_check()
        if check["blocking"]:
            raise UserError(_(
                "Chưa điều phối được đơn %(order)s:\n\n%(problems)s"
            ) % {"order": self.name,
                 "problems": "\n".join("• " + p for p in check["blocking"])})
        if not check["actionable"]:
            # Bấm hai lần là giữ chỗ gấp đôi.
            raise UserError(_(
                "Đơn %(order)s không còn gì để điều phối.\n\n%(detail)s"
            ) % {"order": self.name,
                 "detail": self._dlm_supply_sentence(check)})

        created = []
        delivery = self._dlm_dispatch_delivery(check)
        if delivery:
            created.append(_("phiếu giao %s") % delivery.name)
        issue = self._dlm_dispatch_material_issue(check)
        if issue:
            created.append(_("phiếu cấp vật tư %s") % issue.name)
        shortages = [row for row in check["materials"] if row["missing"] > 0]
        for label in self._dlm_dispatch_shortage(shortages):
            created.append(label)

        # sudo ghi chatter: Thủ kho chỉ ĐỌC dl.sale.order; author_id tường minh để vết ghi đúng người bấm.
        self.sudo().message_post(
            body=_("Điều phối: đã sinh %(what)s.") % {
                "what": ", ".join(created) if created else _("không có gì")},
            author_id=self.env.user.partner_id.id)
        pickings = delivery | issue
        if pickings:
            return pickings._dlm_open_pickings(
                _("Chứng từ điều phối của %s") % self.name)
        return True

    def _dlm_check_dispatch_allowed(self):
        self.ensure_one()
        if self.state == "draft":
            raise UserError(_(
                "Đơn %s còn ở trạng thái Nháp. Điều phối là giữ chỗ hàng cho "
                "một cam kết chưa tồn tại.") % self.name)
        if self.state == "cancelled":
            raise UserError(
                _("Đơn %s đã huỷ, không điều phối được.") % self.name)
        if not self.env.su and not any(
                self.env.user.has_group(role)
                for role in _DLM_DISPATCH_ROLES):
            raise UserError(_(
                "Điều phối đơn hàng là việc của Thủ kho — họ là người biết "
                "hàng thật đang có gì. Bạn xem được kết quả trên đơn nhưng "
                "không bấm được nút này."))
        return True

    def _dlm_dispatch_delivery(self, check):
        """Phiếu giao cho phần thành phẩm lấy được NGAY (chỉ phần khả dụng, không cả dòng đơn)."""
        self.ensure_one()
        ready = {row["product"]: row["ready"] for row in check["goods"]
                 if row["ready"] > 0}
        if not ready:
            return self.env["stock.picking"]
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
            }) for product, qty in ready.items()],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _dlm_dispatch_material_issue(self, check):
        """MỘT phiếu cấp vật tư cho cả đơn; đưa nguyên nhu cầu lên rồi để action_assign giữ được bao nhiêu hay bấy nhiêu."""
        self.ensure_one()
        # Chỉ thứ xưởng dùng được: hàng thương mại tuy phải mua nhưng không ra Xưởng (luật khu chặn).
        needs = {row["product"]: row["need"] for row in check["materials"]
                 if row["product"].product_kind in
                 ("material", "material_processed")}
        if not needs:
            return self.env["stock.picking"]
        Location = self.env["stock.location"]
        source = Location._dlm_location(
            "dl_inventory.stock_location_nhan_kho")
        destination = Location._dlm_location(
            "dl_inventory.stock_location_xuong")
        picking_type = self.env["stock.warehouse"]._dlm_main_warehouse(
        ).int_type_id
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
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
            }) for product, qty in needs.items()],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _dlm_dispatch_shortage(self, shortages):
        """Móc nối cho phần THIẾU — mặc định không làm gì; dl_purchase ghi đè để sinh đơn mua nháp."""
        self.ensure_one()
        return []


def _add(bucket, product, qty):
    rounding = product.uom_id.rounding or 0.01
    bucket[product] = float_round(
        bucket.get(product, 0.0) + qty, precision_rounding=rounding)


def _dlm_num(value):
    """Số cho người đọc: bỏ đuôi 0 thừa (12,50 → 12,5; 3,00 → 3)."""
    text = "%.3f" % (value or 0.0)
    text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") if text else "0"


def _dlm_table(columns, rows, css):
    """columns = [(nhãn, lớp căn lề)]; rows = [(lớp dòng, [ô])] — ô và đầu cột dùng CHUNG lớp căn lề."""
    head = "".join(
        "<th class='%s'>%s</th>" % (align, label) for label, align in columns)
    body = "".join(
        "<tr class='%s'>%s</tr>" % (row_css, "".join(
            "<td class='%s'>%s</td>" % (columns[index][1], cell)
            for index, cell in enumerate(cells)))
        for row_css, cells in rows)
    return (
        "<table class='table table-sm dl-supply-table %s'>"
        "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
            css, head, body))
