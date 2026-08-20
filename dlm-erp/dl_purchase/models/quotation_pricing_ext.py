# -*- coding: utf-8 -*-
"""Giá vật tư trong báo giá = giá lô đang có trong kho (FIFO) + giá mua mới cho phần thiếu."""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape
from odoo.tools.float_utils import float_compare, float_is_zero

# Khu đọc tồn vật tư: Kho nguyên vật liệu (từ K15 chứa cả vật tư lẫn bán thành
# phẩm). Đây đúng là khu phiếu cấp vật tư sẽ lấy hàng ra — đọc tồn ở khu khác
# là hứa một con số mà chứng từ không lấy được.
_DLM_MATERIAL_LOCATION = "dl_inventory.stock_location_nhan_kho"


class DlQuotationPricingService(models.AbstractModel):
    _inherit = "dl.quotation.pricing.service"

    def _material_unit_price(self, material, total_need, context, bom_line=None):
        """Đơn giá vật tư có xét tồn kho — ghi đè bản gốc chỉ đọc bảng giá NCC.

        Vì sao ở `dl_purchase`: đây là module duy nhất thấy được CẢ tồn kho
        (`dl_inventory`) LẪN giá mua đóng trên lô (`stock.lot.dlm_unit_cost` khai
        ở chính module này). `dl_sale` đứng trước cả hai trong đồ thị phụ thuộc.

        🔴 Chỉ `unit_price` (giá thành) mới trộn giá kho. `replacement_price`
        (nuôi GIÁ SÀN) vẫn là giá mua lại hiện hành — bán theo lô cũ rẻ mà lấy
        luôn sàn theo lô cũ thì mỗi vòng giá thép tăng lại tụt một nấc biên."""
        info = super()._material_unit_price(
            material, total_need, context, bom_line=bom_line)
        rounding = material.uom_id.rounding or 0.01
        if float_compare(total_need, 0.0, precision_rounding=rounding) <= 0:
            return info

        gia_mua = info["replacement_price"]
        lo_dung = self._dlm_fifo_lots(material, total_need)
        qty_kho = sum(row["qty"] for row in lo_dung)
        tien_kho = sum(row["qty"] * row["cost"] for row in lo_dung)
        qty_mua = max(0.0, total_need - qty_kho)
        tong_tien = tien_kho + qty_mua * gia_mua

        info.update(
            unit_price=tong_tien / total_need,
            qty_from_stock=qty_kho,
            qty_to_buy=qty_mua,
            buy_price=gia_mua,
            note=self._dlm_price_note(material, lo_dung, qty_mua, gia_mua),
        )
        return info

    def _dlm_fifo_lots(self, material, need):
        """Các lô sẽ được lấy cho `need` đơn vị, theo đúng thứ tự FIFO của kho.

        Đọc `stock.quant` tại Kho nguyên vật liệu, trừ phần đã giữ chỗ cho đơn
        khác, rồi lấy lô cũ trước — cùng thứ tự mà `action_assign` sẽ chọn thật
        khi lập phiếu cấp vật tư (`removal_strategy_id = fifo`). Không tự viết
        bộ chia khác, hai nguồn sự thật là sai im lặng.

        Lô không có giá mua (tồn đầu kỳ, nhận tay) lấy giá vốn tham chiếu và
        được đánh dấu `estimated` để dải cảnh báo nói ra."""
        Location = self.env["stock.location"]
        location = Location.sudo()._dlm_location(_DLM_MATERIAL_LOCATION)
        if not location:
            return []
        quants = self.env["stock.quant"].sudo().search([
            ("location_id", "child_of", location.id),
            ("product_id", "=", material.id),
        ])
        rounding = material.uom_id.rounding or 0.01

        # FIFO = ngày nhập lô tăng dần. Lô không rõ ngày xếp cuối (an toàn hơn:
        # không cho hàng mù ngày chen lên trước hàng có chứng từ rõ).
        def _khoa(quant):
            lot = quant.lot_id
            ngay = lot.dlm_receipt_date if lot else False
            return (0, ngay, lot.id) if ngay else (1, False, lot.id if lot else 0)

        rows = []
        con_lai = need
        for quant in quants.sorted(key=_khoa):
            if float_compare(con_lai, 0.0, precision_rounding=rounding) <= 0:
                break
            kha_dung = quant.quantity - quant.reserved_quantity
            if float_compare(kha_dung, 0.0, precision_rounding=rounding) <= 0:
                continue
            lay = min(con_lai, kha_dung)
            lot = quant.lot_id
            gia = lot.dlm_unit_cost if lot else 0.0
            uoc_tinh = not lot or not gia or lot.dlm_cost_is_estimated
            if not gia:
                gia = material.standard_price or 0.0
            if float_is_zero(gia, precision_digits=2):
                # Không tra được giá nào cho lô này ⇒ bỏ qua, để phần đó rơi
                # sang "phải mua" theo giá bảng. Tính bằng 0 là báo giá bán lỗ.
                continue
            rows.append({"lot": lot, "qty": lay, "cost": gia,
                         "estimated": uoc_tinh})
            con_lai -= lay
        return rows

    def _dlm_price_note(self, material, lo_dung, qty_mua, gia_mua):
        """Câu giải trình đơn giá — bằng SỐ, để trang Phân tích giá thành nói được vì sao."""
        don_vi = material.uom_id.name or ""
        phan = []
        for row in lo_dung:
            phan.append(_("%(qty)s %(uom)s từ lô %(lot)s @ %(gia)s%(uoc)s") % {
                "qty": self._fmt_qty(row["qty"]),
                "uom": don_vi,
                "lot": row["lot"].name if row["lot"] else _("(không lô)"),
                "gia": self._fmt_vnd(row["cost"]),
                "uoc": _(" — ước tính") if row["estimated"] else "",
            })
        if qty_mua > 0:
            phan.append(_("%(qty)s %(uom)s phải mua @ %(gia)s (bảng giá NCC)") % {
                "qty": self._fmt_qty(qty_mua),
                "uom": don_vi,
                "gia": self._fmt_vnd(gia_mua),
            })
        return " · ".join(phan)

    @staticmethod
    def _fmt_qty(value):
        txt = "{:,.3f}".format(value or 0.0).replace(",", "@").replace(".", ",")
        txt = txt.replace("@", ".")
        return txt.rstrip("0").rstrip(",") if "," in txt else txt


