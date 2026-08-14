# -*- coding: utf-8 -*-
"""K16 — Kiểm tra kho & Điều phối đơn bán hàng.

Thiết kế: ``docs/Thiet_ke_luong_sau_don_hang_check_kho_dieu_phoi.md`` §3
và ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §3.

Trước bản này, đường duy nhất từ đơn bán sang kho là bấm tay [Tạo phiếu giao] —
bất kể kho có gì. Đơn hàng gia công thì còn không có đường nào cả: không ai từng
hỏi BOM "làm 10 cái thì cần bao nhiêu thép".

🔴 **LỆCH DOC CÓ CHỦ Ý — không tạo loại hoạt động [10] `XVT`.** Doc B1.5 §3.5 đề
xuất một loại phiếu mới cho việc "xuất vật tư ra xưởng". Nhưng phiếu **Chuyển
kho nội bộ** (`CK`) đi tuyến ``Kho nguyên vật liệu → Xưởng sản xuất`` đã có sẵn
TẤT CẢ những gì loại mới cần:

  • hai chữ ký thủ kho → Kỹ thuật (K15) — chặn cứng ở ``button_validate``;
  • bảng đối chiếu "định mức BOM / đã cấp / cộng dồn" khi phiếu gắn đơn (K16);
  • cờ "Cấp bổ sung ngoài định mức" + lý do bắt buộc;
  • ``dlm_sale_order_id``, form riêng, luật khu, guard nguồn/đích.

Thêm loại thứ 10 là chép lại bốn thứ đó để chúng lệch nhau về sau, và bắt thủ
kho học một chứng từ mới cho đúng việc họ đang làm. Cái doc thật sự đòi là **tách
BÀN GIAO khỏi TIÊU THỤ** (D-04) — điều đó đã đúng sẵn: bàn giao là `CK`, tiêu thụ
là dòng ``consume`` của phiếu [8].

Ba chỗ **không** làm ở đây, cố ý:
  • Không lưu kết quả kiểm kho. Một bảng ghi "đã kiểm, kết quả đủ" chính là con
    số cũ đúng vào lúc nó bắt đầu sai (D-01/D-02).
  • Không tự phân bổ hàng về đơn khi hàng NCC về. Ai điều phối trước thì giữ chỗ
    trước — chỉ con người biết đơn nào gấp (§4.4 doc Mua hàng).
  • Không tự nhả chỗ giữ vì quá hạn. Chỗ giữ là cam kết với khách.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

# U-4 (người dùng chốt 2026-08-14) — Thủ kho là CHỦ SỞ HỮU bước điều phối: họ là
# người biết hàng thật. Sales/Trưởng KD chỉ XEM (chip + dải trên form đơn).
# Hai lối vào mà không ai chịu trách nhiệm ⇒ đơn nằm chờ vì "tưởng bên kia làm".
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
    # 🔴 Tuyệt đối không depends `stock.quant`: mỗi lần bất kỳ phiếu kho nào
    # validate là recompute mọi đơn ⇒ hệ thống bò. Câu hỏi "còn thiếu vật tư
    # không" chỉ được hỏi trên FORM (§9.1 doc B1.5).
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
        """Bảng cung ứng của đơn — ba nhánh hàng, ba câu hỏi khác nhau.

        Trả về dict:
          ``goods``     [{product, need, ready, to_make, kind}] theo mặt hàng bán
          ``materials`` [{product, need, available, missing}] nhu cầu vật tư gộp
          ``blocking``  [câu chặn] — có cái nào thì KHÔNG điều phối được
          ``warnings``  [câu cảnh báo mềm]

        🔴 Khả dụng đọc tại ĐÚNG khu mà phiếu sẽ lấy hàng, không dùng
        ``product.free_qty`` — nó cộng cả hàng chưa qua QC ở khu Chờ kiểm.
        """
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
        # Sổ hàng đã hứa trong CHÍNH lần kiểm này: hai dòng cùng mặt hàng không
        # được cùng nhìn thấy một lô thành phẩm rồi cùng báo "đủ".
        taken = {}

        for product, qty in remaining.items():
            line = self._dlm_line_for(product)
            made_to_order = product.detailed_type == "consu"
            if made_to_order:
                # DP-10 — Hạng A không có tồn và KHÔNG được hỏi tồn. Ghi "không
                # tính", không ghi "Tồn: 0": báo hết hàng cho hàng đặt riêng là
                # dạy người dùng bỏ qua cảnh báo.
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

        # 🔴 "Còn việc để làm" KHÔNG bằng "còn dòng hàng chưa giao". Đơn gia
        # công đã cấp đủ vật tư vẫn còn nguyên dòng hàng chưa giao — hàng đang
        # nằm ở xưởng. Nếu lấy `goods` rỗng làm điều kiện thì nút Điều phối ở
        # lại vĩnh viễn, bấm thì không sinh gì, và người dùng học được rằng nút
        # của hệ thống này bấm cũng chẳng sao.
        result["actionable"] = bool(
            any(row["ready"] > 0 for row in result["goods"])
            or result["materials"])
        return result

    def _dlm_collect_needs(self, line, product, qty, material_need, location,
                           result):
        """Phần PHẢI LÀM của một mặt hàng biến thành nhu cầu gì.

        Hàng thương mại không có BOM ⇒ thứ phải mua chính là **mặt hàng đó**
        (U-5). Bỏ nhánh này là bỏ gần một nửa doanh thu của Đại Linh ra ngoài
        hệ thống — xem ``docs/Thiet_ke_mua_hang_va_vong_cung_ung.md`` §3.3.
        """
        self.ensure_one()
        # 🔴 `sudo()` NGAY TỪ ĐÂY, không phải chỉ ở lời gọi nổ BOM. Thủ kho
        # không có quyền đọc `dl.bom` (định mức là tài sản của Kỹ thuật) — đọc
        # `bom.status` ở dòng dưới mà quên sudo là ném AccessError vào giữa màn
        # Điều phối. Chỉ số LƯỢNG đi ra khỏi đây; không field tiền nào bị chạm,
        # đúng khuôn `stock_picking._dlm_bom_required_qty` đã dùng.
        bom = line.bom_id.sudo() if line else False
        if not bom:
            if line and line.line_type == "manufactured":
                # DP-03 — dòng gia công thiếu BOM: không tính được nhu cầu, mà
                # điều phối vẫn "chạy" ⇒ kết quả sai trông như đúng.
                result["blocking"].append(_(
                    "Dòng gia công \"%s\" chưa gắn định mức (BOM) — không tính "
                    "được cần bao nhiêu vật tư."
                ) % product.display_name)
                return
            # Hàng thương mại / hàng không định mức: mua chính nó.
            _add(material_need, product, qty)
            return

        if bom.status not in ("confirmed", "locked"):
            # DP-06 — cảnh báo MỀM. Chặn cứng là chặn cả ca hợp lệ.
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
        """{vật tư: số đã nằm trên phiếu cấp vật tư chưa xong của đơn này}.

        Không trừ phần này thì bấm điều phối lần hai là giữ chỗ gấp đôi — cùng
        cái bẫy mà ``_dlm_planned_qty`` đã phải xử ở nhánh giao hàng.
        """
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
                # 🔴 Định mức vòng lặp (DP-07) làm hàm nổ BOM raise. Trong một
                # computed field thì raise = CHẾT CẢ FORM, kể cả với Sales —
                # người không sửa được BOM và cũng không hiểu lỗi. Biến nó thành
                # dải đỏ đọc được; chặn thật vẫn nằm ở action.
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
        """Một câu nói được tình hình — dải trên cùng đọc câu này.

        Nêu SỐ và TÊN, không chỉ "thiếu vật tư": người đọc phải biết đi mua gì
        mà không cần mở bảng.
        """
        if check["blocking"]:
            return check["blocking"][0]
        if not check["actionable"]:
            # Hai ca rất khác nhau, và người dùng cần phân biệt: đơn đã xong
            # hẳn, hay đơn đang nằm ở xưởng chờ làm. Nói nhầm ca thứ hai thành
            # "xong rồi" là đóng đơn trong đầu người đọc.
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
        """Bảng HTML hai phần: mặt hàng bán và vật tư.

        Dùng HTML computed thay vì component OWL — cùng khuôn
        ``stock_picking._dlm_build_bom_hint`` đang chạy, nên thừa hưởng luôn
        style bảng của Odoo và không phải nuôi thêm asset nào.
        """
        self.ensure_one()
        if not check["goods"] and not check["materials"]:
            return False
        blocks = []
        if check["goods"]:
            rows = []
            for row in check["goods"]:
                if row["made_to_order"]:
                    # DP-10 — không ghi "0", ghi lý do.
                    san_sang = _("không tính — hàng đặt riêng")
                else:
                    san_sang = _dlm_num(row["ready"])
                rows.append(
                    "<tr><td>%s</td><td>%s</td><td class='text-end'>%s</td>"
                    "<td class='text-end'>%s</td><td class='text-end'>%s</td>"
                    "</tr>" % (
                        row["product"].display_name, row["kind"],
                        _dlm_num(row["need"]), san_sang,
                        _dlm_num(row["to_make"])))
            blocks.append(_dlm_table(
                [_("Mặt hàng"), _("Nhánh"), _("Cần giao"), _("Giao được ngay"),
                 _("Phải làm/mua")], rows))
        if check["materials"]:
            rows = []
            for row in check["materials"]:
                thieu = row["missing"]
                # Không chỉ tô màu: dòng thiếu phải NÓI ra bằng chữ — bảng in ra
                # giấy hoặc người mù màu vẫn phải phân biệt được.
                danh_gia = (_("thiếu %s") % _dlm_num(thieu) if thieu > 0
                            else _("đủ"))
                rows.append(
                    "<tr class='%s'><td>%s</td><td class='text-end'>%s</td>"
                    "<td class='text-end'>%s</td><td>%s</td></tr>" % (
                        "table-warning" if thieu > 0 else "",
                        row["product"].display_name, _dlm_num(row["need"]),
                        _dlm_num(row["available"]), danh_gia))
            blocks.append(_dlm_table(
                [_("Vật tư / hàng phải mua"), _("Cần"), _("Còn lấy được"),
                 _("Đánh giá")], rows))
        return "".join(blocks)

    # ------------------------------------------------------------------
    # Bước 2 — ĐIỀU PHỐI: một nút, N chứng từ, cùng một transaction
    # ------------------------------------------------------------------
    def action_dlm_dispatch(self):
        """Sinh mọi chứng từ mà đơn này cần, trong MỘT lần bấm.

        Hợp đồng: có lỗi chặn ⇒ raise và KHÔNG sinh chứng từ nào. Tính lại bảng
        kiểm SỐNG (DP-15) — không tin con số của lần mở màn trước.
        """
        self.ensure_one()
        self._dlm_check_dispatch_allowed()
        check = self._dlm_supply_check()
        if check["blocking"]:
            raise UserError(_(
                "Chưa điều phối được đơn %(order)s:\n\n%(problems)s"
            ) % {"order": self.name,
                 "problems": "\n".join("• " + p for p in check["blocking"])})
        if not check["actionable"]:
            # DP-08 — bấm hai lần là giữ chỗ gấp đôi.
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

        # sudo khi ghi chatter: Thủ kho chỉ có quyền ĐỌC `dl.sale.order` (ACL
        # 1,0,0,0) nên `mail.message create` bị chặn — và một dòng nhật ký
        # không được phép làm hỏng cả lượt điều phối đã sinh chứng từ thật.
        # `author_id` truyền tường minh để vết còn ghi ĐÚNG người bấm, không
        # phải OdooBot. Cùng khuôn `_notify_approvers` của dl_config.
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
        """Phiếu giao cho phần thành phẩm lấy được NGAY.

        🔴 Chỉ phần khả dụng, không phải cả dòng đơn. Phiếu giao cho hàng chưa
        tồn tại sẽ treo mãi trong hàng đợi thủ kho — đúng lý do K6 cố ý không
        tự sinh phiếu giao lúc chốt đơn.
        """
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
        """MỘT phiếu cấp vật tư cho CẢ đơn — không phải mỗi dòng một phiếu.

        Hai dòng gia công của cùng một đơn hay ăn chung thép hộp 30×60; tách hai
        phiếu thì mỗi phiếu tự thấy "đủ" trong khi cộng lại thì thiếu.

        Đưa nguyên nhu cầu lên phiếu (kể cả phần đang thiếu) rồi để
        ``action_assign`` giữ được bao nhiêu hay bấy nhiêu: chờ mua đủ mới giữ
        chỗ là để đơn khác bốc mất phần đang có.
        """
        self.ensure_one()
        # 🔴 CHỈ thứ xưởng thật sự dùng được. Hàng THƯƠNG MẠI cũng nằm trong
        # `check["materials"]` (nó là thứ phải mua khi thiếu — U-5), nhưng nó
        # không có việc gì ở xưởng: mua về là bán thẳng. Đẩy nó lên phiếu ra
        # Xưởng thì luật khu chặn đúng (`_DLM_WORKSHOP_KINDS` không có
        # 'trading') và cả lượt điều phối chết — kéo theo cả nhánh gia công
        # hợp lệ trong cùng đơn.
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
        """Móc nối cho phần THIẾU — mặc định không làm gì.

        ``dl_inventory`` không biết gì về mua hàng, và không được biết: gỡ
        ``dl_purchase`` ra thì phân hệ Kho vẫn phải chạy. Module Mua hàng ghi đè
        hàm này để sinh đơn mua nháp (xem ``dl_purchase``).

        Trả về danh sách nhãn để ghi vào chatter.
        """
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


def _dlm_table(headers, rows):
    return (
        "<table class='table table-sm mb-2'><thead><tr>%s</tr></thead>"
        "<tbody>%s</tbody></table>" % (
            "".join("<th>%s</th>" % head for head in headers),
            "".join(rows)))