class DlQuotation(models.Model):
    """Mặt báo giá của lớp trộn giá kho: nói ra vật tư nào thiếu và giao việc hỏi giá."""

    _inherit = "dl.quotation"

    dlm_shortage_html = fields.Html(
        string="Vật tư phải mua thêm", compute="_compute_dlm_shortage",
        compute_sudo=True, sanitize=False, readonly=True,
        help="Phần nhu cầu vượt tồn kho — đang tạm tính theo bảng giá nhà cung "
             "cấp. Bảng giá cũ thì con số này cũ theo.")
    dlm_has_shortage = fields.Boolean(
        string="Có vật tư phải mua", compute="_compute_dlm_shortage",
        compute_sudo=True)

    @api.depends("line_ids.component_ids.dlm_qty_to_buy")
    def _compute_dlm_shortage(self):
        for quo in self:
            thieu = quo._dlm_shortage_rows()
            quo.dlm_has_shortage = bool(thieu)
            quo.dlm_shortage_html = quo._dlm_shortage_table(thieu) if thieu else False

    def _dlm_shortage_rows(self):
        """{vật tư: số phải mua} gộp qua mọi dòng — một vật tư dùng ở nhiều dòng chỉ hỏi giá một lần."""
        self.ensure_one()
        gop = {}
        for comp in self.sudo().line_ids.component_ids:
            if comp.component_type != "material" or not comp.material_id:
                continue
            if comp.dlm_qty_to_buy <= 0:
                continue
            gop[comp.material_id] = (
                gop.get(comp.material_id, 0.0) + comp.dlm_qty_to_buy)
        return [{"product": sp, "qty": qty} for sp, qty in gop.items()]

    def _dlm_shortage_table(self, rows):
        Service = self.env["dl.quotation.pricing.service"]
        body = "".join(
            "<tr><td>%s</td><td class='text-end'>%s %s</td></tr>" % (
                html_escape(row["product"].display_name),
                Service._fmt_qty(row["qty"]),
                html_escape(row["product"].uom_id.name or ""))
            for row in rows)
        return Markup(
            "<table class='table table-sm mb-0'><thead><tr>"
            "<th>Vật tư</th><th class='text-end'>Phải mua thêm</th>"
            "</tr></thead><tbody>%s</tbody></table>") % Markup(body)

    dlm_vendor_quote_count = fields.Integer(
        string="Đơn hỏi giá", compute="_compute_dlm_vendor_quote_count",
        compute_sudo=True)

    def _compute_dlm_vendor_quote_count(self):
        PO = self.env["dl.purchase.order"].sudo()
        for quo in self:
            quo.dlm_vendor_quote_count = PO.search_count(
                [("dlm_quotation_id", "=", quo.id)]) if quo.id else 0

    def action_dlm_open_vendor_quotes(self):
        """Smart button: từ báo giá nhìn sang các đơn hỏi giá nó đã sinh ra."""
        self.ensure_one()
        don = self.env["dl.purchase.order"].sudo().search(
            [("dlm_quotation_id", "=", self.id)])
        return don._dlm_open_orders(_("Đơn hỏi giá của %s") % self.name)

    def action_dlm_request_vendor_quote(self):
        """Nút [Hỏi giá nhà cung cấp] — sinh ĐƠN HỎI GIÁ thật, không phải lời nhắc.

        Trước đây nút này chỉ đẻ một activity. Activity là lời nhắc: không trạng
        thái, xoá được, không lọc thành hàng đợi, không tra ngược được — Mua hàng
        nhận xong vẫn phải tự mò sang màn Bảng giá gõ tay, và không gì nối hai
        đầu lại. Nay nó sinh `dl.purchase.order` ở nấc "Đã gửi hỏi giá", gắn vào
        báo giá, để Mua hàng làm việc TRÊN MÀN CỦA HỌ.

        🔴 KHÔNG chốt đơn: báo giá chưa chắc thắng, đặt hàng ở đây là mua cho một
        đơn chưa tồn tại. Đơn nằm chờ; khách chốt thật thì chốt tiếp, giá đã có sẵn."""
        self.ensure_one()
        rows = self._dlm_shortage_rows()
        if not rows:
            raise UserError(_(
                "Báo giá này không thiếu vật tư nào — mọi thứ lấy được từ kho, "
                "không có gì để hỏi giá."))
        PO = self.env["dl.purchase.order"].sudo()
        da_co = PO.search([("dlm_quotation_id", "=", self.id),
                           ("state", "not in", ("cancelled",))])
        if da_co:
            return da_co._dlm_open_orders(_("Đơn hỏi giá của %s") % self.name)

        # Gom theo NHÀ CUNG CẤP: mỗi NCC một đơn, vì đó là một cuộc hỏi giá.
        theo_ncc = {}
        for row in rows:
            ncc = self._dlm_vendor_of(row["product"])
            if not ncc:
                raise UserError(_(
                    "Vật tư “%s” chưa khai nhà cung cấp nào — không "
                    "biết hỏi giá ai. Khai nhà cung cấp cho vật tư này trước.")
                    % row["product"].display_name)
            theo_ncc.setdefault(ncc, []).append(row)

        don = PO
        for ncc, ds in theo_ncc.items():
            don |= PO.create({
                "partner_id": ncc.id,
                "dlm_quotation_id": self.id,
                "state": "sent",
                "line_ids": [(0, 0, {
                    "product_id": r["product"].id,
                    "qty": r["qty"],
                }) for r in ds],
            })
        self.message_post(body=_(
            "Đã lập %(n)s đơn hỏi giá gửi nhà cung cấp: %(ds)s. Mua hàng nhập "
            "giá rồi bấm <b>Ghi nhận giá NCC báo</b>; xong thì báo giá này gửi "
            "khách được.") % {"n": len(don), "ds": ", ".join(don.mapped("name"))})
        return don._dlm_open_orders(_("Đơn hỏi giá của %s") % self.name)

    @staticmethod
    def _dlm_vendor_of(product):
        """NCC để hỏi giá: ưu tiên bên đang áp dụng giá, không có thì bên đã duyệt."""
        sellers = product.sudo().seller_ids
        return (sellers.filtered("is_applied")[:1].partner_id
                or sellers.filtered(lambda r: r.approval_state == "approved")[:1].partner_id
                or sellers[:1].partner_id)

    def _dlm_stamp_price_confirmed(self, order):
        """Đơn hỏi giá ghi nhận xong ⇒ tính lại báo giá theo giá vừa hỏi, rồi mở cổng.

        🔴 Thứ tự bắt buộc: TÍNH LẠI trước, ĐÓNG DẤU sau. Ngược lại thì
        `recompute_quotation` xoá sạch dấu vừa đóng (giá đổi ⇒ xác nhận cũ hết
        hiệu lực) và cổng không bao giờ mở.

        Vì sao phải tính lại: hỏi giá xong mà báo giá vẫn mang giá cũ thì con số
        gửi khách không phải con số Mua hàng vừa xác nhận — đúng cái lỗ mà cả
        cổng này sinh ra để bịt."""
        self.ensure_one()
        # Không có RFQ thì không có định mức để tính lại (báo giá dựng tay).
        # Vẫn đóng dấu — nhưng cổng KHÔNG mở oan: `_dlm_buy_price_moved` thấy
        # giá bảng đã khác giá trong báo giá nên vẫn chặn, và câu báo sẽ chỉ
        # đúng việc phải làm (bấm Cập nhật giá theo thị trường).
        if self.quotation_request_id and self.state in ("draft", "approved", "sent"):
            self.env["dl.quotation.pricing.service"].sudo().recompute_quotation(
                self, extend_validity=True,
                reason=_("Tính lại theo giá nhà cung cấp vừa báo (đơn %s).")
                       % order.name)
        self.sudo().write({
            "dlm_price_confirm_date": fields.Datetime.now(),
            "dlm_price_confirm_uid": self.env.user.id,
        })
        self.sudo().message_post(body=_(
            "<b>Mua hàng đã ghi nhận giá</b> qua đơn hỏi giá %s. Báo giá gửi "
            "khách được.") % order.name)
        return True


    # ------------------------------------------------------------------
    # Cổng: giá MUA phải được xác nhận trước khi cam kết với khách
    # ------------------------------------------------------------------
    # Phần vật tư LẤY TỪ KHO có giá chắc chắn (giá lô đã đóng, bất biến). Phần
    # PHẢI MUA thì không: nó đang tạm tính theo bảng giá NCC, mà bảng giá với
    # mặt hàng thép có thể đã cũ. Gửi khách lúc đó là cam kết 7 ngày trên một
    # con số CHƯA AI KIỂM — mua về đắt hơn thì phần chênh ăn thẳng vào biên lãi,
    # và không có chứng từ nào nổ ra để biết.
    dlm_price_confirm_date = fields.Datetime(
        string="Giá mua đã xác nhận lúc", readonly=True, copy=False)
    dlm_price_confirm_uid = fields.Many2one(
        "res.users", string="Người xác nhận giá mua", readonly=True, copy=False)
    dlm_need_price_confirm = fields.Boolean(
        string="Chờ xác nhận giá mua", compute="_compute_dlm_need_price_confirm",
        compute_sudo=True,
        help="Báo giá có vật tư phải mua thêm nhưng Mua hàng chưa xác nhận giá "
             "mua còn đúng. Chưa xác nhận thì chưa gửi khách được.")

    @api.depends("dlm_has_shortage", "dlm_price_confirm_date",
                 "line_ids.component_ids.dlm_buy_price")
    def _compute_dlm_need_price_confirm(self):
        for quo in self:
            if not quo.dlm_has_shortage:
                quo.dlm_need_price_confirm = False
            elif not quo.dlm_price_confirm_date:
                quo.dlm_need_price_confirm = True
            else:
                # 🔴 Xác nhận gắn vào MỘT CON SỐ, không phải một cái tick.
                # Bảng giá nhúc nhích sau lúc xác nhận ⇒ báo giá đang mang giá
                # cũ trong khi Mua hàng đã chốt giá khác: cổng phải đóng lại,
                # không thì xác nhận chỉ là con dấu rỗng.
                quo.dlm_need_price_confirm = bool(quo._dlm_buy_price_moved())

    def _dlm_buy_price_moved(self):
        """Giá mua đã dùng trong báo giá có còn khớp bảng giá đang áp dụng không."""
        self.ensure_one()
        for comp in self.sudo().line_ids.component_ids:
            if comp.component_type != "material" or comp.dlm_qty_to_buy <= 0:
                continue
            seller = comp.material_id.sudo().seller_ids.filtered("is_applied")[:1]
            if not seller:
                continue
            if float_compare(comp.dlm_buy_price, seller.price,
                             precision_digits=2) != 0:
                return True
        return False

    @api.depends("dlm_need_price_confirm")
    def _compute_dlm_send_blocked(self):
        """Nối cờ chặn chung vào cổng giá mua — để dải "sẵn sàng gửi khách" của
        dl_sale tự tắt, khỏi nói ngược với dải cảnh báo ngay trên nó."""
        for quo in self:
            quo.dlm_send_blocked = quo.dlm_need_price_confirm

    def _dlm_check_ready_to_send(self):
        """Chặn gửi khách khi giá phần PHẢI MUA chưa được Mua hàng xác nhận."""
        self.ensure_one()
        if not self.dlm_need_price_confirm:
            return super()._dlm_check_ready_to_send()
        if self.dlm_price_confirm_date and self._dlm_buy_price_moved():
            raise UserError(_(
                "Bảng giá nhà cung cấp đã đổi SAU khi Mua hàng xác nhận — báo "
                "giá %(ten)s đang mang giá mua cũ. "
                "Bấm “Cập nhật giá theo thị trường” để tính lại theo "
                "giá hiện hành, rồi để Mua hàng xác nhận lại."
            ) % {"ten": self.name})
        raise UserError(_(
            "Báo giá %(ten)s có vật tư phải mua thêm, nhưng giá mua chưa được "
            "Mua hàng xác nhận.\n\n"
            "Phần lấy từ kho có giá chắc chắn; phần phải mua đang tạm tính theo "
            "bảng giá nhà cung cấp — gửi khách lúc này là cam kết 7 ngày trên "
            "một con số chưa ai kiểm. Mua về đắt hơn thì phần chênh trừ thẳng "
            "vào lợi nhuận.\n\n"
            "Bấm \"Hỏi giá nhà cung cấp\" để giao việc cho Mua hàng. Xác nhận "
            "xong mới gửi khách được."
        ) % {"ten": self.name})

    def action_dlm_confirm_buy_price(self):
        """Nút [Xác nhận giá mua] — Mua hàng khẳng định giá phần phải mua còn đúng.

        Đóng dấu cả khi giá KHÔNG đổi: hỏi nhà cung cấp mà giá y cũ vẫn là một
        lần kiểm. Nếu chỉ nhận tín hiệu "bảng giá vừa được sửa" thì ca giá không
        đổi sẽ kẹt vĩnh viễn."""
        self.ensure_one()
        if not self.env.user.has_group("dl_base.dl_group_purchasing") \
                and not self.env.user.has_group("dl_base.dl_group_admin"):
            raise UserError(_(
                "Chỉ nhóm Mua hàng xác nhận được giá mua — đây là kiểm soát "
                "chéo giữa người chào giá và người biết giá thị trường."))
        if not self.dlm_has_shortage:
            raise UserError(_(
                "Báo giá này không có vật tư phải mua thêm — không có giá mua "
                "nào để xác nhận."))
        self.sudo().write({
            "dlm_price_confirm_date": fields.Datetime.now(),
            "dlm_price_confirm_uid": self.env.user.id,
        })
        self.sudo().message_post(body=_(
            "<b>%s xác nhận giá mua</b> cho phần vật tư phải mua thêm. Báo giá "
            "gửi khách được.") % self.env.user.name)
        return True

    def recompute_quotation_clear_confirm(self):
        """Giá vừa tính lại ⇒ xác nhận cũ hết hiệu lực (số phải mua đã khác)."""
        self.sudo().write({
            "dlm_price_confirm_date": False,
            "dlm_price_confirm_uid": False,
        })
        return True
